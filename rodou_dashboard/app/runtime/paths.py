"""Resolução de diretórios por plataforma e variáveis de ambiente.

No modo `local`, os dados persistentes ficam no diretório de dados do usuário
(`platformdirs.user_data_dir("Registrale", appauthor=False)` — no Windows,
`%LOCALAPPDATA%\\Registrale`), a menos que sobrescritos por variáveis de ambiente.
No modo `airflow` (Docker), preserva o comportamento legado (`/data`, `BASE_DIR/data`,
`BASE_DIR/dag_confs`, `BASE_DIR/mnt/airflow-logs`).
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil


def _default_local_user_data_dir() -> Path:
    try:
        from platformdirs import user_data_dir

        return Path(user_data_dir("Registrale", appauthor=False)).resolve()
    except ImportError:
        if os.name == "nt":
            base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            return (Path(base) / "Registrale").resolve()
        return (Path.home() / ".local" / "share" / "Registrale").resolve()


def get_base_dir() -> Path:
    """Retorna a raiz do repositório/aplicação."""
    return Path(__file__).resolve().parents[3]


def _is_local_mode() -> bool:
    return os.getenv("REGISTRALE_EXECUTOR", "airflow").strip().lower() == "local"


def get_data_dir(create: bool = True) -> Path:
    """Retorna o diretório de dados persistentes (`database.db`, `logs/`, `rotinas/`, etc.)."""
    env_dir = os.getenv("REGISTRALE_DATA_DIR")
    if not env_dir and _is_local_mode():
        env_dir = os.getenv("DATA_DIR")
    if env_dir:
        path = Path(env_dir).expanduser().resolve()
    elif _is_local_mode():
        path = _default_local_user_data_dir()
    else:
        path = get_base_dir() / "data"

    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def get_db_path() -> Path:
    """Retorna o caminho do banco SQLite principal (`database.db`)."""
    env_db = os.getenv("REGISTRALE_DB_PATH")
    if env_db:
        path = Path(env_db).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return get_data_dir(create=True) / "database.db"


def get_scheduler_db_path() -> Path:
    """Retorna o caminho do banco SQLite usado pelo jobstore do APScheduler."""
    env_db = os.getenv("REGISTRALE_SCHEDULER_DB_PATH")
    if env_db:
        path = Path(env_db).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return get_data_dir(create=True) / "scheduler_jobs.db"


def get_logs_dir(create: bool = True) -> Path:
    """Retorna o diretório de logs da aplicação."""
    env_logs = os.getenv("REGISTRALE_LOGS_DIR") or os.getenv("LOGS_DIR")
    if env_logs:
        path = Path(env_logs).expanduser().resolve()
    elif _is_local_mode():
        path = get_data_dir(create=create) / "logs"
    else:
        path = get_base_dir() / "mnt" / "airflow-logs"
        create = False

    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def get_run_logs_dir(create: bool = True) -> Path:
    """Retorna o diretório de logs individuais por execução (`logs/runs/`)."""
    path = get_logs_dir(create=create) / "runs"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def get_inlabs_dir(create: bool = True) -> Path:
    """Retorna o diretório de dados/cache do INLABS."""
    env_inlabs = os.getenv("REGISTRALE_INLABS_DIR")
    if env_inlabs:
        path = Path(env_inlabs).expanduser().resolve()
    else:
        path = get_data_dir(create=create) / "inlabs"

    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _seed_routines_if_empty(target_dir: Path) -> None:
    """Copia rotinas iniciais de `dag_confs/` para `rotinas/` na primeira execução local."""
    if any(target_dir.glob("*.y*ml")):
        return
    source_dir = get_base_dir() / "dag_confs"
    if not source_dir.is_dir():
        return
    for item in sorted(source_dir.iterdir()):
        if not item.is_file():
            continue
        name_lower = item.name.lower()
        if not name_lower.endswith((".yaml", ".yml")):
            continue
        if name_lower.startswith("temp_") or "_part_" in name_lower or "_sync" in name_lower:
            continue
        dest = target_dir / item.name
        if not dest.exists():
            try:
                shutil.copy2(item, dest)
            except Exception:
                pass


def get_routines_dir(create: bool = True) -> Path:
    """Retorna o diretório de rotinas YAML (`rotinas/` no modo local, `dag_confs/` no Docker)."""
    env_dir = os.getenv("REGISTRALE_ROUTINES_DIR") or os.getenv("DAG_CONFS_DIR")
    if env_dir:
        path = Path(env_dir).expanduser().resolve()
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    if _is_local_mode():
        path = get_data_dir(create=create) / "rotinas"
        if create:
            path.mkdir(parents=True, exist_ok=True)
            _seed_routines_if_empty(path)
        return path

    base_dir = get_base_dir()
    candidates = [
        base_dir / "dag_confs",
        Path("dag_confs").resolve(),
        Path("/app/dag_confs"),
        Path("/dag_confs"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate

    default_path = base_dir / "dag_confs"
    if create:
        default_path.mkdir(parents=True, exist_ok=True)
    return default_path


def get_sessions_dir(create: bool = True) -> Path:
    """Retorna o diretório de sessões do Flask-Session."""
    env_dir = os.getenv("SESSION_FILE_DIR")
    if env_dir:
        path = Path(env_dir).expanduser().resolve()
    elif _is_local_mode():
        path = get_data_dir(create=create) / "flask_sessions"
    elif Path("/flask_sessions").exists():
        path = Path("/flask_sessions")
    else:
        path = get_base_dir() / "flask_sessions"

    if create:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception:
            path = get_data_dir(create=True) / "flask_sessions"
            path.mkdir(parents=True, exist_ok=True)
    return path


def get_pgdata_dir(create: bool = True) -> Path:
    """Retorna o diretório de dados do PostgreSQL portátil (`pgdata/`)."""
    env_dir = os.getenv("REGISTRALE_PGDATA_DIR")
    if env_dir:
        path = Path(env_dir).expanduser().resolve()
    else:
        path = get_data_dir(create=create) / "pgdata"

    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def get_pg_bin_dir() -> Path | None:
    """Retorna o diretório de binários do PostgreSQL portátil, se encontrado."""
    env_bin = os.getenv("REGISTRALE_PG_BIN_DIR")
    if env_bin:
        candidate = Path(env_bin).expanduser().resolve()
        if candidate.is_dir():
            return candidate
        return None

    vendor_base = get_base_dir() / "windows" / "vendor" / "pgsql"
    for candidate in (vendor_base / "bin", vendor_base):
        exe = "pg_ctl.exe" if os.name == "nt" else "pg_ctl"
        if (candidate / exe).is_file():
            return candidate

    pg_ctl_in_path = shutil.which("pg_ctl")
    if pg_ctl_in_path:
        return Path(pg_ctl_in_path).resolve().parent

    if os.name != "nt":
        pg_root = Path("/usr/lib/postgresql")
        if pg_root.is_dir():
            for ver_dir in sorted(pg_root.iterdir(), reverse=True):
                bin_dir = ver_dir / "bin"
                if (bin_dir / "pg_ctl").is_file():
                    return bin_dir

    return None


def get_default_pdf_dir(create: bool = False) -> Path:
    """Retorna a pasta padrão para arquivamento dos PDFs integrais do DOU.

    No Windows corresponde a ``Documentos\\Registrale\\DOU``.
    """
    env_dir = os.getenv("REGISTRALE_PDF_DIR")
    if env_dir:
        path = Path(env_dir).expanduser().resolve()
    else:
        try:
            from platformdirs import user_documents_dir

            docs_dir = Path(user_documents_dir())
        except ImportError:
            docs_dir = Path.home() / "Documents"
        path = (docs_dir / "Registrale" / "DOU").resolve()

    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path
