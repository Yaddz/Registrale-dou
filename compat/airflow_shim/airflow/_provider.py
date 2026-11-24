"""Provedor interno de variáveis e conexões para o shim do Airflow."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse


@dataclass
class Connection:
    """Representa uma conexão compatível com ``airflow.sdk.bases.hook.BaseHook``."""

    conn_id: str = ""
    conn_type: str = ""
    host: str | None = None
    login: str | None = None
    password: str | None = None
    port: int | None = None
    schema: str | None = None
    extra: str | dict[str, Any] | None = None

    @property
    def extra_dejson(self) -> dict[str, Any]:
        """Retorna ``extra`` desserializado como dicionário."""
        if not self.extra:
            return {}
        if isinstance(self.extra, dict):
            return dict(self.extra)
        if isinstance(self.extra, str):
            parsed = json.loads(self.extra)
            if isinstance(parsed, dict):
                return parsed
        return {}


VariableProvider = Callable[[str], tuple[bool, Any]]
ConnectionProvider = Callable[[str], Connection | None]

_variables: dict[str, Any] = {}
_connections: dict[str, Connection] = {}
_variable_provider: VariableProvider | None = None
_connection_provider: ConnectionProvider | None = None


def set_variables(mapping: dict[str, Any]) -> None:
    """Define variáveis em memória para o shim (útil em testes)."""
    _variables.clear()
    _variables.update(mapping)


def set_connections(mapping: dict[str, Connection]) -> None:
    """Define conexões em memória para o shim (útil em testes)."""
    _connections.clear()
    _connections.update(mapping)


def set_variable_provider(provider: VariableProvider | None) -> None:
    """Registra um provedor dinâmico de variáveis (ex.: leitura do SQLite)."""
    global _variable_provider
    _variable_provider = provider


def set_connection_provider(provider: ConnectionProvider | None) -> None:
    """Registra um provedor dinâmico de conexões (ex.: leitura do SQLite)."""
    global _connection_provider
    _connection_provider = provider


def clear_providers() -> None:
    """Limpa variáveis, conexões e provedores registrados."""
    global _variable_provider, _connection_provider
    _variables.clear()
    _connections.clear()
    _variable_provider = None
    _connection_provider = None


def _read_sqlite_setting(key: str) -> tuple[bool, Any]:
    """Lê chave da tabela ``settings`` do SQLite se ``REGISTRALE_DB_PATH`` estiver definido."""
    db_path = os.getenv("REGISTRALE_DB_PATH") or os.getenv("RODOU_DB_PATH")
    if not db_path or not Path(db_path).is_file():
        return False, None
    try:
        db_uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(db_uri, uri=True)
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            if row is not None:
                return True, row[0]
        finally:
            conn.close()
    except sqlite3.Error:
        return False, None
    return False, None


def resolve_variable(key: str) -> tuple[bool, Any]:
    """Resolve uma variável na ordem: memória -> provedor -> SQLite -> env AIRFLOW_VAR_*."""
    if key in _variables:
        return True, _variables[key]
    if _variable_provider is not None:
        found, value = _variable_provider(key)
        if found:
            return True, value
    found_db, db_val = _read_sqlite_setting(key)
    if found_db:
        return True, db_val
    env_key = f"AIRFLOW_VAR_{key.upper()}"
    if env_key in os.environ:
        return True, os.environ[env_key]
    return False, None


def _resolve_builtin_connection(conn_id: str) -> Connection | None:
    """Resolve `inlabs_portal` e `inlabs_db` a partir do SQLite e/ou Postgres portátil."""
    if conn_id == "inlabs_portal":
        host = os.getenv("INLABS_PORTAL_URL", "https://inlabs.in.gov.br/")
        found, raw_settings = _read_sqlite_setting("global_settings")
        login = None
        password = None
        if found and raw_settings:
            try:
                parsed = (
                    json.loads(raw_settings)
                    if isinstance(raw_settings, str)
                    else raw_settings
                )
                if isinstance(parsed, dict):
                    inlabs_cfg = parsed.get("inlabs") or {}
                    if isinstance(inlabs_cfg, dict):
                        login = inlabs_cfg.get("user") or None
                        password = inlabs_cfg.get("password") or None
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        if login or password:
            return Connection(
                conn_id="inlabs_portal",
                conn_type="http",
                host=host,
                login=login,
                password=password,
            )
        return None

    if conn_id == "inlabs_db":
        db_url = os.getenv("INLABS_DB_URL")
        if db_url:
            parsed = urlparse(db_url)
            return Connection(
                conn_id="inlabs_db",
                conn_type="postgres",
                host=parsed.hostname or "127.0.0.1",
                port=parsed.port or 5432,
                schema=(parsed.path or "").lstrip("/") or "inlabs",
                login=unquote(parsed.username or "") or None,
                password=unquote(parsed.password or "") or None,
            )

        try:
            from rodou_dashboard.app.runtime.pg_portable import get_portable_postgres

            info = get_portable_postgres().get_connection_info()
            if info and info.get("port"):
                return Connection(
                    conn_id="inlabs_db",
                    conn_type="postgres",
                    host=info.get("host", "127.0.0.1"),
                    port=int(info["port"]),
                    schema=info.get("database", "inlabs"),
                    login=info.get("user", "postgres"),
                    password=info.get("password"),
                )
        except Exception:
            pass

        found, raw_pg = _read_sqlite_setting("inlabs_pg_config")
        if found and raw_pg:
            try:
                cfg = json.loads(raw_pg) if isinstance(raw_pg, str) else raw_pg
                if isinstance(cfg, dict) and cfg.get("port"):
                    return Connection(
                        conn_id="inlabs_db",
                        conn_type="postgres",
                        host="127.0.0.1",
                        port=int(cfg["port"]),
                        schema=cfg.get("database", "inlabs"),
                        login=cfg.get("user", "postgres"),
                        password=cfg.get("password"),
                    )
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        return None

    return None


def resolve_connection(conn_id: str) -> Connection | None:
    """Resolve uma conexão na ordem: memória -> provedor -> configurações locais."""
    if conn_id in _connections:
        return _connections[conn_id]
    if _connection_provider is not None:
        conn = _connection_provider(conn_id)
        if conn is not None:
            return conn
    return _resolve_builtin_connection(conn_id)
