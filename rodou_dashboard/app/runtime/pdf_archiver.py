"""Arquivamento automático dos PDFs integrais do Diário Oficial da União (DOU).

Fontes suportadas:
1. Principal: Portal INLABS (``https://inlabs.in.gov.br/``), autenticado via cookie de sessão,
   baixando o PDF integral por seção em uma única requisição HTTP.
2. Alternativa: Portal oficial ``https://pesquisa.in.gov.br/imprensa/`` (``INPDFViewer``),
   sem necessidade de login, usado automaticamente quando o INLABS está em manutenção,
   sem credenciais ou para datas fora da janela de retenção do INLABS.

Os arquivos são salvos de forma idempotente em:
``<pasta>/<AAAA>/<MM>/DOU_<AAAA-MM-DD>_Secao1.pdf`` (e ``Secao2``, ``Secao3``, ``SecaoExtra``).
"""

from __future__ import annotations

import calendar
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import io
import logging
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urljoin

import requests

from .paths import get_default_pdf_dir

logger = logging.getLogger(__name__)

_BRASILIA_TZ = timezone(timedelta(hours=-3))
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_PESQUISA_BASE_URL = "https://pesquisa.in.gov.br/imprensa/"
_SECTION_TO_JORNAL: Dict[str, Tuple[int, ...]] = {
    "1": (515,),
    "2": (529,),
    "3": (530,),
    "extra": (600, 601, 602, 603, 604),
}

_SECTION_FILE_LABELS: Dict[str, str] = {
    "1": "Secao1",
    "2": "Secao2",
    "3": "Secao3",
    "extra": "SecaoExtra",
}

DEFAULT_SECTIONS: List[str] = ["1", "2", "3", "extra"]
_ARCHIVE_LOCK = threading.Lock()
_ARCHIVE_RUNNING = False


class PdfArchiverError(RuntimeError):
    """Erro operacional no arquivamento de PDFs do DOU."""


def normalize_date_iso(raw_date: str) -> str:
    """Converte ``DD/MM/AAAA``, ``DD/MM/AA`` ou ``AAAA-MM-DD`` para ``AAAA-MM-DD``."""
    s = str(raw_date or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Formato de data inválido para arquivamento de PDF: {raw_date!r}")


def normalize_section_key(raw_section: Any) -> Optional[str]:
    """Normaliza identificador de seção (``1``, ``2``, ``3``, ``extra``), incluindo enums/YAML."""
    raw = getattr(raw_section, "value", raw_section)
    s = str(raw or "").strip().lower()
    if not s:
        return None
    if "extra" in s or "suplementar" in s or s.endswith("e") or s in {"do1e", "do2e", "do3e", "ex"}:
        return "extra"
    if (
        s in {"1", "do1", "secao1", "secao_1", "seção 1", "secao 1", "s1"}
        or "seção 1" in s
        or "secao 1" in s
        or s.endswith("_1")
    ):
        return "1"
    if (
        s in {"2", "do2", "secao2", "secao_2", "seção 2", "secao 2", "s2"}
        or "seção 2" in s
        or "secao 2" in s
        or s.endswith("_2")
    ):
        return "2"
    if (
        s in {"3", "do3", "secao3", "secao_3", "seção 3", "secao 3", "s3"}
        or "seção 3" in s
        or "secao 3" in s
        or s.endswith("_3")
    ):
        return "3"
    return None


def normalize_sections(sections: Optional[Iterable[Any]]) -> List[str]:
    """Normaliza e ordena a lista de seções configuradas sem duplicatas."""
    if not sections:
        return list(DEFAULT_SECTIONS)
    seen: List[str] = []
    for item in sections:
        key = normalize_section_key(item)
        if key and key not in seen:
            seen.append(key)
    return seen or list(DEFAULT_SECTIONS)


def build_pdf_target_path(
    base_folder: Path,
    date_iso: str,
    section_key: str,
    extra_suffix: Optional[str] = None,
) -> Path:
    """Retorna ``<base_folder>/<AAAA>/<MM>/DOU_<AAAA-MM-DD>_SecaoN.pdf``."""
    dt = datetime.strptime(date_iso, "%Y-%m-%d")
    label = _SECTION_FILE_LABELS.get(section_key, f"Secao{section_key}")
    if extra_suffix:
        safe_suffix = re.sub(r"[^A-Za-z0-9_-]", "", extra_suffix)
        if safe_suffix:
            label = f"{label}_{safe_suffix}"
    filename = f"DOU_{date_iso}_{label}.pdf"
    return Path(base_folder) / dt.strftime("%Y") / dt.strftime("%m") / filename


def is_valid_pdf_bytes(payload: bytes, min_bytes: int = 128) -> bool:
    """Valida cabeçalho ``%PDF``, tamanho mínimo e leitura estrutural via ``pypdf``."""
    if not payload or len(payload) < min_bytes:
        return False
    if not payload.lstrip()[:8].startswith(b"%PDF"):
        return False
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(payload), strict=False)
        return len(reader.pages) >= 1
    except Exception:
        return False


