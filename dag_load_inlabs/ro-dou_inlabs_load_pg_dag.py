"""Airflow DAG to download XML files from INLABS and store data into
Postgres db.
"""

import os
import sys
import shutil
import time
import logging
from datetime import datetime, timedelta, date

from airflow import Dataset  # type: ignore
from airflow.decorators import dag, task  # type: ignore
from airflow.models.param import Param  # type: ignore
from airflow.operators.python import get_current_context  # type: ignore
from airflow.models import Variable  # type: ignore
from airflow.providers.common.sql.operators.sql import SQLCheckOperator  # type: ignore

from ro_dou_src.utils.open_search.config import RO_DOU_INLABS_USE_OPENSEARCH  # type: ignore

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Constants
DEST_DIR = "download_inlabs"
DEST_CONN_ID = "inlabs_db"
INLABS_CONN_ID = "inlabs_portal"
STG_TABLE = "dou_inlabs.article_raw"

RAW_COLUMNS = [
    "id", "name", "idoficio", "pubname", "arttype", "pubdate",
    "artclass", "artcategory", "artsize", "artnotes", "numberpage",
    "pdfpage", "editionnumber", "highlighttype", "highlightpriority",
    "highlight", "highlightimage", "highlightimagename", "idmateria",
    "midias", "identifica", "data", "ementa", "titulo", "subtitulo",
    "texto", "assina"
]


def _notify_on_failure(context):
    """Sends a failure notification reusing FailureSender."""
    from types import SimpleNamespace
    from ro_dou_src.notification.failure_sender import FailureSender

    try:
        task_instance = context.get("task_instance") or context.get("ti")
        dag_run = context.get("dag_run")

        if not task_instance or not dag_run:
            logging.error("Missing required context: task_instance or dag_run")
            return

        specs = SimpleNamespace(callback=None, report=None)
        FailureSender(specs=specs).send(
            context, dag_run, task_instance, exception=context.get("exception")
        )
    except Exception as e:
        logging.error(f"Error in _notify_on_failure: {str(e)}", exc_info=True)


default_args = {
    "owner": "ro-dou_inlabs_load_pg",
    "start_date": datetime(2024, 4, 1),
    "depends_on_past": False,
    "retries": 4,
    "retry_delay": timedelta(seconds=15),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=1),
    "on_failure_callback": _notify_on_failure,
}


