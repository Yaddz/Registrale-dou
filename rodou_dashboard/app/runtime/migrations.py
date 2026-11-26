"""Migrações versionadas do banco SQLite (`schema_version`)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Callable

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_TZ_BRT = timezone(timedelta(hours=-3))


def _mig_001_baseline_indexes_and_pdf_path(conn) -> None:
    """Garante coluna `mentions.pdf_path` e índices principais em `mentions` e `companies`."""
    tables = {
        row[0]
        for row in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table';")
        ).fetchall()
    }
    if "mentions" in tables:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(mentions);")).fetchall()]
        if "pdf_path" not in cols:
            conn.execute(text("ALTER TABLE mentions ADD COLUMN pdf_path TEXT;"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_mentions_cnpj_norm ON mentions (cnpj_norm);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_mentions_data ON mentions (data);"))

    if "companies" in tables:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_companies_status ON companies (status);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_companies_origem ON companies (origem);"))


def _mig_002_job_runs_indexes(conn) -> None:
    """Garante índices da tabela `job_runs` usada pelo executor local."""
    tables = {
        row[0]
        for row in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table';")
        ).fetchall()
    }
    if "job_runs" in tables:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_job_runs_rotina ON job_runs (rotina);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_job_runs_data ON job_runs (data);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_job_runs_status ON job_runs (status);"))


def _mig_003_mentions_highlight_pdf_path(conn) -> None:
    """Garante coluna `mentions.highlight_pdf_path` para a página destacada do DOU."""
    tables = {
        row[0]
        for row in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table';")
        ).fetchall()
    }
    if "mentions" in tables:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(mentions);")).fetchall()]
        if "highlight_pdf_path" not in cols:
            conn.execute(text("ALTER TABLE mentions ADD COLUMN highlight_pdf_path TEXT;"))


MIGRATIONS: list[tuple[int, str, Callable]] = [
    (1, "baseline_indexes_and_pdf_path", _mig_001_baseline_indexes_and_pdf_path),
    (2, "job_runs_indexes", _mig_002_job_runs_indexes),
    (3, "mentions_highlight_pdf_path", _mig_003_mentions_highlight_pdf_path),
]


def _ensure_schema_version_table(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
            """
        )
    )


def get_schema_version(engine: Engine) -> int:
    """Retorna a maior versão de schema aplicada no banco (0 se nenhuma)."""
    with engine.begin() as conn:
        _ensure_schema_version_table(conn)
        row = conn.execute(text("SELECT COALESCE(MAX(version), 0) FROM schema_version;")).fetchone()
        return int(row[0]) if row else 0


def apply_migrations(engine: Engine) -> list[int]:
    """Aplica todas as migrações pendentes em ordem e retorna os IDs aplicados."""
    applied_now: list[int] = []
    with engine.begin() as conn:
        _ensure_schema_version_table(conn)
        existing = {
            int(row[0])
            for row in conn.execute(text("SELECT version FROM schema_version;")).fetchall()
        }
        for ver, name, fn in MIGRATIONS:
            if ver in existing:
                continue
            logger.info("Aplicando migração de banco v%d (%s)...", ver, name)
            fn(conn)
            now_str = datetime.now(_TZ_BRT).isoformat()
            conn.execute(
                text(
                    "INSERT INTO schema_version (version, name, applied_at) "
                    "VALUES (:version, :name, :applied_at);"
                ),
                {"version": ver, "name": name, "applied_at": now_str},
            )
            applied_now.append(ver)
    return applied_now