def is_valid_pdf_file(path: Path, min_bytes: int = 128) -> bool:
    """Valida se ``path`` existe, possui tamanho mínimo, cabeçalho ``%PDF`` e >= 1 página."""
    try:
        if not path.is_file() or path.stat().st_size < min_bytes:
            return False
        with open(path, "rb") as fh:
            head = fh.read(16)
        if not head.lstrip().startswith(b"%PDF"):
            return False
        from pypdf import PdfReader

        reader = PdfReader(str(path), strict=False)
        return len(reader.pages) >= 1
    except Exception:
        return False


def _atomic_write_pdf(target_path: Path, payload: bytes) -> None:
    """Grava ``payload`` em arquivo temporário e move atomicamente para ``target_path``."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f".{target_path.name}.tmp.{os.getpid()}.{threading.get_ident()}")
    try:
        with open(tmp_path, "wb") as fh:
            fh.write(payload)
        os.replace(tmp_path, target_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def get_pdf_archive_config() -> Dict[str, Any]:
    """Lê configuração de arquivamento de PDF do SQLite (``global_settings.pdf_archive``)."""
    default_folder = str(get_default_pdf_dir(create=False))
    cfg: Dict[str, Any] = {
        "enabled": True,
        "folder": default_folder,
        "sections": list(DEFAULT_SECTIONS),
    }
    try:
        from ..models import Settings

        rec = Settings.query.filter_by(key="global_settings").first()
        if rec:
            val = rec.get_value()
            if isinstance(val, dict) and isinstance(val.get("pdf_archive"), dict):
                raw = val["pdf_archive"]
                if "enabled" in raw:
                    cfg["enabled"] = bool(raw["enabled"])
                folder_raw = str(raw.get("folder") or "").strip()
                if folder_raw:
                    cfg["folder"] = str(Path(folder_raw).expanduser())
                if "sections" in raw and isinstance(raw["sections"], list):
                    cfg["sections"] = normalize_sections(raw["sections"])
    except Exception:
        pass

    if os.getenv("REGISTRALE_PDF_DIR"):
        cfg["folder"] = str(get_default_pdf_dir(create=False))
    return cfg


def get_pdf_archive_status() -> Dict[str, Any]:
    """Retorna o status do último arquivamento salvo em ``Settings``."""
    status: Dict[str, Any] = {
        "running": _ARCHIVE_RUNNING,
        "last_run_at": None,
        "last_date": None,
        "last_source": None,
        "last_status": "never",
        "last_message": "Nenhum arquivamento executado ainda.",
        "saved_files": [],
        "skipped_files": [],
        "errors": [],
    }
    try:
        from ..models import Settings

        rec = Settings.query.filter_by(key="pdf_archive_status").first()
        if rec:
            val = rec.get_value()
            if isinstance(val, dict):
                status.update(val)
    except Exception:
        pass
    status["running"] = _ARCHIVE_RUNNING
    return status


def _save_pdf_archive_status(payload: Dict[str, Any]) -> None:
    """Persiste o status do último arquivamento em ``Settings``."""
    try:
        from ..models import Settings, db

        rec = Settings.query.filter_by(key="pdf_archive_status").first()
        if not rec:
            rec = Settings(key="pdf_archive_status")
            db.session.add(rec)
        rec.set_value(payload)
        db.session.commit()
    except Exception as exc:
        logger.debug("Não foi possível persistir pdf_archive_status: %s", exc)


def _request_with_retries(
    session: requests.Session,
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    max_retries: int = 3,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> requests.Response:
    """Executa requisição HTTP com tentativas e backoff exponencial em falhas transitórias."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.request(method, url, headers=headers, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                sleep_fn(min(10.0, 1.5 * attempt))
                continue
            resp.raise_for_status()
            return resp
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                sleep_fn(min(10.0, 1.5 * attempt))
    assert last_exc is not None
    raise last_exc


