"""Assistente de primeira execução: importa dados do modo Docker para o modo local.

Importa `database.db` (empresas, menções, configurações, templates de e-mail,
histórico e usuários) e rotinas YAML de `dag_confs/`, sempre criando backup
do banco de destino antes de alterar qualquer registro.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import shutil
import sqlite3
from typing import Any

from .paths import get_base_dir, get_data_dir, get_db_path, get_routines_dir

logger = logging.getLogger(__name__)

_TZ_BRT = timezone(timedelta(hours=-3))


def _timestamp() -> str:
    return datetime.now(_TZ_BRT).strftime("%Y%m%d-%H%M%S")


def backup_database(db_path: Path | None = None, backup_dir: Path | None = None) -> Path | None:
    """Cria cópia de segurança do SQLite atual antes da importação."""
    target = Path(db_path) if db_path else get_db_path()
    if not target.is_file() or target.stat().st_size == 0:
        return None
    dest_dir = Path(backup_dir) if backup_dir else (get_data_dir(create=True) / "backups")
    dest_dir.mkdir(parents=True, exist_ok=True)
    backup_path = dest_dir / f"database.db.bak-{_timestamp()}"
    # Usa API de backup do sqlite3 para consistência mesmo em modo WAL
    src_conn = sqlite3.connect(str(target))
    try:
        dst_conn = sqlite3.connect(str(backup_path))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()
    logger.info("Backup do banco criado em %s", backup_path)
    return backup_path


def detect_legacy_sources() -> dict[str, Any]:
    """Detecta possíveis arquivos legados (`data/database.db` e `dag_confs/`) no workspace."""
    base_dir = get_base_dir()
    current_db = get_db_path().resolve()
    current_routines = get_routines_dir(create=False).resolve()

    legacy_db = (base_dir / "data" / "database.db").resolve()
    has_legacy_db = legacy_db.is_file() and legacy_db != current_db and legacy_db.stat().st_size > 0

    legacy_routines = (base_dir / "dag_confs").resolve()
    routine_files: list[str] = []
    if legacy_routines.is_dir() and legacy_routines != current_routines:
        for item in sorted(legacy_routines.iterdir()):
            if not item.is_file():
                continue
            low = item.name.lower()
            if not low.endswith((".yaml", ".yml")):
                continue
            if low.startswith("temp_") or "_part_" in low or "_sync" in low:
                continue
            routine_files.append(item.name)

    return {
        "legacy_db_path": str(legacy_db) if has_legacy_db else None,
        "legacy_routines_dir": str(legacy_routines) if routine_files else None,
        "legacy_routine_files": routine_files,
    }


def _read_source_tables(src_conn: sqlite3.Connection) -> set[str]:
    rows = src_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table';"
    ).fetchall()
    return {r[0] for r in rows}


def _get_table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table});").fetchall()]


def import_routines_from_dir(
    source_dir: Path,
    target_dir: Path | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Importa rotinas `.yaml`/`.yml` válidas de `source_dir` para o diretório de rotinas local."""
    src = Path(source_dir).expanduser().resolve()
    if not src.is_dir():
        raise FileNotFoundError(f"Diretório de rotinas não encontrado: {src}")

    dst = Path(target_dir) if target_dir else get_routines_dir(create=True)
    dst.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    skipped: list[str] = []
    for item in sorted(src.iterdir()):
        if not item.is_file():
            continue
        low = item.name.lower()
        if not low.endswith((".yaml", ".yml")):
            continue
        if low.startswith("temp_") or "_part_" in low or "_sync" in low:
            continue
        dest_file = dst / item.name
        if dest_file.exists() and not overwrite:
            skipped.append(item.name)
            continue
        shutil.copy2(item, dest_file)
        copied.append(item.name)

    return {"copied": copied, "skipped": skipped, "target_dir": str(dst)}


