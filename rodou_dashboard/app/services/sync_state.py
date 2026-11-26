"""Estado em memória da sincronização em andamento (GestãoClick e Google Sheets).

Compartilhado entre as rotas do painel, o agendador e os avisos da Visão geral
para evitar sincronizações duplicadas do GestãoClick e detectar execuções travadas.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import threading
from typing import Any, Optional

BRASILIA_TZ = timezone(timedelta(hours=-3))

_sync_state_lock = threading.Lock()
_sync_running = False
_sync_started_at: Optional[datetime] = None
_sheets_sync_running = False
_sheets_sync_started_at: Optional[datetime] = None


def try_start_sync(now: Optional[datetime] = None) -> bool:
    """Marca a sincronização do GestãoClick como ativa; retorna False se já houver uma rodando."""
    global _sync_running, _sync_started_at
    with _sync_state_lock:
        if _sync_running:
            return False
        _sync_running = True
        _sync_started_at = now or datetime.now(BRASILIA_TZ)
        return True


def finish_sync() -> None:
    """Libera o estado de sincronização do GestãoClick."""
    global _sync_running, _sync_started_at
    with _sync_state_lock:
        _sync_running = False
        _sync_started_at = None


def start_sheets_sync(now: Optional[datetime] = None) -> None:
    """Registra início da sincronização do Google Sheets para monitoramento de travamento."""
    global _sheets_sync_running, _sheets_sync_started_at
    with _sync_state_lock:
        _sheets_sync_running = True
        _sheets_sync_started_at = now or datetime.now(BRASILIA_TZ)


def finish_sheets_sync() -> None:
    """Libera o estado de monitoramento da sincronização do Google Sheets."""
    global _sheets_sync_running, _sheets_sync_started_at
    with _sync_state_lock:
        _sheets_sync_running = False
        _sheets_sync_started_at = None


def get_sync_state(now: Optional[datetime] = None) -> dict[str, Any]:
    """Retorna o estado atual da sincronização (`running`, `started_at`, `elapsed_s`)."""
    current = now or datetime.now(BRASILIA_TZ)
    with _sync_state_lock:
        gc_running = bool(_sync_running)
        gc_started = _sync_started_at
        sh_running = bool(_sheets_sync_running)
        sh_started = _sheets_sync_started_at

    started = gc_started if gc_running else (sh_started if sh_running else None)
    elapsed_s: Optional[int] = None
    if started is not None:
        elapsed_s = max(0, int((current - started).total_seconds()))

    return {
        "running": gc_running,
        "sheets_running": sh_running,
        "any_running": gc_running or sh_running,
        "started_at": started.isoformat() if started is not None else None,
        "started_at_dt": started,
        "elapsed_s": elapsed_s,
    }


def reset_sync_state() -> None:
    """Limpa todo o estado em memória (uso em testes)."""
    finish_sync()
    finish_sheets_sync()