def _discover_inlabs_pdf_links(
    session: requests.Session,
    base_url: str,
    date_iso: str,
    headers: Dict[str, str],
) -> Dict[str, List[str]]:
    """Lista links ``.pdf`` no INLABS para ``date_iso``, agrupados por seção."""
    url = urljoin(base_url, f"index.php?p={date_iso}")
    resp = _request_with_retries(session, "GET", url, headers=headers, timeout=30)
    from .inlabs_loader import _is_maintenance_html

    if _is_maintenance_html(resp.text):
        from .inlabs_loader import InlabsMaintenanceError

        raise InlabsMaintenanceError("INLABS em manutenção programada.")

    hrefs = re.findall(r'href=["\']([^"\']*\.pdf[^"\']*)["\']', resp.text, re.IGNORECASE)
    grouped: Dict[str, List[str]] = {"1": [], "2": [], "3": [], "extra": []}
    for href in hrefs:
        upper = href.upper()
        if "DO1E" in upper or "DO2E" in upper or "DO3E" in upper or "EXTRA" in upper:
            grouped["extra"].append(href)
        elif "DO1" in upper:
            grouped["1"].append(href)
        elif "DO2" in upper:
            grouped["2"].append(href)
        elif "DO3" in upper:
            grouped["3"].append(href)
    return grouped


