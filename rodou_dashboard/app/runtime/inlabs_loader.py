"""Loader local do INLABS (porta direta de `dag_load_inlabs/ro_dou_inlabs_load_pg_dag.py`).

Reutiliza a lógica de download, parse de XML e upsert em `dou_inlabs.article_raw`
via `PostgresHook`, adicionando extração ZIP segura (Zip Slip e limites de
tamanho/quantidade) e limpeza de temporários.
"""

from __future__ import annotations

import glob
import logging
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin
import zipfile

from bs4 import BeautifulSoup
import pandas as pd
import requests
from sqlalchemy.dialects.postgresql import insert
from unidecode import unidecode

from .paths import get_inlabs_dir
from .runner import _ensure_src_imports

logger = logging.getLogger(__name__)

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
    "texto", "assina",
]

DEFAULT_MAX_ZIP_FILES = 2000
DEFAULT_MAX_ZIP_TOTAL_BYTES = 512 * 1024 * 1024  # 512 MB
DEFAULT_MAX_ZIP_FILE_BYTES = 64 * 1024 * 1024    # 64 MB

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


class InlabsLoaderError(RuntimeError):
    """Erro geral no carregamento do INLABS."""


class InlabsMaintenanceError(InlabsLoaderError):
    """Portal INLABS em manutenção ou indisponível."""


class InlabsSecurityError(InlabsLoaderError):
    """Violação de segurança na extração de arquivo ZIP (Zip Slip ou ZIP bomb)."""


def _slugify_col(name: str) -> str:
    try:
        from slugify import slugify  # type: ignore

        return slugify(name, separator="_")
    except ImportError:
        ascii_name = unidecode(str(name)).lower()
        return re.sub(r"[^a-z0-9]+", "_", ascii_name).strip("_")


def _get_cached_cookie() -> Optional[str]:
    _ensure_src_imports()
    from airflow.sdk import Variable  # type: ignore

    val = Variable.get("inlabs_session_cookie", default=None)
    return str(val) if val else None


def _save_cached_cookie(cookie: str) -> None:
    try:
        from ..models import Settings, db

        rec = Settings.query.filter_by(key="inlabs_session_cookie").first()
        if rec:
            rec.value = cookie
        else:
            db.session.add(Settings(key="inlabs_session_cookie", value=cookie))
        db.session.commit()
    except Exception:
        pass


def safe_extract_zip(
    zip_path: Path | str,
    extract_to: Path | str,
    max_files: int = DEFAULT_MAX_ZIP_FILES,
    max_total_bytes: int = DEFAULT_MAX_ZIP_TOTAL_BYTES,
    max_file_bytes: int = DEFAULT_MAX_ZIP_FILE_BYTES,
) -> List[Path]:
    """Extrai um arquivo ZIP validando Zip Slip, symlinks e limites de tamanho/quantidade."""
    extract_root = Path(extract_to).resolve()
    extract_root.mkdir(parents=True, exist_ok=True)

    extracted: List[Path] = []
    total_bytes = 0
    file_count = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        infos = zf.infolist()
        if len(infos) > max_files:
            raise InlabsSecurityError(
                f"ZIP excede o limite de entradas ({len(infos)} > {max_files})."
            )

        for info in infos:
            member_name = info.filename
            if not member_name:
                continue

            # Rejeita symlinks embutidos no ZIP
            unix_mode = info.external_attr >> 16
            if stat.S_ISLNK(unix_mode):
                raise InlabsSecurityError(
                    f"Entrada symlink rejeitada no ZIP: {member_name!r}"
                )

            # Normaliza separadores e bloqueia caminhos absolutos ou traversal ('..')
            normalized = member_name.replace("\\", "/")
            if (
                normalized.startswith("/")
                or (len(normalized) >= 2 and normalized[1] == ":")
                or ".." in PurePosixPath(normalized).parts
            ):
                raise InlabsSecurityError(
                    f"Caminho inseguro (Zip Slip) detectado no ZIP: {member_name!r}"
                )

            target_path = (extract_root / normalized).resolve()
            if target_path != extract_root and not target_path.is_relative_to(extract_root):
                raise InlabsSecurityError(
                    f"Destino fora do diretório permitido (Zip Slip): {member_name!r}"
                )

            if info.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            file_count += 1
            if file_count > max_files:
                raise InlabsSecurityError(
                    f"ZIP excede o limite de arquivos ({file_count} > {max_files})."
                )

            if info.file_size > max_file_bytes:
                raise InlabsSecurityError(
                    f"Arquivo {member_name!r} excede o limite de {max_file_bytes} bytes."
                )

            target_path.parent.mkdir(parents=True, exist_ok=True)
            entry_bytes = 0
            with zf.open(info, "r") as src, open(target_path, "wb") as dst:
                while True:
                    chunk = src.read(65536)
                    if not chunk:
                        break
                    entry_bytes += len(chunk)
                    total_bytes += len(chunk)
                    if entry_bytes > max_file_bytes:
                        raise InlabsSecurityError(
                            f"Arquivo {member_name!r} excedeu o limite real de {max_file_bytes} bytes."
                        )
                    if total_bytes > max_total_bytes:
                        raise InlabsSecurityError(
                            f"Tamanho total extraído excedeu o limite de {max_total_bytes} bytes."
                        )
                    dst.write(chunk)

            extracted.append(target_path)

    return extracted


