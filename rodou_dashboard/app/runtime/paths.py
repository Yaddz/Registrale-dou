"""Resolução de diretórios por plataforma e variáveis de ambiente.

Os dados persistentes ficam no diretório de dados do usuário
(`platformdirs.user_data_dir("Registrale", appauthor=False)` — no Windows,
`%LOCALAPPDATA%\\Registrale`), a menos que sobrescritos por variáveis de ambiente.
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


def get_data_dir(create: bool = True) -> Path:
    """Retorna o diretório de dados persistentes (`database.db`, `logs/`, `rotinas/`, etc.)."""
    env_dir = os.getenv("REGISTRALE_DATA_DIR") or os.getenv("DATA_DIR")
    if env_dir:
        path = Path(env_dir).expanduser().resolve()
    else:
        path = _default_local_user_data_dir()

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
    else:
        path = get_data_dir(create=create) / "logs"

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


_EMPTY_MAIN_ROUTINE_YAML = """dag:
  id: pesquisa_cnpj_anvisa
  description: Busca padrão diária vinculada às empresas com monitoramento ativo.
  tags:
    - pesquisa_cnpj
    - inlabs
  owner:
    - CNPJ_SYNC
  schedule: 0 8 * * MON-FRI
  active: true
  is_paused: false
  dataset: inlabs
  search:
    - header: MONITORAMENTO PADRÃO
      is_exact_search: false
      force_rematch: true
      field: TUDO
      department: []
      dou_sections:
        - SECAO_1
        - SECAO_2
        - SECAO_3
        - EDICAO_EXTRA
      terms_ignore: []
      terms: []
  report:
    title: MONITORAMENTO PADRÃO
    subject: ""
    skip_null: true
    emails: []
"""


def _seed_routines_if_empty(target_dir: Path) -> None:
    """Inicializa `rotinas/` na primeira execução com a rotina principal vazia (sem CNPJs de clientes)."""
    if any(target_dir.glob("*.y*ml")):
        return
    source_dir = get_base_dir() / "dag_confs"
    if source_dir.is_dir():
        for item in sorted(source_dir.iterdir()):
            if not item.is_file():
                continue
            name_lower = item.name.lower()
            if not name_lower.endswith((".yaml", ".yml")):
                continue
            if (
                name_lower.startswith("pesquisa_cnpj")
                or name_lower.startswith("temp_")
                or "_part_" in name_lower
                or "_sync" in name_lower
            ):
                continue
            dest = target_dir / item.name
            if not dest.exists():
                try:
                    shutil.copy2(item, dest)
                except Exception:
                    pass

    main_dest = target_dir / "Pesquisa_cnpj.yaml"
    if not main_dest.exists():
        try:
            main_dest.write_text(_EMPTY_MAIN_ROUTINE_YAML, encoding="utf-8")
        except Exception:
            pass


def get_routines_dir(create: bool = True) -> Path:
    """Retorna o diretório de rotinas YAML (`rotinas/`)."""
    env_dir = os.getenv("REGISTRALE_ROUTINES_DIR") or os.getenv("DAG_CONFS_DIR")
    if env_dir:
        path = Path(env_dir).expanduser().resolve()
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    path = get_data_dir(create=create) / "rotinas"
    if create:
        path.mkdir(parents=True, exist_ok=True)
        _seed_routines_if_empty(path)
    return path


def get_sessions_dir(create: bool = True) -> Path:
    """Retorna o diretório de sessões do Flask-Session."""
    env_dir = os.getenv("SESSION_FILE_DIR")
    if env_dir:
        path = Path(env_dir).expanduser().resolve()
    else:
        path = get_data_dir(create=create) / "flask_sessions"

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