def _try_archive_via_inlabs(
    date_iso: str,
    sections: List[str],
    base_folder: Path,
    *,
    session_factory: Callable[[], requests.Session] = requests.Session,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Optional[Dict[str, Any]]:
    """Tenta baixar os PDFs faltantes via INLABS. Retorna ``None`` se indisponível."""
    try:
        from compat.bootstrap import install_airflow_shim

        install_airflow_shim()
        from airflow.sdk.bases.hook import BaseHook  # type: ignore

        inlabs_conn = BaseHook.get_connection("inlabs_portal")
    except Exception:
        return None

    if not getattr(inlabs_conn, "login", None) or not getattr(inlabs_conn, "password", None):
        return None

    base_url = getattr(inlabs_conn, "host", None) or "https://inlabs.in.gov.br/"

    try:
        from .inlabs_loader import InlabsMaintenanceError, _get_authenticated_session

        session, cookie = _get_authenticated_session(
            base_url=base_url,
            login=inlabs_conn.login,
            password=inlabs_conn.password,
            session_factory=session_factory,
            max_attempts=3,
            sleep_fn=sleep_fn,
        )
        headers = {
            "User-Agent": _USER_AGENT,
            "Cookie": f"inlabs_session_cookie={cookie}; origem=736372697074",
        }
        grouped = _discover_inlabs_pdf_links(session, base_url, date_iso, headers)
    except InlabsMaintenanceError as exc:
        logger.info("INLABS em manutenção ao arquivar PDF (%s): %s", date_iso, exc)
        return None
    except Exception as exc:
        logger.warning("Falha no INLABS para PDF (%s), usando fallback: %s", date_iso, exc)
        return None

    saved: List[str] = []
    errors: List[str] = []
    any_found = False

    for sec in sections:
        links = grouped.get(sec, [])
        if not links:
            continue
        any_found = True
        for idx, href in enumerate(links):
            suffix = None if (sec != "extra" or idx == 0) else chr(ord("A") + idx)
            target = build_pdf_target_path(base_folder, date_iso, sec, extra_suffix=suffix)
            if is_valid_pdf_file(target):
                continue
            dl_url = urljoin(base_url, f"index.php{href}" if href.startswith("?") else href)
            try:
                resp = _request_with_retries(
                    session, "GET", dl_url, headers=headers, timeout=120, sleep_fn=sleep_fn
                )
                if not is_valid_pdf_bytes(resp.content):
                    raise PdfArchiverError(f"PDF inválido recebido do INLABS ({dl_url}).")
                _atomic_write_pdf(target, resp.content)
                saved.append(str(target))
            except Exception as exc:
                errors.append(f"Seção {sec} (INLABS): {exc}")

    if not any_found:
        return None

    return {
        "source": "inlabs",
        "saved": saved,
        "errors": errors,
    }


def _discover_pesquisa_total_pages(
    session: requests.Session,
    date_br: str,
    jornal_code: int,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Consulta ``visualiza/index.jsp`` e retorna ``totalArquivos`` (0 se não houver edição)."""
    url = (
        f"{_PESQUISA_BASE_URL}jsp/visualiza/index.jsp"
        f"?data={date_br}&jornal={jornal_code}&pagina=1"
    )
    resp = _request_with_retries(
        session,
        "GET",
        url,
        headers={"User-Agent": _USER_AGENT},
        timeout=25,
        max_retries=3,
        sleep_fn=sleep_fn,
    )
    m = re.search(r"totalArquivos=(\d+)", resp.text)
    return int(m.group(1)) if m else 0


def _download_pesquisa_page(
    session: Any,
    date_br: str,
    jornal_code: int,
    page_num: int,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> bytes:
    """Baixa uma única página em PDF certificado do ``INPDFViewer`` com retries."""
    url = (
        f"{_PESQUISA_BASE_URL}servlet/INPDFViewer"
        f"?jornal={jornal_code}&pagina={page_num}&data={date_br}&captchafield=firstAccess"
    )
    resp = _request_with_retries(
        session,
        "GET",
        url,
        headers={"User-Agent": _USER_AGENT},
        timeout=35,
        max_retries=3,
        sleep_fn=sleep_fn,
    )
    if not resp.content.lstrip()[:8].startswith(b"%PDF"):
        raise PdfArchiverError(
            f"Resposta não-PDF na página {page_num} (jornal={jornal_code}, data={date_br})."
        )
    return resp.content


def _assemble_pdf_from_pages(pages_map: Dict[int, bytes], total_pages: int) -> bytes:
    """Une páginas PDF individuais em um único documento PDF válido, liberando memória."""
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for p in range(1, total_pages + 1):
        page_data = pages_map.pop(p)
        reader = PdfReader(io.BytesIO(page_data), strict=False)
        for page in reader.pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _archive_section_via_pesquisa(
    date_iso: str,
    date_br: str,
    jornal_code: int,
    target_path: Path,
    *,
    session_factory: Callable[[], requests.Session] = requests.Session,
    max_workers: int = 4,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Optional[Path]:
    """Baixa e monta o PDF integral de uma seção via ``pesquisa.in.gov.br``."""
    discovery_session = session_factory()
    try:
        total_pages = _discover_pesquisa_total_pages(
            discovery_session, date_br, jornal_code, sleep_fn=sleep_fn
        )
    finally:
        if hasattr(discovery_session, "close"):
            try:
                discovery_session.close()
            except Exception:
                pass
    if total_pages <= 0:
        return None

    thread_local = threading.local()
    created_sessions: List[Any] = []
    sessions_lock = threading.Lock()

    def _get_worker_session():
        sess = getattr(thread_local, "session", None)
        if sess is None:
            sess = session_factory()
            thread_local.session = sess
            with sessions_lock:
                created_sessions.append(sess)
        return sess

    def _worker_download(p_num: int) -> bytes:
        return _download_pesquisa_page(
            _get_worker_session(), date_br, jornal_code, p_num, sleep_fn=sleep_fn
        )

    pages_map: Dict[int, bytes] = {}
    workers = max(1, min(max_workers, total_pages))
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {
                pool.submit(_worker_download, p): p for p in range(1, total_pages + 1)
            }
            for future in as_completed(future_map):
                p_num = future_map[future]
                pages_map[p_num] = future.result()
    finally:
        for sess in created_sessions:
            if hasattr(sess, "close"):
                try:
                    sess.close()
                except Exception:
                    pass

    merged = _assemble_pdf_from_pages(pages_map, total_pages)
    if not is_valid_pdf_bytes(merged):
        raise PdfArchiverError(
            f"PDF montado inválido para jornal={jornal_code} em {date_iso}."
        )
    _atomic_write_pdf(target_path, merged)
    return target_path


def archive_date_pdfs(
    raw_date: str,
    *,
    folder: Optional[Path | str] = None,
    sections: Optional[Iterable[Any]] = None,
    prefer_inlabs: bool = True,
    session_factory: Callable[[], requests.Session] = requests.Session,
    max_workers: int = 4,
    sleep_fn: Callable[[float], None] = time.sleep,
    record_status: bool = True,
) -> Dict[str, Any]:
    """Arquiva os PDFs integrais do DOU para uma data específica de forma idempotente."""
    global _ARCHIVE_RUNNING

    date_iso = normalize_date_iso(raw_date)
    date_br = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    cfg = get_pdf_archive_config()
    base_folder = Path(folder) if folder is not None else Path(cfg["folder"])
    base_folder.mkdir(parents=True, exist_ok=True)
    target_sections = normalize_sections(sections if sections is not None else cfg["sections"])

    saved_files: List[str] = []
    skipped_files: List[str] = []
    errors: List[str] = []
    missing_sections: List[str] = []

    with _ARCHIVE_LOCK:
        _ARCHIVE_RUNNING = True
        try:
            # 1. Verifica idempotência: o que já existe e é válido é pulado
            for sec in target_sections:
                if sec != "extra":
                    target = build_pdf_target_path(base_folder, date_iso, sec)
                    if is_valid_pdf_file(target):
                        skipped_files.append(str(target))
                    else:
                        missing_sections.append(sec)
                else:
                    target_extra = build_pdf_target_path(base_folder, date_iso, "extra")
                    if is_valid_pdf_file(target_extra):
                        skipped_files.append(str(target_extra))
                    else:
                        missing_sections.append("extra")

            used_source = "cache" if not missing_sections else "pesquisa.in.gov.br"

            # 2. Tenta fonte principal (INLABS) para as seções faltantes
            if missing_sections and prefer_inlabs:
                inlabs_res = _try_archive_via_inlabs(
                    date_iso,
                    missing_sections,
                    base_folder,
                    session_factory=session_factory,
                    sleep_fn=sleep_fn,
                )
                if inlabs_res is not None:
                    used_source = "inlabs"
                    saved_files.extend(inlabs_res["saved"])
                    errors.extend(inlabs_res["errors"])
                    still_missing: List[str] = []
                    for sec in missing_sections:
                        target = build_pdf_target_path(base_folder, date_iso, sec)
                        if not is_valid_pdf_file(target):
                            still_missing.append(sec)
                    missing_sections = still_missing

            # 3. Fallback (ou fonte padrão se INLABS indisponível): pesquisa.in.gov.br
            if missing_sections:
                used_source = "pesquisa.in.gov.br" if not saved_files else "inlabs+pesquisa.in.gov.br"
                for sec in missing_sections:
                    jornal_codes = _SECTION_TO_JORNAL.get(sec, ())
                    for idx, j_code in enumerate(jornal_codes):
                        suffix = None if (sec != "extra" or idx == 0) else chr(ord("A") + idx)
                        target = build_pdf_target_path(
                            base_folder, date_iso, sec, extra_suffix=suffix
                        )
                        if is_valid_pdf_file(target):
                            skipped_files.append(str(target))
                            continue
                        try:
                            res_path = _archive_section_via_pesquisa(
                                date_iso,
                                date_br,
                                j_code,
                                target,
                                session_factory=session_factory,
                                max_workers=max_workers,
                                sleep_fn=sleep_fn,
                            )
                            if res_path is not None:
                                saved_files.append(str(res_path))
                            elif sec == "extra":
                                # Sem mais edições extras nesta data
                                break
                        except Exception as exc:
                            errors.append(f"Seção {sec} (jornal {j_code}): {exc}")
                            if sec == "extra":
                                break

            if errors and not saved_files and not skipped_files:
                status = "error"
                msg = f"Falha ao arquivar PDFs de {date_br}: {errors[0]}"
            elif not saved_files and not skipped_files:
                status = "empty"
                msg = f"Nenhuma edição publicada em {date_br} (fim de semana ou feriado)."
            elif saved_files:
                status = "success"
                msg = (
                    f"{len(saved_files)} PDF(s) salvo(s) e {len(skipped_files)} já existente(s) "
                    f"para {date_br} (fonte: {used_source})."
                )
            else:
                status = "skipped"
                msg = f"Todos os {len(skipped_files)} PDF(s) de {date_br} já estavam arquivados."

            result = {
                "status": status,
                "date": date_iso,
                "date_br": date_br,
                "source": used_source,
                "folder": str(base_folder),
                "saved_files": saved_files,
                "skipped_files": skipped_files,
                "errors": errors,
                "message": msg,
                "last_run_at": datetime.now(_BRASILIA_TZ).strftime("%d/%m/%Y %H:%M:%S"),
            }

            if record_status:
                _save_pdf_archive_status(
                    {
                        "last_run_at": result["last_run_at"],
                        "last_date": date_br,
                        "last_source": used_source,
                        "last_status": status,
                        "last_message": msg,
                        "saved_files": saved_files,
                        "skipped_files": skipped_files,
                        "errors": errors,
                    }
                )
                link_mentions_to_pdfs(date_iso=date_iso, folder=base_folder)

            return result
        finally:
            _ARCHIVE_RUNNING = False


def archive_month_pdfs(
    year: int,
    month: int,
    *,
    folder: Optional[Path | str] = None,
    sections: Optional[Iterable[Any]] = None,
    prefer_inlabs: bool = True,
    session_factory: Callable[[], requests.Session] = requests.Session,
    max_workers: int = 4,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    """Arquiva os PDFs de todos os dias úteis de um mês até a data atual."""
    _, last_day = calendar.monthrange(year, month)
    today_dt = datetime.now(_BRASILIA_TZ).date()

    saved_all: List[str] = []
    skipped_all: List[str] = []
    errors_all: List[str] = []
    sources_used: List[str] = []
    processed_days = 0

    try:
        from ..services.holiday_service import is_holiday
    except Exception:
        is_holiday = None

    for day in range(1, last_day + 1):
        d_obj = date(year, month, day)
        if d_obj > today_dt:
            break
        if d_obj.weekday() >= 5:
            continue
        d_iso = d_obj.strftime("%Y-%m-%d")
        if is_holiday is not None:
            try:
                if is_holiday(d_iso):
                    continue
            except Exception:
                pass

        res = archive_date_pdfs(
            d_iso,
            folder=folder,
            sections=sections,
            prefer_inlabs=prefer_inlabs,
            session_factory=session_factory,
            max_workers=max_workers,
            sleep_fn=sleep_fn,
            record_status=False,
        )
        processed_days += 1
        saved_all.extend(res["saved_files"])
        skipped_all.extend(res["skipped_files"])
        errors_all.extend(res["errors"])
        if res.get("source") and res["source"] not in sources_used:
            sources_used.append(res["source"])

    base_folder = Path(folder) if folder is not None else Path(get_pdf_archive_config()["folder"])
    link_mentions_to_pdfs(folder=base_folder)

    month_label = f"{str(month).zfill(2)}/{year}"
    msg = (
        f"Mês {month_label}: {len(saved_all)} PDF(s) salvo(s), "
        f"{len(skipped_all)} já existente(s), {len(errors_all)} erro(s)."
    )
    status = "error" if (errors_all and not saved_all and not skipped_all) else "success"
    now_str = datetime.now(_BRASILIA_TZ).strftime("%d/%m/%Y %H:%M:%S")
    source_summary = "+".join(sources_used) if sources_used else "cache"
    _save_pdf_archive_status(
        {
            "last_run_at": now_str,
            "last_date": month_label,
            "last_source": source_summary,
            "last_status": status,
            "last_message": msg,
            "saved_files": saved_all,
            "skipped_files": skipped_all,
            "errors": errors_all,
        }
    )
    return {
        "status": status,
        "month": month_label,
        "processed_days": processed_days,
        "saved_files": saved_all,
        "skipped_files": skipped_all,
        "errors": errors_all,
        "message": msg,
    }


def resolve_pdf_for_mention(
    raw_date: Optional[str],
    raw_section: Optional[str],
    *,
    folder: Optional[Path | str] = None,
) -> Optional[str]:
    """Localiza no disco o PDF do dia correspondente à menção (se existir e for válido)."""
    if not raw_date or str(raw_date).strip() in ("", "N/A"):
        return None
    try:
        date_iso = normalize_date_iso(str(raw_date))
    except ValueError:
        return None

    sec_key = normalize_section_key(raw_section) or "1"
    base_folder = Path(folder) if folder is not None else Path(get_pdf_archive_config()["folder"])
    candidate = build_pdf_target_path(base_folder, date_iso, sec_key)
    if candidate.is_file() and candidate.stat().st_size >= 128:
        return str(candidate)
    return None


def link_mentions_to_pdfs(
    *,
    date_iso: Optional[str] = None,
    folder: Optional[Path | str] = None,
) -> int:
    """Atualiza ``Mention.pdf_path`` no SQLite para menções cujo PDF do dia exista no disco."""
    updated = 0
    try:
        from ..models import Mention, db
        from ..services.mention_service import clear_mentions_cache

        query = Mention.query
        if date_iso:
            date_br = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
            query = query.filter(Mention.data.in_([date_br, date_iso]))

        mentions = query.all()
        for m in mentions:
            resolved = resolve_pdf_for_mention(m.data, m.secao, folder=folder)
            if resolved and m.pdf_path != resolved:
                m.pdf_path = resolved
                updated += 1
        if updated:
            db.session.commit()
            clear_mentions_cache()
    except Exception as exc:
        logger.debug("Falha ao vincular menções a PDFs: %s", exc)
    return updated
