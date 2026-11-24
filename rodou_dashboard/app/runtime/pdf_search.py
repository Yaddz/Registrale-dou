"""Fonte alternativa ao INLABS: texto do PDF integral do DOU.

Quando o INLABS não tem a edição do dia (portal em manutenção, carga com
falha, Postgres portátil indisponível), o runner usa esta fonte no lugar de
pesquisar um banco vazio:

1. garante os PDFs integrais do dia (os mesmos que o arquivamento do
   Sprint 5 salva na pasta do analista; ``pesquisa.in.gov.br`` não exige
   login e funciona com o INLABS fora do ar);
2. extrai o texto página a página (com cache) e procura cada empresa pela
   raiz do CNPJ com a regra única de ``src/utils/cnpj.py``;
3. confirma na API do DOU apenas as empresas encontradas, para gravar o link
   e o título da matéria como no fluxo normal. Se a API falhar ou não achar,
   a menção é gravada com o link da página no visualizador oficial.

Nada em ``src/`` é alterado; o formato devolvido é o mesmo do XCom de
``exec_search_N`` (``{"single_group": {termo: {departamento: [pub]}}}``).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

FALLBACK_PDF = "pdf"
FALLBACK_API = "api"
FALLBACK_OFF = "off"
_VALID_MODES = {FALLBACK_PDF, FALLBACK_API, FALLBACK_OFF}

_VIEWER_URL = (
    "https://pesquisa.in.gov.br/imprensa/jsp/visualiza/index.jsp"
    "?data={date_br}&jornal={jornal}&pagina={page}"
)
_SECTION_LABEL = {
    "1": "DOU - Seção 1",
    "2": "DOU - Seção 2",
    "3": "DOU - Seção 3",
    "extra": "DOU - Edição Extra",
}
_BASE_JORNAL = {"1": 515, "2": 529, "3": 530, "extra": 600}
_FILE_RE = re.compile(r"^DOU_(\d{4}-\d{2}-\d{2})_Secao(1|2|3|Extra)(?:_([A-Z]))?\.pdf$")
_ACT_RE = re.compile(
    r"^\s*((?:RESOLUÇÃO|PORTARIA|DESPACHO|EXTRATO|AVISO|DECISÃO|ATO|EDITAL|ACÓRDÃO|"
    r"INSTRUÇÃO NORMATIVA|DELIBERAÇÃO|RETIFICAÇÃO|ARESTO|AUTO|ALVARÁ|CONSULTA PÚBLICA)"
    r"[^\n]{0,140})$",
    re.MULTILINE,
)
_HIGHLIGHT = "<span class='highlight' style='background:#FFA;'>{}</span>"
_ABSTRACT_RADIUS = 350


# ─── Configuração ────────────────────────────────────────────────────────────


def get_fallback_mode() -> str:
    """Fonte usada quando o INLABS não tem o dia: ``pdf`` (padrão), ``api`` ou ``off``."""
    env = (os.getenv("REGISTRALE_INLABS_FALLBACK") or "").strip().lower()
    if env in _VALID_MODES:
        return env
    try:
        from ..models import Settings

        rec = Settings.query.filter_by(key="global_settings").first()
        val = rec.get_value() if rec else None
        mode = str((val or {}).get("inlabs_fallback") or "").strip().lower()
        if mode in _VALID_MODES:
            return mode
    except Exception:
        pass
    return FALLBACK_PDF


def inlabs_has_date(reference_date: date) -> bool:
    """True se o banco do INLABS já tem matérias da data (mesma checagem do painel)."""
    try:
        from ..services.inlabs_service import is_date_loaded

        loaded, _count = is_date_loaded(reference_date.strftime("%Y-%m-%d"))
        return bool(loaded)
    except Exception as exc:  # sem app context, sem Postgres etc.
        logger.info("Não foi possível checar o INLABS para %s: %s", reference_date, exc)
        return False


def section_keys_from_dou_sections(dou_sections: Optional[Iterable[Any]]) -> List[str]:
    """Converte ``SECAO_1``/``EDICAO_EXTRA``... (YAML) em ``1``/``2``/``3``/``extra``."""
    from .pdf_archiver import normalize_section_key

    keys: List[str] = []
    for raw in dou_sections or []:
        key = normalize_section_key(raw)
        if key and key not in keys:
            keys.append(key)
    return keys or ["1", "2", "3", "extra"]


# ─── PDFs e texto ────────────────────────────────────────────────────────────


def _pdf_folder() -> Path:
    """Pasta do arquivamento (se ligado) ou cache interno em ``<dados>/pdf_cache``."""
    from .pdf_archiver import get_pdf_archive_config
    from .paths import get_data_dir

    cfg = get_pdf_archive_config()
    if cfg.get("enabled", True):
        return Path(cfg["folder"])
    folder = get_data_dir() / "pdf_cache"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def ensure_day_pdfs(
    date_iso: str,
    section_keys: List[str],
    *,
    layout: Optional[str] = None,
) -> Tuple[List[Tuple[str, int, Path]], List[str]]:
    """Baixa (se preciso) os PDFs do dia e devolve ``[(seção, jornal, caminho)]`` e erros."""
    from .pdf_archiver import (
        DEFAULT_LAYOUT,
        archive_date_pdfs,
        build_pdf_target_path,
        get_pdf_archive_config,
        normalize_pdf_layout,
    )

    cfg = get_pdf_archive_config()
    enabled = cfg.get("enabled", True)
    folder = _pdf_folder()
    active_layout = (
        normalize_pdf_layout(layout if layout is not None else cfg.get("layout"))
        if enabled
        else DEFAULT_LAYOUT
    )

    res = archive_date_pdfs(date_iso, folder=folder, sections=section_keys, layout=active_layout)
    errors = list(res.get("errors") or [])

    candidate_dirs: List[Path] = []
    for sec in section_keys:
        parent_dir = build_pdf_target_path(folder, date_iso, sec, layout=active_layout).parent
        if parent_dir not in candidate_dirs:
            candidate_dirs.append(parent_dir)

    seen_paths: set[Path] = set()
    files: List[Tuple[str, int, Path]] = []
    for day_dir in candidate_dirs:
        if not day_dir.is_dir():
            continue
        for path in sorted(day_dir.iterdir()):
            if path in seen_paths:
                continue
            m = _FILE_RE.match(path.name)
            if not m or m.group(1) != date_iso:
                continue
            sec = "extra" if m.group(2) == "Extra" else m.group(2)
            if sec not in section_keys:
                continue
            seen_paths.add(path)
            jornal = _BASE_JORNAL[sec]
            if sec == "extra" and m.group(3):
                jornal += ord(m.group(3)) - ord("A")
            files.append((sec, jornal, path))
    if res.get("status") == "error" and not files:
        raise RuntimeError(res.get("message") or "Falha ao obter os PDFs do DOU.")
    return files, errors


def _text_cache_path(pdf_path: Path) -> Path:
    from .paths import get_data_dir

    st = pdf_path.stat()
    key = hashlib.sha1(f"{pdf_path.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:20]
    cache_dir = get_data_dir() / "pdf_text"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{pdf_path.stem}_{key}.json.gz"


def extract_pages_text(pdf_path: Path) -> List[str]:
    """Texto de cada página do PDF (cache gzip em ``<dados>/pdf_text``)."""
    cache = _text_cache_path(pdf_path)
    if cache.is_file():
        try:
            with gzip.open(cache, "rt", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass

    from pypdf import PdfReader

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(str(pdf_path), strict=False)
    pages: List[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:
            logger.warning("Falha ao extrair texto de %s: %s", pdf_path.name, exc)
            pages.append("")

    tmp = cache.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(pages, fh, ensure_ascii=False)
    os.replace(tmp, cache)
    return pages


def normalize_page_text(text: str) -> str:
    """Achata espaços e remove quebras dentro de números (``0001-\\n36`` → ``0001-36``)."""
    flat = re.sub(r"\s+", " ", text or "")
    return re.sub(r"(?<=\d) ?([./-]) ?(?=\d)", r"\1", flat)


def _guess_title(raw_page: str, flat_page: str, match_pos: int) -> Optional[str]:
    """Último cabeçalho de ato (RESOLUÇÃO-RE Nº ..., PORTARIA ...) antes da menção."""
    prefix = flat_page[:match_pos]
    best = None
    for m in _ACT_RE.finditer(raw_page or ""):
        head = re.sub(r"\s+", " ", m.group(1)).strip()
        probe = head[:40]
        if probe and probe in prefix:
            best = head
    return best[:160] if best else None


def _build_abstract(flat: str, start: int, end: int, root_fmt: str) -> str:
    a = max(0, start - _ABSTRACT_RADIUS)
    b = min(len(flat), end + _ABSTRACT_RADIUS)
    snippet = flat[a:b]
    rel = start - a
    idx = snippet.find(root_fmt, rel)
    if idx == -1:
        idx = snippet.find(root_fmt)
    if idx != -1:
        snippet = snippet[:idx] + _HIGHLIGHT.format(root_fmt) + snippet[idx + len(root_fmt):]
    prefix = "..." if a > 0 else ""
    suffix = "..." if b < len(flat) else ""
    return f"{prefix}{snippet.strip()}{suffix}"


def scan_pages_for_terms(
    pages: List[str],
    terms: Iterable[str],
) -> Dict[str, List[Dict[str, Any]]]:
    """Procura cada termo CNPJ (pela raiz) nas páginas; devolve ``{termo: [ocorrência]}``."""
    _ensure_src_path()
    from utils.cnpj import cnpj_root, find_company_mentions, format_root

    roots: Dict[str, Tuple[str, str]] = {}
    for term in terms:
        root = cnpj_root(term)
        if root:
            roots[str(term)] = (root, format_root(root))

    hits: Dict[str, List[Dict[str, Any]]] = {}
    for page_no, raw in enumerate(pages, start=1):
        flat = normalize_page_text(raw)
        for term, (root, root_fmt) in roots.items():
            if root_fmt not in flat and root not in flat:
                continue
            found = find_company_mentions(flat, root)
            if not found:
                continue
            pos = flat.find(found[0])
            if pos == -1:
                pos = flat.find(root_fmt)
            pos = max(pos, 0)
            hits.setdefault(term, []).append(
                {
                    "page": page_no,
                    "matched": found,
                    "abstract": _build_abstract(flat, pos, pos + len(found[0]), root_fmt),
                    "title": _guess_title(raw, flat, pos),
                    "root_only": "/" not in found[0],
                }
            )
    return hits


def _ensure_src_path() -> None:
    src = str(Path(__file__).resolve().parents[3] / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


# ─── Busca ───────────────────────────────────────────────────────────────────


def _pdf_publication(term: str, sec: str, jornal: int, date_iso: str, hit: Dict[str, Any]) -> Dict[str, Any]:
    date_br = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    label = _SECTION_LABEL[sec]
    return {
        "section": label,
        "title": hit.get("title") or f"{label} - página {hit['page']}",
        "href": _VIEWER_URL.format(date_br=date_br, jornal=jornal, page=hit["page"]),
        "abstract": hit["abstract"],
        "date": date_br,
        "id": f"pdf-{date_iso}-{jornal}-{hit['page']}",
        "matched_cnpj": hit["matched"][0],
        "root_only": hit["root_only"],
        "is_branch": False,
        "source": "pdf_dou",
        "pdf_page": hit["page"],
    }


def _pubs_by_term(api_result: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for group in (api_result or {}).values():
        if not isinstance(group, dict):
            continue
        for term, depts in group.items():
            if not isinstance(depts, dict):
                continue
            for pubs in depts.values():
                if isinstance(pubs, list):
                    out.setdefault(str(term), []).extend(p for p in pubs if isinstance(p, dict))
    return out


def search_day_via_pdf(
    terms: List[str],
    dou_sections: Optional[Iterable[Any]],
    reference_date: date,
    *,
    confirm_with_api: Optional[Callable[[List[str]], Dict[str, Any]]] = None,
    ensure_pdfs: Callable[[str, List[str]], Tuple[List[Tuple[str, int, Path]], List[str]]] = ensure_day_pdfs,
    extract_text: Callable[[Path], List[str]] = extract_pages_text,
) -> Tuple[Dict[str, Any], List[str]]:
    """Busca os termos no PDF integral do dia.

    Retorna ``(resultado no formato XCom, seções que falharam)``. As seções
    com falha de download devem ser cobertas pela API do DOU pelo chamador.
    """
    date_iso = reference_date.strftime("%Y-%m-%d")
    section_keys = section_keys_from_dou_sections(dou_sections)
    files, errors = ensure_pdfs(date_iso, section_keys)

    present = {sec for sec, _j, _p in files}
    failed_sections = [
        sec for sec in section_keys
        if sec not in present and any(e.startswith(f"Seção {sec} ") for e in errors)
    ]

    pdf_pubs: Dict[str, List[Dict[str, Any]]] = {}
    for sec, jornal, path in files:
        pages = extract_text(path)
        for term, occurrences in scan_pages_for_terms(pages, terms).items():
            for hit in occurrences:
                pdf_pubs.setdefault(term, []).append(_pdf_publication(term, sec, jornal, date_iso, hit))

    logger.info(
        "Busca no PDF integral de %s: %d arquivo(s), %d empresa(s) encontrada(s).",
        date_iso, len(files), len(pdf_pubs),
    )

    final: Dict[str, List[Dict[str, Any]]] = {}
    if pdf_pubs and confirm_with_api is not None:
        try:
            api_pubs = _pubs_by_term(confirm_with_api(sorted(pdf_pubs)))
        except Exception as exc:
            logger.warning("Confirmação na API do DOU falhou (%s); usando links do PDF.", exc)
            api_pubs = {}
        for term, pubs in pdf_pubs.items():
            final[term] = api_pubs.get(term) or pubs
    else:
        final = pdf_pubs

    result = {"single_group": {t: {"single_department": p} for t, p in final.items() if p}}
    return result, failed_sections
