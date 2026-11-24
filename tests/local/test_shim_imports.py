"""Testes de cobertura e comportamento do shim ``compat/airflow_shim``."""

from __future__ import annotations

import importlib
import sqlite3
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

pytest.importorskip("compat.bootstrap", reason="compat/ não montado no container Airflow")
from compat.bootstrap import SHIM_DIR, install_airflow_shim, is_airflow_installed

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"

EXCLUDED_MODULES = {
    "dou_dag_generator",
    "utils.open_search.indexer",
}


def _discover_src_modules() -> list[str]:
    """Lista todos os módulos Python de ``src/`` exceto os excluídos do modo local."""
    modules: list[str] = []
    for py_file in sorted(SRC_DIR.rglob("*.py")):
        if py_file.name == "__init__.py":
            continue
        rel = py_file.relative_to(SRC_DIR).with_suffix("")
        mod_name = ".".join(rel.parts)
        if mod_name in EXCLUDED_MODULES:
            continue
        modules.append(mod_name)
    return modules


@pytest.fixture(autouse=True)
def _reset_shim_providers():
    """Garante isolamento dos provedores em memória entre testes."""
    from airflow._provider import clear_providers

    clear_providers()
    yield
    clear_providers()


def test_shim_ativado_sem_airflow_real():
    """Confirma que o shim está ativo e que o Airflow real não está instalado."""
    assert install_airflow_shim() is True
    assert is_airflow_installed() is False
    assert str(SHIM_DIR) in sys.path

    import airflow

    assert getattr(airflow, "__is_registrale_shim__", False) is True


def test_bootstrap_nao_sobrescreve_airflow_real(monkeypatch):
    """Se um módulo ``airflow`` real existir, ``install_airflow_shim`` retorna False."""
    fake_real_airflow = types.ModuleType("airflow")
    monkeypatch.setitem(sys.modules, "airflow", fake_real_airflow)
    assert is_airflow_installed() is True
    assert install_airflow_shim() is False


@pytest.mark.parametrize("module_name", _discover_src_modules())
def test_src_module_importavel_com_shim(module_name: str):
    """Todos os módulos de ``src/`` (exceto gerador de DAG e indexer) importam com o shim."""
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
    mod = importlib.import_module(module_name)
    assert mod is not None


def test_variable_get_memoria_default_json_env_e_sqlite(tmp_path, monkeypatch):
    """Valida ``Variable.get`` com memória, default, JSON, env var, provedor e SQLite."""
    from airflow._provider import set_variable_provider, set_variables
    from airflow.sdk import Variable

    set_variables({"CHAVE_STR": "valor", "CHAVE_JSON": '{"a": 1, "b": [2, 3]}'})
    assert Variable.get("CHAVE_STR") == "valor"
    assert Variable.get("CHAVE_JSON", deserialize_json=True) == {"a": 1, "b": [2, 3]}
    assert Variable.get("INEXISTENTE", default="padrao") == "padrao"
    assert Variable.get("INEXISTENTE", "posicional") == "posicional"
    assert Variable.get("INEXISTENTE", default_var="compat") == "compat"

    with pytest.raises(KeyError, match="INEXISTENTE"):
        Variable.get("INEXISTENTE")

    monkeypatch.setenv("AIRFLOW_VAR_MINHA_VAR", "via_env")
    assert Variable.get("minha_var") == "via_env"

    db_file = tmp_path / "settings.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)",
            ("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com"),
        )
    monkeypatch.setenv("REGISTRALE_DB_PATH", str(db_file))
    assert Variable.get("AZURE_OPENAI_ENDPOINT") == "https://example.openai.azure.com"

    set_variable_provider(lambda k: (True, "do_provedor") if k == "DINAMICA" else (False, None))
    assert Variable.get("DINAMICA") == "do_provedor"


def test_base_hook_get_connection():
    """Valida ``BaseHook.get_connection`` com atributos e ``extra_dejson``."""
    from airflow._provider import Connection, set_connection_provider, set_connections
    from airflow.sdk.bases.hook import BaseHook

    set_connections(
        {
            "inlabs_portal": Connection(
                conn_id="inlabs_portal",
                conn_type="http",
                host="https://inlabs.in.gov.br",
                login="user@example.com",
                password="secret",
                port=443,
                schema="https",
                extra='{"timeout": 30}',
            )
        }
    )

    conn = BaseHook.get_connection("inlabs_portal")
    assert conn.host == "https://inlabs.in.gov.br"
    assert conn.login == "user@example.com"
    assert conn.password == "secret"
    assert conn.port == 443
    assert conn.schema == "https"
    assert conn.extra_dejson == {"timeout": 30}

    set_connection_provider(
        lambda cid: Connection(conn_id=cid, conn_type="postgres", host="127.0.0.1", port=54329)
        if cid == "inlabs_db"
        else None
    )
    db_conn = BaseHook.get_connection("inlabs_db")
    assert db_conn.conn_type == "postgres"
    assert db_conn.port == 54329
    assert db_conn.extra_dejson == {}

    with pytest.raises(KeyError, match="nao_existe"):
        BaseHook.get_connection("nao_existe")