@dag(
    dag_id="ro-dou_inlabs_load_pg",
    default_args=default_args,
    schedule="59 6,23 * * *",
    catchup=False,
    description=__doc__,
    max_active_runs=1,
    params={
        "trigger_date": Param(
            default=date.today().isoformat(), type="string", format="date"
        )
    },
    tags=["ro-dou", "inlabs"],
)
def load_inlabs():

    @task
    def get_date() -> str:
        """Returns DAG trigger_date in YYYY-MM-DD"""
        from utils.date import get_trigger_date

        context = get_current_context()
        return get_trigger_date(context, local_time=True).strftime("%Y-%m-%d")

    @task.short_circuit
    def download_n_unzip_files(trigger_date: str):
        import requests
        from bs4 import BeautifulSoup
        import zipfile
        from urllib.parse import urljoin
        from airflow.hooks.base import BaseHook  # type: ignore

        date_dest_path = os.path.join(Variable.get("path_tmp"), DEST_DIR, trigger_date)

        def _prepare_directories():
            if os.path.exists(date_dest_path):
                shutil.rmtree(date_dest_path, ignore_errors=True)
            os.makedirs(date_dest_path, exist_ok=True)
            logging.info("Isolated directory %s initialized.", date_dest_path)

        def _get_authenticated_session():
            session = requests.Session()

            # 1. Tenta reaproveitar cookie em cache do Airflow
            cached_cookie = Variable.get("inlabs_session_cookie", default_var=None)
            if cached_cookie:
                test_headers = {
                    "Cookie": f"inlabs_session_cookie={cached_cookie}",
                    "origem": "736372697074",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                }
                try:
                    r_test = session.get(
                        urljoin(inlabs_conn.host, f"index.php?p={trigger_date}"),
                        headers=test_headers,
                        timeout=20,
                    )
                    if "Baixar Arquivo" in r_test.text or ".zip" in r_test.text:
                        logging.info("Sessão INLABS reaproveitada com sucesso a partir do cache!")
                        return session, cached_cookie
                    else:
                        logging.info("Cookie em cache expirou ou não retornou arquivos. Realizando nova autenticação...")
                except Exception as e:
                    logging.warning("Erro ao testar sessão em cache: %s", e)

            # 2. Realiza novo login com backoff progressivo (até 10 tentativas)
            logging.info("Iniciando autenticação no portal INLABS...")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }

            for attempt in range(1, 11):
                try:
                    s_login = requests.Session()
                    r = s_login.post(
                        urljoin(inlabs_conn.host, "logar.php"),
                        data={"email": inlabs_conn.login, "password": inlabs_conn.password},
                        headers=headers,
                        allow_redirects=False,
                        timeout=20,
                    )
                    cookie = s_login.cookies.get("inlabs_session_cookie") or r.cookies.get("inlabs_session_cookie")
                    if cookie:
                        logging.info("Autenticação realizada com sucesso na tentativa %s!", attempt)
                        Variable.set("inlabs_session_cookie", cookie)
                        return s_login, cookie
                    logging.warning("Tentativa %s retornou HTTP %s (aguardando portal se restabelecer)...", attempt, r.status_code)
                except Exception as ex:
                    logging.warning("Erro na tentativa de autenticação %s: %s", attempt, ex)

                time.sleep(attempt * 2)

            raise ValueError("Falha na autenticação do INLABS após 10 tentativas")

        def _find_files(session, headers):
            response = session.request(
                "GET",
                urljoin(inlabs_conn.host, f"index.php?p={trigger_date}"),
                headers=headers,
                timeout=60,
            )
            soup = BeautifulSoup(response.text, "html.parser")
            a_tags = soup.find_all("a", title="Baixar Arquivo")
            files = [
                tag.get("href") for tag in a_tags if tag.get("href", "").endswith(".zip")
            ]
            logging.info("Files found for %s: %s", trigger_date, files)
            if not files:
                logging.info("Nenhum arquivo .zip disponível no portal INLABS para a data %s (ex: final de semana, feriado ou data fora de circulação).", trigger_date)
                return []
            return files

        def _download_files():
            session, cookie = _get_authenticated_session()
            headers = {
                "Cookie": f"inlabs_session_cookie={cookie}",
                "origem": "736372697074",
            }
            files = _find_files(session, headers)
            if not files:
                return []

            downloaded_zip_paths = []
            for file in files:
                r = session.request(
                    "GET",
                    urljoin(inlabs_conn.host, f"index.php{file}"),
                    headers=headers,
                    timeout=120,
                )
                filename = file.split("dl=")[1]
                target_file_path = os.path.join(date_dest_path, filename)
                with open(target_file_path, "wb") as f:
                    f.write(r.content)
                downloaded_zip_paths.append(target_file_path)

            logging.info("Downloaded %s files into %s", len(downloaded_zip_paths), date_dest_path)
            return downloaded_zip_paths

        def _unzip_files(downloaded_zip_paths):
            if not downloaded_zip_paths:
                return
            extract_to = os.path.join(date_dest_path, "extracted")
            os.makedirs(extract_to, exist_ok=True)
            for zip_file_path in downloaded_zip_paths:
                with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
                    zip_ref.extractall(extract_to)
            logging.info("Unzipped %s files into %s", len(downloaded_zip_paths), extract_to)

        inlabs_conn = BaseHook.get_connection(INLABS_CONN_ID)
        _prepare_directories()
        downloaded_zip_paths = _download_files()
        _unzip_files(downloaded_zip_paths)

        if not downloaded_zip_paths:
            logging.info("Nenhum arquivo baixado para %s. Encerrando pipeline com sucesso (short-circuit).", trigger_date)
            return False

        return bool(downloaded_zip_paths)

    @task
    def load_data(trigger_date: str) -> None:
        from bs4 import BeautifulSoup
        import glob
        import pandas as pd
        from slugify import slugify  # type: ignore
        from airflow.providers.postgres.hooks.postgres import PostgresHook  # type: ignore
        from sqlalchemy.dialects.postgresql import insert

        def _get_assina(text):
            if not text or not isinstance(text, str):
                return None
            soup = BeautifulSoup(text, "html.parser")
            p_tags = soup.find_all("p", class_="assina")
            return ", ".join([p.text.strip() for p in p_tags if p.text]) if p_tags else None

        def _read_files() -> pd.DataFrame:
            extract_dir = os.path.join(
                Variable.get("path_tmp"), DEST_DIR, trigger_date, "extracted"
            )
            xml_files = glob.glob(os.path.join(extract_dir, "**/*.xml"), recursive=True)
            if not xml_files:
                logging.warning("No XML files found in %s", extract_dir)
                return pd.DataFrame(columns=RAW_COLUMNS)

            df_list = []
            for xml_file in xml_files:
                try:
                    df1 = pd.read_xml(xml_file)
                    df2 = pd.read_xml(xml_file, xpath="//body")
                    df_combined = df1.join(df2)
                    df_list.append(df_combined)
                except Exception as ex:
                    logging.warning("Failed parsing %s: %s", xml_file, str(ex))

            if not df_list:
                return pd.DataFrame(columns=RAW_COLUMNS)

            df = pd.concat(df_list, ignore_index=True)
            df.columns = [slugify(col, separator="_") for col in df.columns]

            if "body" in df.columns:
                df.drop(columns=["body"], inplace=True)

            if "pubdate" in df.columns:
                df["pubdate"] = pd.to_datetime(df["pubdate"], format="%d/%m/%Y", errors="coerce")

            if "texto" in df.columns:
                df["assina"] = df["texto"].apply(_get_assina)
            else:
                df["assina"] = None

            if "id" in df.columns:
                df["id"] = pd.to_numeric(df["id"], errors="coerce")
                df = df[df["id"].notna()]
                df["id"] = df["id"].astype("int64")

            # Deduplicação em memória mantendo a versão mais recente
            df = df.drop_duplicates(subset=["id"], keep="last")

            for col in RAW_COLUMNS:
                if col not in df.columns:
                    df[col] = None

            df = df[RAW_COLUMNS]
            return df

        def _postgres_upsert(table, conn, keys, data_iter):
            data = [dict(zip(keys, row)) for row in data_iter]
            if not data:
                return
            insert_stmt = insert(table.table).values(data)
            update_dict = {
                c.name: c for c in insert_stmt.excluded if c.name != "id"
            }
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=["id"],
                set_=update_dict,
            )
            conn.execute(upsert_stmt)

        df = _read_files()
        if df.empty:
            logging.warning("No data to load for date %s", trigger_date)
            return

        hook = PostgresHook(DEST_CONN_ID)
        engine = hook.get_sqlalchemy_engine()

        df.to_sql(
            name=STG_TABLE.split(".")[1],
            schema=STG_TABLE.split(".", maxsplit=1)[0],
            con=engine,
            if_exists="append",
            index=False,
            method=_postgres_upsert,
            chunksize=1000,
        )
        logging.info("Table `%s` successfully upserted with %s rows.", STG_TABLE, len(df))

    check_loaded_data = SQLCheckOperator(
        task_id="check_loaded_data",
        conn_id=DEST_CONN_ID,
        sql=f"""
            SELECT 1
                FROM
                    {STG_TABLE}
                WHERE
                    DATE(pubdate) = '{{{{ ti.xcom_pull(task_ids='get_date')}}}}'
                LIMIT 1
            """,
    )

    @task.branch
    def check_if_should_run_indexer():
        if RO_DOU_INLABS_USE_OPENSEARCH.lower() == "true":
            logging.info("OpenSearch enabled. Running indexer task.")
            return "indexer_data"
        logging.info("OpenSearch disabled. Skipping indexer task.")
        return "skip_indexer_data"

    @task
    def skip_indexer_data():
        logging.info("Indexer skipped because OpenSearch is disabled.")

    @task
    def indexer_data(trigger_date: str) -> None:
        from ro_dou_src.utils.open_search.indexer import Indexer  # type: ignore

        indexer = Indexer(conn_id=DEST_CONN_ID)
        indexer.run(trigger_date)

    @task.branch
    def check_if_first_run_of_day():
        context = get_current_context()
        execution_date = context.get("logical_date")
        prev_execution_date = context.get("prev_execution_date")
        logging.info("Execution_date: %s", execution_date)
        logging.info("Prev_execution_date: %s", prev_execution_date)

        if (
            execution_date
            and prev_execution_date
            and execution_date.day == prev_execution_date.day
        ):
            logging.info("Não é a primeira execução do dia - Triggering dataset edicao_extra")
            return "trigger_dataset_inlabs_edicao_extra"
        else:
            logging.info("Primeira execução do dia - Triggering dataset inlabs")
            return "trigger_dataset_inlabs"

    @task(outlets=[Dataset("inlabs_edicao_extra")])
    def trigger_dataset_inlabs_edicao_extra():
        pass

    @task(outlets=[Dataset("inlabs")])
    def trigger_dataset_inlabs():
        pass

    @task(trigger_rule="all_done")
    def remove_directory(trigger_date: str):
        date_dest_path = os.path.join(Variable.get("path_tmp"), DEST_DIR, trigger_date)
        if os.path.exists(date_dest_path):
            shutil.rmtree(date_dest_path, ignore_errors=True)
            logging.info(f"Directory {date_dest_path} removed.")

    # Orchestration
    trigger_date = get_date()
    download_task = download_n_unzip_files(trigger_date)
    load_task = load_data(trigger_date)
    run_indexer_task = check_if_should_run_indexer()
    indexer_task = indexer_data(trigger_date)
    skip_indexer_task = skip_indexer_data()
    remove_directory_task = remove_directory(trigger_date)
    check_first_run_task = check_if_first_run_of_day()

    (
        download_task
        >> load_task
        >> check_loaded_data
        >> run_indexer_task
    )
    run_indexer_task >> [indexer_task, skip_indexer_task] >> remove_directory_task
    (
        remove_directory_task
        >> check_first_run_task
        >> [trigger_dataset_inlabs_edicao_extra(), trigger_dataset_inlabs()]
    )


load_inlabs()
