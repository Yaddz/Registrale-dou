"""Implementação local de ``PostgresHook`` sobre ``psycopg`` e SQLAlchemy."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

import pandas as pd
import psycopg
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from airflow.sdk.bases.hook import BaseHook


class PostgresHook:
    """Implementação local de ``airflow.providers.postgres.hooks.postgres.PostgresHook``."""

    def __init__(self, postgres_conn_id: str = "postgres_default", *args: Any, **kwargs: Any):
        self.postgres_conn_id = postgres_conn_id

    def get_uri(self) -> str:
        """Monta a URI SQLAlchemy (``postgresql+psycopg://...``) a partir da conexão."""
        conn = BaseHook.get_connection(self.postgres_conn_id)
        user = quote_plus(conn.login or "")
        password = quote_plus(conn.password or "")
        auth = f"{user}:{password}@" if (conn.login or conn.password) else ""
        host = conn.host or "localhost"
        port = f":{conn.port}" if conn.port else ""
        schema = conn.schema or ""
        return f"postgresql+psycopg://{auth}{host}{port}/{schema}"

    def get_sqlalchemy_engine(self, engine_kwargs: dict[str, Any] | None = None) -> Engine:
        """Retorna um ``Engine`` do SQLAlchemy para a conexão configurada."""
        return create_engine(self.get_uri(), **(engine_kwargs or {}))

    def get_conn(self) -> psycopg.Connection[Any]:
        """Abre uma conexão DBAPI ``psycopg``."""
        conn = BaseHook.get_connection(self.postgres_conn_id)
        return psycopg.connect(
            host=conn.host or "localhost",
            port=conn.port or 5432,
            dbname=conn.schema or "",
            user=conn.login or "",
            password=conn.password or "",
        )

    def get_pandas_df(self, sql: str, parameters: Any = None) -> pd.DataFrame:
        """Executa consulta SELECT e retorna um ``pandas.DataFrame``."""
        engine = self.get_sqlalchemy_engine()
        try:
            with engine.connect() as connection:
                return pd.read_sql(sql, con=connection, params=parameters)
        finally:
            engine.dispose()

    def run(
        self,
        sql: str | list[str],
        autocommit: bool = False,
        parameters: Any = None,
    ) -> None:
        """Executa uma ou mais instruções SQL na conexão PostgreSQL."""
        statements = [sql] if isinstance(sql, str) else list(sql)
        with self.get_conn() as conn:
            conn.autocommit = autocommit
            with conn.cursor() as cur:
                for stmt in statements:
                    cur.execute(stmt, parameters)
            if not autocommit:
                conn.commit()