def import_docker_database(
    source_db_path: Path,
    target_db_path: Path | None = None,
    overwrite_existing: bool = False,
) -> dict[str, Any]:
    """Importa dados de um `database.db` existente para o banco local, fazendo backup antes."""
    src_path = Path(source_db_path).expanduser().resolve()
    if not src_path.is_file():
        raise FileNotFoundError(f"Banco de origem não encontrado: {src_path}")

    dst_path = Path(target_db_path).resolve() if target_db_path else get_db_path().resolve()
    if src_path == dst_path:
        raise ValueError("O banco de origem e o banco de destino são o mesmo arquivo.")

    backup_path = backup_database(dst_path)

    src_conn = sqlite3.connect(f"{src_path.as_uri()}?mode=ro", uri=True)
    src_conn.row_factory = sqlite3.Row
    dst_conn = sqlite3.connect(str(dst_path))
    dst_conn.row_factory = sqlite3.Row

    stats: dict[str, int] = {
        "companies": 0,
        "mentions": 0,
        "settings": 0,
        "email_templates": 0,
        "sync_history": 0,
        "users": 0,
        "inlabs_download_log": 0,
    }

    try:
        src_tables = _read_source_tables(src_conn)
        dst_tables = _read_source_tables(dst_conn)
        expected = {"companies", "mentions", "settings"}
        if not (src_tables & expected):
            raise ValueError(
                "O arquivo selecionado não parece ser um banco válido do Registrale-DOU."
            )

        with dst_conn:
            # 1. Companies (chave única: cnpj_norm)
            if "companies" in src_tables and "companies" in dst_tables:
                for row in src_conn.execute(
                    "SELECT nome, cnpj, cnpj_norm, origem, status FROM companies;"
                ):
                    exists = dst_conn.execute(
                        "SELECT id FROM companies WHERE cnpj_norm = ?;", (row["cnpj_norm"],)
                    ).fetchone()
                    if exists:
                        if overwrite_existing:
                            dst_conn.execute(
                                "UPDATE companies SET nome = ?, cnpj = ?, origem = ?, status = ? "
                                "WHERE cnpj_norm = ?;",
                                (
                                    row["nome"],
                                    row["cnpj"],
                                    row["origem"],
                                    row["status"],
                                    row["cnpj_norm"],
                                ),
                            )
                            stats["companies"] += 1
                    else:
                        dst_conn.execute(
                            "INSERT INTO companies (nome, cnpj, cnpj_norm, origem, status) "
                            "VALUES (?, ?, ?, ?, ?);",
                            (
                                row["nome"],
                                row["cnpj"],
                                row["cnpj_norm"],
                                row["origem"],
                                row["status"],
                            ),
                        )
                        stats["companies"] += 1

            # 2. Mentions (chave primária: id)
            if "mentions" in src_tables and "mentions" in dst_tables:
                src_cols = set(_get_table_columns(src_conn, "mentions"))
                has_pdf = "pdf_path" in src_cols
                select_cols = (
                    "id, empresa, cnpj, cnpj_norm, secao, data, detected_at, trecho, link"
                    + (", pdf_path" if has_pdf else "")
                )
                for row in src_conn.execute(f"SELECT {select_cols} FROM mentions;"):
                    exists = dst_conn.execute(
                        "SELECT id FROM mentions WHERE id = ?;", (row["id"],)
                    ).fetchone()
                    if exists:
                        continue
                    pdf_val = row["pdf_path"] if has_pdf else None
                    dst_conn.execute(
                        "INSERT INTO mentions "
                        "(id, empresa, cnpj, cnpj_norm, secao, data, detected_at, trecho, link, pdf_path) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                        (
                            row["id"],
                            row["empresa"],
                            row["cnpj"],
                            row["cnpj_norm"],
                            row["secao"],
                            row["data"],
                            row["detected_at"],
                            row["trecho"],
                            row["link"],
                            pdf_val,
                        ),
                    )
                    stats["mentions"] += 1

            # 3. Settings (chave única: key)
            if "settings" in src_tables and "settings" in dst_tables:
                for row in src_conn.execute("SELECT key, value FROM settings;"):
                    if row["key"] in ("inlabs_pg_config", "first_run_import_done"):
                        continue
                    exists = dst_conn.execute(
                        "SELECT id FROM settings WHERE key = ?;", (row["key"],)
                    ).fetchone()
                    if exists:
                        if overwrite_existing or row["key"] == "global_settings":
                            dst_conn.execute(
                                "UPDATE settings SET value = ? WHERE key = ?;",
                                (row["value"], row["key"]),
                            )
                            stats["settings"] += 1
                    else:
                        dst_conn.execute(
                            "INSERT INTO settings (key, value) VALUES (?, ?);",
                            (row["key"], row["value"]),
                        )
                        stats["settings"] += 1

            # 4. EmailTemplates (chave única: name)
            if "email_templates" in src_tables and "email_templates" in dst_tables:
                for row in src_conn.execute(
                    "SELECT name, subject, body_html FROM email_templates;"
                ):
                    exists = dst_conn.execute(
                        "SELECT id FROM email_templates WHERE name = ?;", (row["name"],)
                    ).fetchone()
                    if exists:
                        if overwrite_existing:
                            dst_conn.execute(
                                "UPDATE email_templates SET subject = ?, body_html = ? WHERE name = ?;",
                                (row["subject"], row["body_html"], row["name"]),
                            )
                            stats["email_templates"] += 1
                    else:
                        dst_conn.execute(
                            "INSERT INTO email_templates (name, subject, body_html) VALUES (?, ?, ?);",
                            (row["name"], row["subject"], row["body_html"]),
                        )
                        stats["email_templates"] += 1

            # 5. SyncHistory
            if "sync_history" in src_tables and "sync_history" in dst_tables:
                for row in src_conn.execute(
                    "SELECT data, evento, detalhes FROM sync_history ORDER BY id ASC;"
                ):
                    exists = dst_conn.execute(
                        "SELECT id FROM sync_history WHERE data = ? AND evento = ?;",
                        (row["data"], row["evento"]),
                    ).fetchone()
                    if not exists:
                        dst_conn.execute(
                            "INSERT INTO sync_history (data, evento, detalhes) VALUES (?, ?, ?);",
                            (row["data"], row["evento"], row["detalhes"]),
                        )
                        stats["sync_history"] += 1

            # 6. Users (chave única: username)
            if "users" in src_tables and "users" in dst_tables:
                for row in src_conn.execute(
                    "SELECT username, password_hash, role FROM users;"
                ):
                    exists = dst_conn.execute(
                        "SELECT id FROM users WHERE username = ?;", (row["username"],)
                    ).fetchone()
                    if exists:
                        if overwrite_existing:
                            dst_conn.execute(
                                "UPDATE users SET password_hash = ?, role = ? WHERE username = ?;",
                                (row["password_hash"], row["role"], row["username"]),
                            )
                            stats["users"] += 1
                    else:
                        dst_conn.execute(
                            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?);",
                            (row["username"], row["password_hash"], row["role"]),
                        )
                        stats["users"] += 1

            # 7. InlabsDownloadLog (chave única: date_str)
            if "inlabs_download_log" in src_tables and "inlabs_download_log" in dst_tables:
                for row in src_conn.execute(
                    "SELECT date_str, downloaded_at, status FROM inlabs_download_log;"
                ):
                    exists = dst_conn.execute(
                        "SELECT id FROM inlabs_download_log WHERE date_str = ?;",
                        (row["date_str"],),
                    ).fetchone()
                    if not exists:
                        dst_conn.execute(
                            "INSERT INTO inlabs_download_log (date_str, downloaded_at, status) "
                            "VALUES (?, ?, ?);",
                            (row["date_str"], row["downloaded_at"], row["status"]),
                        )
                        stats["inlabs_download_log"] += 1

    finally:
        src_conn.close()
        dst_conn.close()

    return {
        "backup_path": str(backup_path) if backup_path else None,
        "imported": stats,
    }
