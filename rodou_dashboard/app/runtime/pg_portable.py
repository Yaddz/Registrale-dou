"""Gerenciamento do PostgreSQL 17 portátil para o modo local do INLABS.

Controla inicialização (`initdb`), ciclo de vida (`pg_ctl start/stop`),
detecção de porta livre em `127.0.0.1`, geração segura de senha persistida
no SQLite e criação do schema `dou_inlabs` + extensão `unaccent`.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import secrets
import shlex
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
from typing import Any, Dict, Optional
from urllib.parse import quote_plus

from .paths import get_base_dir, get_db_path, get_logs_dir, get_pg_bin_dir, get_pgdata_dir

logger = logging.getLogger(__name__)

_PG_SETTINGS_KEY = "inlabs_pg_config"
_DEFAULT_PORT = 54329
_DEFAULT_USER = "postgres"
_DEFAULT_DATABASE = "inlabs"


class PortablePostgresError(RuntimeError):
    """Erro operacional ao inicializar, iniciar ou parar o PostgreSQL portátil."""


class PostgresBinariesNotFoundError(PortablePostgresError):
    """Lançada quando os binários do PostgreSQL portátil não estão disponíveis."""


def find_free_port(preferred: int = _DEFAULT_PORT, host: str = "127.0.0.1") -> int:
    """Retorna `preferred` se livre em `host`, ou outra porta TCP livre do sistema."""
    for candidate in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, candidate))
                return int(sock.getsockname()[1])
            except OSError:
                continue
    raise PortablePostgresError(f"Não foi possível encontrar uma porta livre em {host}.")


def _subprocess_kwargs() -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {}
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def _exe_name(bin_dir: Path, tool: str) -> str:
    suffix = ".exe" if os.name == "nt" else ""
    candidate = bin_dir / f"{tool}{suffix}"
    if not candidate.is_file():
        raise PostgresBinariesNotFoundError(
            f"Binário '{tool}{suffix}' não encontrado em {bin_dir}."
        )
    return str(candidate)


def _read_pg_config_sqlite(db_path: Path) -> Optional[Dict[str, Any]]:
    if not db_path.is_file():
        return None
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?",
                (_PG_SETTINGS_KEY,),
            ).fetchone()
            if row and row[0]:
                data = json.loads(row[0])
                if isinstance(data, dict):
                    return data
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    except json.JSONDecodeError:
        return None
    return None


def _write_pg_config_sqlite(db_path: Path, payload: Dict[str, Any]) -> None:
    if not db_path.is_file():
        return
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        try:
            serialized = json.dumps(payload)
            cur = conn.execute(
                "UPDATE settings SET value = ? WHERE key = ?",
                (serialized, _PG_SETTINGS_KEY),
            )
            if cur.rowcount == 0:
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?)",
                    (_PG_SETTINGS_KEY, serialized),
                )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logger.warning("Não foi possível persistir configuração do Postgres portátil no SQLite: %s", exc)


def _load_init_sql_statements() -> list[str]:
    """Lê `runtime/sql/init-db.sql` filtrando comandos meta do `psql`."""
    sql_path = Path(__file__).resolve().parent / "sql" / "init-db.sql"
    if sql_path.is_file():
        raw = sql_path.read_text(encoding="utf-8")
        lines = []
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("\\"):
                continue
            if stripped.upper().startswith("CREATE DATABASE "):
                continue
            lines.append(line)
        cleaned = "\n".join(lines).strip()
        if cleaned:
            return [stmt.strip() for stmt in cleaned.split(";") if stmt.strip()]

    return [
        "CREATE SCHEMA IF NOT EXISTS dou_inlabs",
        """
        CREATE TABLE IF NOT EXISTS dou_inlabs.article_raw (
            id BIGINT PRIMARY KEY,
            name TEXT,
            idoficio BIGINT,
            pubname TEXT,
            arttype TEXT,
            pubdate TIMESTAMP WITHOUT TIME ZONE,
            artclass TEXT,
            artcategory TEXT,
            artsize BIGINT,
            artnotes TEXT,
            numberpage BIGINT,
            pdfpage TEXT,
            editionnumber TEXT,
            highlighttype TEXT,
            highlightpriority FLOAT,
            highlight TEXT,
            highlightimage TEXT,
            highlightimagename TEXT,
            idmateria BIGINT,
            midias TEXT,
            identifica TEXT,
            data TEXT,
            ementa TEXT,
            titulo TEXT,
            subtitulo TEXT,
            texto TEXT,
            assina TEXT
        )
        """.strip(),
    ]


class PortablePostgres:
    """Gerencia uma instância local isolada do PostgreSQL 17."""

    def __init__(
        self,
        pgdata_dir: Optional[Path] = None,
        bin_dir: Optional[Path] = None,
        db_path: Optional[Path] = None,
        preferred_port: int = _DEFAULT_PORT,
    ) -> None:
        self._lock = threading.Lock()
        self._pgdata_dir = Path(pgdata_dir) if pgdata_dir is not None else None
        self._bin_dir = Path(bin_dir) if bin_dir is not None else None
        self._db_path = Path(db_path) if db_path is not None else None
        self._preferred_port = preferred_port
        self._port: Optional[int] = None
        self._password: Optional[str] = None
        self._user = _DEFAULT_USER
        self._database = _DEFAULT_DATABASE
        self._started_by_us = False

    @property
    def host(self) -> str:
        return "127.0.0.1"

    @property
    def port(self) -> Optional[int]:
        return self._port

    @property
    def user(self) -> str:
        return self._user

    @property
    def database(self) -> str:
        return self._database

    @property
    def password(self) -> str:
        if self._password is None:
            self._password = self._load_or_create_password()
        return self._password

    def _resolve_pgdata_dir(self, create: bool = True) -> Path:
        if self._pgdata_dir is not None:
            if create:
                self._pgdata_dir.mkdir(parents=True, exist_ok=True)
            return self._pgdata_dir
        return get_pgdata_dir(create=create)

    def _resolve_bin_dir(self) -> Path:
        if self._bin_dir is not None:
            if self._bin_dir.is_dir():
                return self._bin_dir
            raise PostgresBinariesNotFoundError(
                f"Diretório de binários PostgreSQL inexistente: {self._bin_dir}"
            )
        found = get_pg_bin_dir()
        if found is None:
            raise PostgresBinariesNotFoundError(
                "Binários do PostgreSQL portátil não encontrados em windows/vendor/pgsql/ nem no PATH."
            )
        return found

    def _resolve_db_path(self) -> Path:
        if self._db_path is not None:
            return self._db_path
        return get_db_path()

    def _load_or_create_password(self) -> str:
        db_path = self._resolve_db_path()
        cfg = _read_pg_config_sqlite(db_path)
        if cfg and cfg.get("password"):
            return str(cfg["password"])

        generated = secrets.token_urlsafe(24)
        _write_pg_config_sqlite(
            db_path,
            {
                "user": self._user,
                "password": generated,
                "database": self._database,
                "port": self._port or self._preferred_port,
            },
        )
        return generated

    def _persist_port(self, port: int) -> None:
        db_path = self._resolve_db_path()
        cfg = _read_pg_config_sqlite(db_path) or {}
        cfg.update(
            {
                "user": self._user,
                "password": self.password,
                "database": self._database,
                "port": int(port),
            }
        )
        _write_pg_config_sqlite(db_path, cfg)

    def _ensure_initialized(self, bin_dir: Path, pgdata: Path) -> None:
        if (pgdata / "PG_VERSION").is_file():
            return

        initdb_exe = _exe_name(bin_dir, "initdb")
        pw = self.password
        pw_file: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                delete=False,
                prefix="reg_pg_",
            ) as tmp:
                tmp.write(pw + "\n")
                pw_file = tmp.name

            cmd = [
                initdb_exe,
                "-D",
                str(pgdata),
                "-U",
                self._user,
                "--auth=scram-sha-256",
                "--encoding=UTF8",
                "--locale=C",
                f"--pwfile={pw_file}",
            ]
            logger.info("Inicializando cluster PostgreSQL portátil em %s...", pgdata)
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                **_subprocess_kwargs(),
            )
            if res.returncode != 0:
                raise PortablePostgresError(
                    f"Falha no initdb (exit={res.returncode}): {res.stderr.strip() or res.stdout.strip()}"
                )
        finally:
            if pw_file and os.path.exists(pw_file):
                try:
                    os.unlink(pw_file)
                except OSError:
                    pass

        conf_path = pgdata / "postgresql.conf"
        if conf_path.is_file():
            try:
                content = conf_path.read_text(encoding="utf-8", errors="ignore")
                if "listen_addresses = '127.0.0.1'" not in content:
                    with open(conf_path, "a", encoding="utf-8") as fh:
                        fh.write("\nlisten_addresses = '127.0.0.1'\n")
            except OSError:
                pass

    def is_running(self) -> bool:
        """Retorna True se o cluster PostgreSQL portátil estiver ativo."""
        pgdata = self._resolve_pgdata_dir(create=False)
        if not (pgdata / "postmaster.pid").is_file():
            return False
        try:
            bin_dir = self._resolve_bin_dir()
            pg_ctl_exe = _exe_name(bin_dir, "pg_ctl")
        except PostgresBinariesNotFoundError:
            return False

        res = subprocess.run(
            [pg_ctl_exe, "-D", str(pgdata), "status"],
            capture_output=True,
            text=True,
            timeout=10,
            **_subprocess_kwargs(),
        )
        return res.returncode == 0

    def _wait_ready(self, port: int, timeout: float = 20.0) -> None:
        import psycopg

        deadline = time.monotonic() + timeout
        last_err: Optional[Exception] = None
        while time.monotonic() < deadline:
            try:
                with psycopg.connect(
                    host=self.host,
                    port=port,
                    user=self._user,
                    password=self.password,
                    dbname="postgres",
                    connect_timeout=2,
                ) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")
                return
            except Exception as exc:
                last_err = exc
                time.sleep(0.25)
        raise PortablePostgresError(
            f"PostgreSQL portátil não respondeu na porta {port} após {timeout}s: {last_err}"
        )

    def _ensure_schema(self, port: int) -> None:
        import psycopg

        with psycopg.connect(
            host=self.host,
            port=port,
            user=self._user,
            password=self.password,
            dbname="postgres",
            autocommit=True,
            connect_timeout=5,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (self._database,),
                )
                if cur.fetchone() is None:
                    cur.execute(f'CREATE DATABASE "{self._database}"')

        statements = _load_init_sql_statements()
        with psycopg.connect(
            host=self.host,
            port=port,
            user=self._user,
            password=self.password,
            dbname=self._database,
            autocommit=True,
            connect_timeout=5,
        ) as conn:
            with conn.cursor() as cur:
                for stmt in statements:
                    cur.execute(stmt)
                cur.execute("CREATE EXTENSION IF NOT EXISTS unaccent SCHEMA dou_inlabs")

    def _read_running_port(self, pgdata: Path) -> Optional[int]:
        pid_file = pgdata / "postmaster.pid"
        if pid_file.is_file():
            try:
                lines = pid_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                if len(lines) >= 4 and lines[3].strip().isdigit():
                    return int(lines[3].strip())
            except OSError:
                pass
        cfg = _read_pg_config_sqlite(self._resolve_db_path())
        if cfg and cfg.get("port"):
            return int(cfg["port"])
        return None

    def start(self, preferred_port: Optional[int] = None) -> int:
        """Inicializa (se necessário) e inicia o PostgreSQL portátil em `127.0.0.1`."""
        with self._lock:
            pgdata = self._resolve_pgdata_dir(create=True)
            if self.is_running():
                if self._port is None:
                    recovered = self._read_running_port(pgdata)
                    if recovered is not None:
                        self._wait_ready(recovered)
                        self._ensure_schema(recovered)
                        self._port = recovered
                if self._port is not None:
                    return self._port

            bin_dir = self._resolve_bin_dir()
            self._ensure_initialized(bin_dir, pgdata)

            port = find_free_port(preferred_port or self._preferred_port, host=self.host)
            pg_ctl_exe = _exe_name(bin_dir, "pg_ctl")
            log_file = get_logs_dir(create=True) / "postgresql.log"

            pg_opts = f"-h {self.host} -p {port}"
            if os.name != "nt":
                pg_opts += f" -k {shlex.quote(str(pgdata))}"

            cmd = [
                pg_ctl_exe,
                "-D",
                str(pgdata),
                "-l",
                str(log_file),
                "-w",
                "-t",
                "30",
                "-o",
                pg_opts,
                "start",
            ]
            logger.info("Iniciando PostgreSQL portátil em %s:%d...", self.host, port)
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=45,
                **_subprocess_kwargs(),
            )
            if res.returncode != 0:
                raise PortablePostgresError(
                    f"Falha ao iniciar PostgreSQL portátil (exit={res.returncode}): "
                    f"{res.stderr.strip() or res.stdout.strip()}"
                )

            self._port = port
            self._started_by_us = True
            self._wait_ready(port)
            self._ensure_schema(port)
            self._persist_port(port)
            logger.info("PostgreSQL portátil pronto em %s:%d (db=%s).", self.host, port, self._database)
            return port

    def stop(self, timeout: int = 15) -> None:
        """Encerra o PostgreSQL portátil se estiver em execução."""
        with self._lock:
            pgdata = self._resolve_pgdata_dir(create=False)
            if not (pgdata / "postmaster.pid").is_file():
                self._port = None
                return
            try:
                bin_dir = self._resolve_bin_dir()
                pg_ctl_exe = _exe_name(bin_dir, "pg_ctl")
            except PostgresBinariesNotFoundError:
                return

            cmd = [
                pg_ctl_exe,
                "-D",
                str(pgdata),
                "-m",
                "fast",
                "-w",
                "-t",
                str(timeout),
                "stop",
            ]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 10,
                **_subprocess_kwargs(),
            )
            if res.returncode == 0:
                logger.info("PostgreSQL portátil encerrado.")
            else:
                logger.warning(
                    "Aviso ao parar PostgreSQL portátil (exit=%d): %s",
                    res.returncode,
                    res.stderr.strip() or res.stdout.strip(),
                )
            self._port = None
            self._started_by_us = False

    def get_connection_info(self) -> Optional[Dict[str, Any]]:
        """Retorna os parâmetros de conexão se o Postgres portátil estiver configurado."""
        port = self._port
        if port is None:
            cfg = _read_pg_config_sqlite(self._resolve_db_path())
            if cfg and cfg.get("port"):
                port = int(cfg["port"])
        if port is None:
            return None
        return {
            "host": self.host,
            "port": port,
            "user": self._user,
            "password": self.password,
            "database": self._database,
        }

    def get_sqlalchemy_url(self, driver: str = "psycopg") -> Optional[str]:
        """Monta a URL SQLAlchemy para o PostgreSQL portátil."""
        info = self.get_connection_info()
        if not info:
            return None
        user = quote_plus(info["user"])
        password = quote_plus(info["password"])
        return (
            f"postgresql+{driver}://{user}:{password}@"
            f"{info['host']}:{info['port']}/{info['database']}"
        )


_PG_LOCK = threading.Lock()
_PG_INSTANCE: Optional[PortablePostgres] = None


def get_portable_postgres() -> PortablePostgres:
    """Retorna o singleton de `PortablePostgres`."""
    global _PG_INSTANCE
    with _PG_LOCK:
        if _PG_INSTANCE is None:
            _PG_INSTANCE = PortablePostgres()
        return _PG_INSTANCE


def reset_portable_postgres_for_tests() -> None:
    """Reseta o singleton global (uso exclusivo em testes)."""
    global _PG_INSTANCE
    with _PG_LOCK:
        _PG_INSTANCE = None


def start_portable_postgres(preferred_port: int = _DEFAULT_PORT) -> Optional[int]:
    """Inicia o Postgres portátil no modo local; retorna None se os binários não existirem."""
    pg = get_portable_postgres()
    try:
        return pg.start(preferred_port=preferred_port)
    except PostgresBinariesNotFoundError as exc:
        logger.warning("PostgreSQL portátil indisponível: %s", exc)
        return None
    except Exception as exc:
        logger.error("Erro ao iniciar PostgreSQL portátil: %s", exc)
        return None


def stop_portable_postgres() -> None:
    """Encerra o Postgres portátil se ativo."""
    with _PG_LOCK:
        inst = _PG_INSTANCE
    if inst is not None:
        inst.stop()