def _get_assina(text: Any) -> Optional[str]:
    if not text or not isinstance(text, str):
        return None
    soup = BeautifulSoup(text, "html.parser")
    p_tags = soup.find_all("p", class_="assina")
    return ", ".join([p.text.strip() for p in p_tags if p.text]) if p_tags else None


def parse_xml_files(extract_dir: Path | str) -> pd.DataFrame:
    """Lê os XMLs extraídos e retorna DataFrame normalizado no schema `RAW_COLUMNS`."""
    xml_files = sorted(
        glob.glob(os.path.join(str(extract_dir), "**/*.xml"), recursive=True)
    )
    if not xml_files:
        logger.warning("Nenhum XML encontrado em %s", extract_dir)
        return pd.DataFrame(columns=RAW_COLUMNS)

    df_list = []
    for xml_file in xml_files:
        try:
            df1 = pd.read_xml(xml_file)
            df2 = pd.read_xml(xml_file, xpath="//body")
            df_combined = df1.join(df2)
            df_list.append(df_combined)
        except Exception as ex:
            logger.warning("Falha ao processar XML %s: %s", xml_file, ex)

    if not df_list:
        return pd.DataFrame(columns=RAW_COLUMNS)

    df = pd.concat(df_list, ignore_index=True)
    df.columns = [_slugify_col(col) for col in df.columns]

    if "body" in df.columns:
        df.drop(columns=["body"], inplace=True)

    if "pubdate" in df.columns:
        df["pubdate"] = pd.to_datetime(
            df["pubdate"], format="%d/%m/%Y", errors="coerce"
        )

    if "texto" in df.columns:
        df["assina"] = df["texto"].apply(_get_assina)
    else:
        df["assina"] = None

    if "id" in df.columns:
        df["id"] = pd.to_numeric(df["id"], errors="coerce")
        df = df[df["id"].notna()]
        df["id"] = df["id"].astype("int64")
        df = df.drop_duplicates(subset=["id"], keep="last")

    for col in RAW_COLUMNS:
        if col not in df.columns:
            df[col] = None

    return df[RAW_COLUMNS]


def _postgres_upsert(table: Any, conn: Any, keys: Any, data_iter: Any) -> None:
    data = [dict(zip(keys, row)) for row in data_iter]
    if not data:
        return
    insert_stmt = insert(table.table).values(data)
    update_dict = {c.name: c for c in insert_stmt.excluded if c.name != "id"}
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=["id"],
        set_=update_dict,
    )
    conn.execute(upsert_stmt)


def upsert_articles(df: pd.DataFrame, conn_id: str = DEST_CONN_ID) -> int:
    """Insere ou atualiza artigos em `dou_inlabs.article_raw` via `PostgresHook`."""
    if df.empty:
        return 0
    _ensure_src_imports()
    from airflow.providers.postgres.hooks.postgres import PostgresHook  # type: ignore

    hook = PostgresHook(conn_id)
    engine = hook.get_sqlalchemy_engine()
    try:
        df.to_sql(
            name=STG_TABLE.split(".")[1],
            schema=STG_TABLE.split(".", maxsplit=1)[0],
            con=engine,
            if_exists="append",
            index=False,
            method=_postgres_upsert,
            chunksize=1000,
        )
    finally:
        engine.dispose()

    logger.info("Tabela `%s` atualizada (upsert) com %d linha(s).", STG_TABLE, len(df))
    return len(df)


