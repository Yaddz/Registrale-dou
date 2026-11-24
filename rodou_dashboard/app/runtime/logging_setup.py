"""Configuração de logs com rotação e logs individuais por execução."""

from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import threading
from typing import Any, Dict, Iterator, List, Optional

from .paths import get_logs_dir, get_run_logs_dir

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_CONFIGURED_LOG_FILE: Optional[Path] = None
_CONFIG_LOCK = threading.Lock()
_BRASILIA_TZ = timezone(timedelta(hours=-3))


class _ThreadFilter(logging.Filter):
    """Restringe o handler aos registros emitidos pela thread da execução."""

    def __init__(self, thread_id: int) -> None:
        super().__init__()
        self._thread_id = thread_id

    def filter(self, record: logging.LogRecord) -> bool:
        return record.thread == self._thread_id


def sanitize_run_id(run_id: str) -> str:
    """Normaliza um `run_id` para nome seguro de arquivo sem caracteres inválidos no Windows."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(run_id or "run")).strip("._")
    return cleaned or "run"


def configure_logging(
    logs_dir: Optional[Path] = None,
    level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
) -> Path:
    """Configura `logs/registrale.log` com rotação automática no logger raiz."""
    global _CONFIGURED_LOG_FILE

    target_dir = Path(logs_dir) if logs_dir is not None else get_logs_dir(create=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    log_file = (target_dir / "registrale.log").resolve()

    with _CONFIG_LOCK:
        root = logging.getLogger()
        if root.level == logging.NOTSET or root.level > level:
            root.setLevel(level)

        if _CONFIGURED_LOG_FILE == log_file:
            return log_file

        # Remove handler anterior configurado por este módulo, se houver
        for handler in list(root.handlers):
            if getattr(handler, "_registrale_main_log", False):
                root.removeHandler(handler)
                try:
                    handler.close()
                except Exception:
                    pass

        formatter = logging.Formatter(_LOG_FORMAT)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler._registrale_main_log = True  # type: ignore[attr-defined]
        root.addHandler(file_handler)

        if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in root.handlers):
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(level)
            stream_handler.setFormatter(formatter)
            root.addHandler(stream_handler)

        _CONFIGURED_LOG_FILE = log_file

    return log_file


@contextmanager
def run_log_context(
    run_id: str,
    run_logs_dir: Optional[Path] = None,
) -> Iterator[Path]:
    """Captura os logs da thread atual em `logs/runs/<run_id>.log` durante uma execução."""
    target_dir = Path(run_logs_dir) if run_logs_dir is not None else get_run_logs_dir(create=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    log_file = target_dir / f"{sanitize_run_id(run_id)}.log"

    handler = RotatingFileHandler(
        log_file,
        maxBytes=2 * 1024 * 1024,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    handler.addFilter(_ThreadFilter(threading.get_ident()))

    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield log_file
    finally:
        root.removeHandler(handler)
        try:
            handler.flush()
            handler.close()
        except Exception:
            pass


def list_log_files(logs_dir: Optional[Path] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Lista `registrale.log` e os logs recentes em `runs/` ordenados por data de modificação."""
    base_dir = (Path(logs_dir) if logs_dir is not None else get_logs_dir(create=False)).resolve()
    if not base_dir.exists():
        return []

    entries: List[Dict[str, Any]] = []
    main_log = base_dir / "registrale.log"
    if main_log.is_file():
        stat = main_log.stat()
        entries.append(
            {
                "name": "registrale.log",
                "path": "registrale.log",
                "kind": "app",
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime, _BRASILIA_TZ).strftime("%d/%m/%Y %H:%M:%S"),
                "mtime_ts": stat.st_mtime,
            }
        )

    runs_dir = base_dir / "runs"
    if runs_dir.is_dir():
        run_files = sorted(
            (p for p in runs_dir.glob("*.log") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]
        for p in run_files:
            stat = p.stat()
            entries.append(
                {
                    "name": p.name,
                    "path": f"runs/{p.name}",
                    "kind": "run",
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime, _BRASILIA_TZ).strftime("%d/%m/%Y %H:%M:%S"),
                    "mtime_ts": stat.st_mtime,
                }
            )

    return entries


def read_log_tail(
    rel_path: str = "registrale.log",
    lines: int = 200,
    logs_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Lê as últimas `lines` linhas de um arquivo de log dentro de `logs_dir`."""
    base_dir = (Path(logs_dir) if logs_dir is not None else get_logs_dir(create=False)).resolve()
    requested = (rel_path or "registrale.log").strip().replace("\\", "/")
    if not requested or requested.startswith("/") or ".." in requested.split("/"):
        raise ValueError("Caminho de log inválido.")

    target = (base_dir / requested).resolve()
    if not target.is_relative_to(base_dir):
        raise ValueError("Caminho de log fora do diretório permitido.")
    if not target.is_file():
        return {"path": requested, "exists": False, "content": "", "lines": 0}

    max_lines = max(1, min(int(lines or 200), 2000))
    tail_deque: deque[str] = deque(maxlen=max_lines)
    total_lines = 0
    with open(target, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            total_lines += 1
            tail_deque.append(line)

    tail = list(tail_deque)
    return {
        "path": requested,
        "exists": True,
        "content": "".join(tail),
        "lines": len(tail),
        "total_lines": total_lines,
    }
