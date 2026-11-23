"""Shim de ``airflow.sdk.bases.hook``."""

from __future__ import annotations

from airflow._provider import Connection, resolve_connection

__all__ = ["BaseHook", "Connection"]


class BaseHook:
    """Implementação local de ``airflow.sdk.bases.hook.BaseHook``."""

    @classmethod
    def get_connection(cls, conn_id: str) -> Connection:
        """Retorna a conexão cadastrada para ``conn_id``."""
        conn = resolve_connection(conn_id)
        if conn is None:
            raise KeyError(f"Connection '{conn_id}' not found")
        return conn
