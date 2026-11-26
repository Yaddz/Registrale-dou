"""Geração de PDF com a página destacada do DOU para cada menção.

Extrai apenas a página do PDF integral arquivado em que a empresa aparece
(usando a regra de raiz de CNPJ de ``src/utils/cnpj.py``) e acrescenta
anotações ``Highlight`` do ``pypdf`` nas ocorrências encontradas.
"""

from __future__ import annotations

from datetime import datetime
import logging
import os
from pathlib import Path
import re
import sys
import threading
from typing import Any, List, Optional, Tuple

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Highlight
from pypdf.generic import ArrayObject, FloatObject

logger = logging.getLogger(__name__)


def _ensure_src_utils() -> None:
    src_dir = str(Path(__file__).resolve().parents[3] / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)


def _sanitize_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return cleaned.strip("._") or "mencao"


def _normalize_date_iso_safe(raw_date: Optional[str]) -> str:
    s = str(raw_date or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return "sem-data"


def _collect_highlight_rects(page: Any, pattern: re.Pattern[str]) -> List[Tuple[float, float, float, float]]:
    """Usa ``extract_text(visitor_text=...)`` para estimar caixas ao redor das ocorrências."""
    rects: List[Tuple[float, float, float, float]] = []
    media_box = getattr(page, "mediabox", None)
    page_w = float(media_box.width) if media_box is not None else 595.0
    page_h = float(media_box.height) if media_box is not None else 842.0

    def _visitor(text: str, cm: Any, tm: Any, _font_dict: Any, font_size: float) -> None:
        if not text or not pattern.search(text):
            return
        try:
            tx = float(tm[4]) if tm and len(tm) >= 6 else 40.0
            ty = float(tm[5]) if tm and len(tm) >= 6 else 400.0
            if cm and len(cm) >= 6:
                x = float(cm[0]) * tx + float(cm[2]) * ty + float(cm[4])
                y = float(cm[1]) * tx + float(cm[3]) * ty + float(cm[5])
            else:
                x, y = tx, ty
            fs = float(font_size or 10.0)
            if fs <= 0:
                fs = 10.0
            width = max(80.0, min(page_w - 20.0, len(text.strip()) * fs * 0.52))
            x1 = max(0.0, min(page_w - 10.0, x - 2.0))
            y1 = max(0.0, min(page_h - 10.0, y - 2.0))
            x2 = min(page_w, x1 + width + 4.0)
            y2 = min(page_h, y1 + fs + 4.0)
            if x2 > x1 and y2 > y1:
                rects.append((x1, y1, x2, y2))
        except Exception:
            return

    try:
        page.extract_text(visitor_text=_visitor)
    except Exception as exc:
        logger.debug("Falha ao extrair coordenadas de texto para destaque: %s", exc)
    return rects


def generate_highlight_pdf_for_mention(
    mention_id: str,
    cnpj: Optional[str],
    date_str: Optional[str],
    section_str: Optional[str],
    source_pdf_path: Optional[str] = None,
    pdf_folder: Optional[Path] = None,
) -> Optional[str]:
    """Gera `<pasta_pdfs>/destaques/<AAAA-MM-DD>/<raiz>_<id>.pdf` e retorna o caminho.

    Retorna ``None`` se não houver PDF integral arquivado ou se o CNPJ não for
    localizado nas páginas do arquivo.
    """
    _ensure_src_utils()
    from utils.cnpj import cnpj_root, company_regex, find_company_mentions
    from .pdf_archiver import get_pdf_archive_config, resolve_pdf_for_mention
    from .pdf_search import extract_pages_text, normalize_page_text

    root = cnpj_root(cnpj or "")
    if not root:
        return None

    base_folder = Path(pdf_folder) if pdf_folder is not None else Path(get_pdf_archive_config()["folder"])

    resolved_source: Optional[Path] = None
    if source_pdf_path and os.path.isfile(source_pdf_path):
        resolved_source = Path(source_pdf_path)
    else:
        found = resolve_pdf_for_mention(date_str or "", section_str or "1", folder=base_folder)
        if found and os.path.isfile(found):
            resolved_source = Path(found)

    if resolved_source is None:
        return None

    try:
        pages_text = extract_pages_text(resolved_source)
    except Exception as exc:
        logger.warning("Não foi possível ler páginas de %s: %s", resolved_source, exc)
        return None

    target_page_idx: Optional[int] = None
    for idx, page_text in enumerate(pages_text):
        flat_page = normalize_page_text(page_text or "")
        if find_company_mentions(flat_page, root):
            target_page_idx = idx
            break

    if target_page_idx is None:
        return None

    reader = PdfReader(str(resolved_source))
    if target_page_idx >= len(reader.pages):
        return None

    page = reader.pages[target_page_idx]
    writer = PdfWriter()
    writer.add_page(page)

    pattern = company_regex(root)
    for x1, y1, x2, y2 in _collect_highlight_rects(page, pattern):
        quad = ArrayObject([
            FloatObject(x1), FloatObject(y2),
            FloatObject(x2), FloatObject(y2),
            FloatObject(x1), FloatObject(y1),
            FloatObject(x2), FloatObject(y1),
        ])
        writer.add_annotation(
            page_number=0,
            annotation=Highlight(rect=(x1, y1, x2, y2), quad_points=quad, highlight_color="fff066"),
        )

    iso_date = _normalize_date_iso_safe(date_str)
    out_dir = base_folder / "destaques" / iso_date
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{root}_{_sanitize_filename_part(mention_id)}.pdf"
    tmp_path = out_path.with_suffix(".pdf.tmp")
    with open(tmp_path, "wb") as fh:
        writer.write(fh)
    os.replace(tmp_path, out_path)
    return str(out_path)


def generate_highlights_for_ids(app: Any, mention_ids: List[str]) -> int:
    """Processa uma lista de IDs de menções e atualiza ``highlight_pdf_path`` no SQLite."""
    if not mention_ids:
        return 0
    from ..models import Mention, db

    generated = 0
    with app.app_context():
        for mid in mention_ids:
            try:
                mention = db.session.get(Mention, mid)
                if not mention:
                    continue
                if mention.highlight_pdf_path and os.path.isfile(mention.highlight_pdf_path):
                    continue
                out_path = generate_highlight_pdf_for_mention(
                    mention_id=mention.id,
                    cnpj=mention.cnpj_norm or mention.cnpj,
                    date_str=mention.data,
                    section_str=mention.secao,
                    source_pdf_path=mention.pdf_path,
                )
                if out_path:
                    mention.highlight_pdf_path = out_path
                    db.session.commit()
                    generated += 1
            except Exception as exc:
                db.session.rollback()
                logger.warning("Erro ao gerar página destacada para menção %s: %s", mid, exc)
    return generated


def schedule_highlight_generation(app: Any, mention_ids: List[str]) -> None:
    """Dispara a geração das páginas destacadas em segundo plano, sem atrasar o e-mail."""
    ids = [str(mid) for mid in (mention_ids or []) if mid]
    if not ids or app is None:
        return
    threading.Thread(
        target=generate_highlights_for_ids,
        args=(app, ids),
        daemon=True,
    ).start()