def check_loaded_data(reference_date: str, conn_id: str = DEST_CONN_ID) -> bool:
    """Verifica se há ao menos 1 artigo carregado em `dou_inlabs.article_raw` na data."""
    _ensure_src_imports()
    from airflow.providers.postgres.hooks.postgres import PostgresHook  # type: ignore

    hook = PostgresHook(conn_id)
    df = hook.get_pandas_df(
        f"SELECT 1 FROM {STG_TABLE} WHERE DATE(pubdate) = %s LIMIT 1",
        parameters=(reference_date,),
    )
    return not df.empty


def _get_authenticated_session(
    base_url: str,
    login: str,
    password: str,
    session_factory: Callable[[], requests.Session] = requests.Session,
    max_attempts: int = 10,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Tuple[requests.Session, str]:
    """Autentica no portal INLABS reaproveitando cookie e falhando rápido em manutenção."""
    session = session_factory()

    cached_cookie = _get_cached_cookie()
    if cached_cookie:
        session.cookies.set("inlabs_session_cookie", cached_cookie)
        session.cookies.set("origem", "736372697074")
        test_headers = {
            "User-Agent": _USER_AGENT,
            "Cookie": f"inlabs_session_cookie={cached_cookie}; origem=736372697074",
        }
        try:
            r_test = session.get(
                urljoin(base_url, "index.php"),
                headers=test_headers,
                timeout=20,
                allow_redirects=True,
            )
            body_lower = r_test.text.lower()
            if "logar.php" not in r_test.url and (
                "deslogar" in body_lower
                or "sair" in body_lower
                or "usuário" in body_lower
                or "usuario" in body_lower
                or "p=" in r_test.text
                or "Baixar Arquivo" in r_test.text
            ):
                logger.info("Sessão INLABS reaproveitada com sucesso a partir do cache.")
                return session, cached_cookie
            logger.info("Cookie em cache expirou. Realizando nova autenticação...")
        except Exception as exc:
            logger.warning("Erro ao testar sessão em cache do INLABS: %s", exc)

    # Falha rápida se o portal estiver em manutenção
    try:
        r_probe = session.get(base_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        probe_text = r_probe.content.decode("utf-8", errors="ignore").lower()[:3000]
        if (
            r_probe.status_code >= 500
            or "manutenção" in probe_text
            or "manutencao" in probe_text
        ):
            raise InlabsMaintenanceError(
                f"Portal INLABS em manutenção/indisponível (HTTP {r_probe.status_code})."
            )
    except requests.exceptions.RequestException as probe_err:
        logger.warning("Falha ao verificar disponibilidade do INLABS: %s", probe_err)

    headers = {
        "User-Agent": _USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    for attempt in range(1, max_attempts + 1):
        try:
            s_login = session_factory()
            r = s_login.post(
                urljoin(base_url, "logar.php"),
                data={"email": login, "password": password},
                headers=headers,
                allow_redirects=False,
                timeout=20,
            )
            if r.status_code == 404 or r.status_code >= 500:
                raise InlabsMaintenanceError(
                    f"Endpoint de login do INLABS indisponível (HTTP {r.status_code})."
                )
            cookie = s_login.cookies.get("inlabs_session_cookie") or r.cookies.get(
                "inlabs_session_cookie"
            )
            if cookie:
                logger.info("Autenticação INLABS realizada na tentativa %d.", attempt)
                _save_cached_cookie(cookie)
                s_login.cookies.set("inlabs_session_cookie", cookie)
                s_login.cookies.set("origem", "736372697074")
                return s_login, cookie
            logger.warning(
                "Tentativa %d de login INLABS retornou HTTP %s.", attempt, r.status_code
            )
        except InlabsMaintenanceError:
            raise
        except Exception as ex:
            logger.warning("Erro na tentativa %d de login INLABS: %s", attempt, ex)

        sleep_fn(attempt * 2)

    raise InlabsLoaderError(
        f"Falha na autenticação do INLABS após {max_attempts} tentativas."
    )


def _find_zip_links(
    session: requests.Session,
    base_url: str,
    reference_date: str,
    headers: Dict[str, str],
) -> List[str]:
    response = session.request(
        "GET",
        urljoin(base_url, f"index.php?p={reference_date}"),
        headers=headers,
        timeout=60,
    )
    soup = BeautifulSoup(response.text, "html.parser")
    a_tags = soup.find_all("a", title="Baixar Arquivo")
    files = [
        tag.get("href") for tag in a_tags if str(tag.get("href", "")).endswith(".zip")
    ]
    if not files:
        logger.info(
            "Nenhum arquivo .zip disponível no INLABS para %s.", reference_date
        )
        return []
    return files


def load_inlabs_date(
    reference_date: str,
    *,
    conn_id: str = DEST_CONN_ID,
    inlabs_conn_id: str = INLABS_CONN_ID,
    work_root: Optional[Path] = None,
    session_factory: Callable[[], requests.Session] = requests.Session,
    max_attempts: int = 10,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    """Baixa, extrai com segurança, processa XMLs e carrega `reference_date` no PostgreSQL."""
    _ensure_src_imports()
    from airflow.sdk.bases.hook import BaseHook  # type: ignore

    inlabs_conn = BaseHook.get_connection(inlabs_conn_id)
    if not inlabs_conn.login or not inlabs_conn.password:
        raise InlabsLoaderError(
            "Credenciais do INLABS (usuário/senha) não configuradas no painel."
        )
    base_url = inlabs_conn.host or "https://inlabs.in.gov.br/"

    base_dir = Path(work_root) if work_root is not None else get_inlabs_dir(create=True)
    date_dest_path = base_dir / DEST_DIR / reference_date
    if date_dest_path.exists():
        shutil.rmtree(date_dest_path, ignore_errors=True)
    date_dest_path.mkdir(parents=True, exist_ok=True)

    try:
        session, cookie = _get_authenticated_session(
            base_url=base_url,
            login=inlabs_conn.login,
            password=inlabs_conn.password,
            session_factory=session_factory,
            max_attempts=max_attempts,
            sleep_fn=sleep_fn,
        )
        headers = {
            "User-Agent": _USER_AGENT,
            "Cookie": f"inlabs_session_cookie={cookie}; origem=736372697074",
        }
        files = _find_zip_links(session, base_url, reference_date, headers)
        if not files:
            return {
                "status": "empty",
                "date": reference_date,
                "rows": 0,
                "message": f"Nenhum arquivo .zip disponível para {reference_date}.",
            }

        downloaded_zip_paths: List[Path] = []
        for file_href in files:
            r = session.request(
                "GET",
                urljoin(base_url, f"index.php{file_href}"),
                headers=headers,
                timeout=120,
            )
            r.raise_for_status()
            raw_name = file_href.split("dl=")[1] if "dl=" in file_href else file_href
            safe_name = os.path.basename(raw_name.replace("\\", "/"))
            if not safe_name.endswith(".zip"):
                safe_name += ".zip"
            target_zip = date_dest_path / safe_name
            target_zip.write_bytes(r.content)
            downloaded_zip_paths.append(target_zip)

        extract_to = date_dest_path / "extracted"
        extract_to.mkdir(parents=True, exist_ok=True)
        for zip_file_path in downloaded_zip_paths:
            safe_extract_zip(zip_file_path, extract_to)

        df = parse_xml_files(extract_to)
        if df.empty:
            return {
                "status": "empty",
                "date": reference_date,
                "rows": 0,
                "message": f"Nenhum artigo XML válido encontrado para {reference_date}.",
            }

        rows = upsert_articles(df, conn_id=conn_id)
        has_data = check_loaded_data(reference_date, conn_id=conn_id)
        if not has_data:
            raise InlabsLoaderError(
                f"Verificação pós-carga não encontrou registros para {reference_date}."
            )

        try:
            from ..services.inlabs_service import (
                enforce_inlabs_retention_limit,
                record_inlabs_download_success,
            )

            record_inlabs_download_success(reference_date)
            enforce_inlabs_retention_limit(max_days=120, protected_dates=[reference_date])
        except Exception as exc:
            logger.debug("Retenção/log INLABS ignorado fora do contexto Flask: %s", exc)

        return {
            "status": "success",
            "date": reference_date,
            "rows": rows,
            "message": f"{rows} artigo(s) carregado(s) no INLABS para {reference_date}.",
        }
    finally:
        if date_dest_path.exists():
            shutil.rmtree(date_dest_path, ignore_errors=True)