def test_postgres_hook_uri_engine_conn_pandas_e_run():
    """Valida ``PostgresHook`` (URI, SQLAlchemy engine, psycopg conn, DataFrame e run)."""
    from airflow._provider import Connection, set_connections
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    set_connections(
        {
            "inlabs_db": Connection(
                conn_id="inlabs_db",
                conn_type="postgres",
                host="127.0.0.1",
                port=54329,
                schema="inlabs",
                login="registrale",
                password="p@ss:word",
            )
        }
    )

    hook = PostgresHook("inlabs_db")
    assert hook.get_uri() == "postgresql+psycopg://registrale:p%40ss%3Aword@127.0.0.1:54329/inlabs"

    mock_engine = MagicMock()
    with patch(
        "airflow.providers.postgres.hooks.postgres.create_engine",
        return_value=mock_engine,
    ) as create_eng:
        eng = hook.get_sqlalchemy_engine()
        assert eng is mock_engine
        create_eng.assert_called_once()

    expected_df = pd.DataFrame({"id": [1]})
    with (
        patch.object(hook, "get_sqlalchemy_engine", return_value=mock_engine),
        patch("airflow.providers.postgres.hooks.postgres.pd.read_sql", return_value=expected_df) as read_sql,
    ):
        df = hook.get_pandas_df("SELECT 1")
        assert df.equals(expected_df)
        read_sql.assert_called_once()
        mock_engine.dispose.assert_called_once()

    mock_pg_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pg_conn.__enter__.return_value = mock_pg_conn
    mock_pg_conn.cursor.return_value.__enter__.return_value = mock_cursor
    with patch(
        "airflow.providers.postgres.hooks.postgres.psycopg.connect",
        return_value=mock_pg_conn,
    ) as pg_connect:
        hook.run("CREATE EXTENSION IF NOT EXISTS unaccent", autocommit=True)
        pg_connect.assert_called_once_with(
            host="127.0.0.1",
            port=54329,
            dbname="inlabs",
            user="registrale",
            password="p@ss:word",
        )
        assert mock_pg_conn.autocommit is True
        mock_cursor.execute.assert_called_once_with("CREATE EXTENSION IF NOT EXISTS unaccent", None)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: __import__("airflow").DAG("x"),
        lambda: __import__("airflow.sdk", fromlist=["TaskGroup"]).TaskGroup("x"),
        lambda: __import__("airflow.sdk.definitions.asset", fromlist=["Dataset"]).Dataset("x"),
        lambda: __import__(
            "airflow.providers.microsoft.mssql.hooks.mssql", fromlist=["MsSqlHook"]
        ).MsSqlHook("x"),
        lambda: __import__(
            "airflow.providers.slack.notifications.slack", fromlist=["SlackNotifier"]
        ).SlackNotifier(),
        lambda: __import__(
            "airflow.providers.standard.operators.empty", fromlist=["EmptyOperator"]
        ).EmptyOperator(task_id="x"),
        lambda: __import__(
            "airflow.providers.standard.operators.python", fromlist=["PythonOperator"]
        ).PythonOperator(task_id="x", python_callable=lambda: None),
        lambda: __import__(
            "airflow.providers.standard.operators.python", fromlist=["BranchPythonOperator"]
        ).BranchPythonOperator(task_id="x", python_callable=lambda: None),
        lambda: __import__(
            "airflow.timetables.assets", fromlist=["AssetOrTimeSchedule"]
        ).AssetOrTimeSchedule(timetable=None, assets=[]),
        lambda: __import__(
            "airflow.timetables.trigger", fromlist=["CronTriggerTimetable"]
        ).CronTriggerTimetable("0 5 * * *"),
        lambda: __import__("airflow.utils.email", fromlist=["send_email"]).send_email(
            to="a@b.com", subject="s", html_content="c"
        ),
    ],
)
def test_stubs_nao_suportados_lancam_not_implemented_error(factory):
    """Símbolos não usados no modo local falham com ``NotImplementedError`` explicativo."""
    with pytest.raises(NotImplementedError):
        factory()
