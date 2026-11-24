"""Executor de buscas em memória usando o núcleo `src/` sem Airflow.

Reproduz os argumentos e o formato de retorno (XCom de `exec_search_N`)
de `DouDigestDagGenerator.perform_searches`.
"""

from __future__ import annotations

import ast
from datetime import date, datetime, timedelta, timezone
from functools import reduce
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Union

_BRASILIA_TZ = timezone(timedelta(hours=-3))
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_DIR = _REPO_ROOT / "src"


def _ensure_src_imports() -> None:
    """Garante o shim do Airflow (se necessário) e os caminhos de `src/`."""
    repo_str = str(_REPO_ROOT)
    src_str = str(_SRC_DIR)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)

    try:
        from compat.bootstrap import install_airflow_shim
        install_airflow_shim()
    except ImportError:
        pass

    # O upstream importa `ro_dou_src.*` (nome do pacote dentro do Airflow).
    # Fora do Airflow e do pytest esse pacote não existe: cria o alias para `src/`.
    if "ro_dou_src" not in sys.modules:
        import importlib.util
        import types

        if importlib.util.find_spec("ro_dou_src") is None:
            pkg = types.ModuleType("ro_dou_src")
            pkg.__path__ = [src_str]
            sys.modules["ro_dou_src"] = pkg


def parse_reference_date(execution_date: Union[date, datetime, str, None]) -> date:
    """Converte a data de execução para `datetime.date`."""
    if execution_date is None:
        return datetime.now(_BRASILIA_TZ).date()
    if isinstance(execution_date, datetime):
        return execution_date.date()
    if isinstance(execution_date, date):
        return execution_date

    raw = str(execution_date).strip()
    if not raw:
        return datetime.now(_BRASILIA_TZ).date()

    raw_date = raw.split("T")[0].split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw_date, fmt).date()
        except ValueError:
            continue
    return date.fromisoformat(raw_date)


def _merge_results(*dicts: Dict[str, Any]) -> Dict[str, Any]:
    """Mescla dicionários de resultados de busca (mesma lógica do gerador)."""

    def merge_two(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        all_keys = set(dict1) | set(dict2)
        for key in all_keys:
            value1 = dict1.get(key)
            value2 = dict2.get(key)
            if isinstance(value1, dict) and isinstance(value2, dict):
                merged[key] = _merge_results(value1, value2)
            elif isinstance(value1, dict) or isinstance(value2, dict):
                merged[key] = value1 if isinstance(value1, dict) else value2
            else:
                merged[key] = value1 + value2
        return merged

    filtered = []
    for d in dicts:
        if d:
            first_key = next(iter(d))
            if d.get(first_key):
                filtered.append(d)

    if not filtered:
        return {}
    return reduce(merge_two, filtered)


def _parse_term_list(term_list: Any) -> Any:
    """Converte `term_list` serializado em lista, quando aplicável."""
    if not isinstance(term_list, str):
        return term_list
    cleaned = term_list.strip()
    for _ in range(2):
        if cleaned.startswith(("[", '"[', "'[")):
            try:
                parsed = ast.literal_eval(cleaned)
                if isinstance(parsed, list):
                    return parsed
            except (ValueError, SyntaxError):
                break
    return cleaned


def load_specs(yaml_source: Union[str, Path, Dict[str, Any]]) -> Any:
    """Carrega um arquivo YAML ou dicionário em memória para `DAGConfig`."""
    _ensure_src_imports()
    from parsers import YAMLParser
    from schemas import RoDouConfig

    if isinstance(yaml_source, dict):
        return RoDouConfig(**yaml_source).dag
    return YAMLParser(os.fspath(yaml_source)).parse()


def _resolve_terms(subsearch: Any) -> Any:
    """Resolve `subsearch.terms` (lista, None, variável ou consulta SQL)."""
    _ensure_src_imports()
    from schemas import FetchTermsConfig
    from utils.select_terms import TermSelector

    if subsearch.terms is None:
        return None
    if isinstance(subsearch.terms, list):
        return subsearch.terms

    term_selector = TermSelector()
    if isinstance(subsearch.terms, FetchTermsConfig):
        if getattr(subsearch.terms, "from_airflow_variable", None):
            return term_selector.select_terms_from_airflow_variable(
                variable=subsearch.terms.from_airflow_variable
            )
        if getattr(subsearch.terms, "from_db_select", None):
            return term_selector.select_terms_from_db(
                sql=subsearch.terms.from_db_select.sql,
                conn_id=subsearch.terms.from_db_select.conn_id,
            )
    return subsearch.terms


def _build_default_searchers() -> Dict[str, Any]:
    _ensure_src_imports()
    from searchers import DOESPSearcher, DOUSearcher, INLABSSearcher, QDSearcher

    from .pdf_search import search_day_via_pdf

    return {
        "DOU": DOUSearcher(),
        "QD": QDSearcher(),
        "INLABS": INLABSSearcher(),
        "DOESP": DOESPSearcher(),
        # Fonte usada quando o INLABS não tem o dia (ver runtime/pdf_search.py)
        "INLABS_FALLBACK": search_day_via_pdf,
    }


def _use_inlabs_fallback(
    subsearch: Any,
    reference_date: date,
    searchers: Optional[Dict[str, Any]],
) -> bool:
    """INLABS sem a edição do dia → usa a fonte alternativa em vez de um banco vazio.

    Só vale quando ``INLABS_FALLBACK`` está entre os buscadores (os padrão o
    incluem); testes que injetam buscadores falsos sem ele mantêm o comportamento.
    """
    if searchers is None or "INLABS_FALLBACK" not in searchers:
        return False
    from .pdf_search import FALLBACK_OFF, get_fallback_mode, inlabs_has_date

    if get_fallback_mode() == FALLBACK_OFF:
        return False
    if "INLABS_HAS_DATE" in searchers:
        return not searchers["INLABS_HAS_DATE"](reference_date)
    return not inlabs_has_date(reference_date)


def _dou_api_search(subsearch: Any, terms: Any, reference_date: date, searcher: Any, dou_sections: Any = None) -> Dict[str, Any]:
    """Busca na API do DOU com os mesmos argumentos do bloco (sempre com rematch)."""
    return searcher.exec_search(
        term_list=terms,
        dou_sections=dou_sections if dou_sections is not None else subsearch.dou_sections,
        search_date=subsearch.date,
        field=subsearch.field,
        is_exact_search=subsearch.is_exact_search,
        ignore_signature_match=subsearch.ignore_signature_match,
        force_rematch=True,
        department=subsearch.department,
        department_ignore=subsearch.department_ignore,
        terms_ignore=subsearch.terms_ignore,
        pubtype=subsearch.pubtype,
        reference_date=reference_date,
    )


def _merge_term_results(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    """Junta ``{grupo: {termo: {depto: [pub]}}}`` sem duplicar publicações (por ``id``)."""
    merged: Dict[str, Any] = {g: {t: {d: list(p) for d, p in depts.items()} for t, depts in terms.items()}
                              for g, terms in (base or {}).items() if isinstance(terms, dict)}
    for group, terms in (extra or {}).items():
        if not isinstance(terms, dict):
            continue
        g = merged.setdefault(group, {})
        for term, depts in terms.items():
            if not isinstance(depts, dict):
                continue
            t = g.setdefault(term, {})
            for dept, pubs in depts.items():
                current = t.setdefault(dept, [])
                seen = {p.get("id") for p in current if isinstance(p, dict)}
                current.extend(p for p in pubs or [] if isinstance(p, dict) and p.get("id") not in seen)
    return merged


def _run_inlabs_fallback(
    subsearch: Any,
    term_list: Any,
    reference_date: date,
    active_searchers: Dict[str, Any],
) -> tuple[Dict[str, Any], str]:
    """PDF integral do dia (confirmado na API) ou, se configurado/necessário, só a API.

    Retorna ``(resultado_xcom, fonte_efetiva)``.
    """
    import logging

    from .pdf_search import FALLBACK_API, get_fallback_mode, search_day_via_pdf

    log = logging.getLogger(__name__)
    terms = _parse_term_list(term_list)
    terms = [terms] if isinstance(terms, str) else list(terms or [])
    dou = active_searchers["DOU"]
    pdf_search = active_searchers.get("INLABS_FALLBACK", search_day_via_pdf)
    if not callable(pdf_search):
        pdf_search = search_day_via_pdf

    date_spec = str(getattr(subsearch.date, "value", subsearch.date) or "DIA").upper()
    if get_fallback_mode() == FALLBACK_API or date_spec != "DIA":
        log.info("INLABS sem %s: buscando via API do DOU.", reference_date)
        return _dou_api_search(subsearch, terms, reference_date, dou), "API do DOU"

    try:
        result, failed_sections = pdf_search(
            terms,
            subsearch.dou_sections,
            reference_date,
            confirm_with_api=lambda hit_terms: _dou_api_search(subsearch, hit_terms, reference_date, dou),
        )
    except Exception as exc:
        log.warning("PDF integral de %s indisponível (%s): buscando via API do DOU.", reference_date, exc)
        return _dou_api_search(subsearch, terms, reference_date, dou), "API do DOU"

    if failed_sections:
        section_map = {"1": "SECAO_1", "2": "SECAO_2", "3": "SECAO_3", "extra": "EDICAO_EXTRA"}
        missing = [section_map[s] for s in failed_sections if s in section_map]
        log.warning("PDF de %s sem as seções %s: completando via API do DOU.", reference_date, missing)
        try:
            api_part = _dou_api_search(subsearch, terms, reference_date, dou, dou_sections=missing)
            result = _merge_term_results(result, api_part)
        except Exception as exc:
            log.error("API do DOU também falhou para %s em %s: %s", missing, reference_date, exc)
    return result, "PDF integral + API do DOU"


def run_search_block(
    specs: Any,
    subsearch: Any,
    reference_date: date,
    searchers: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Executa um único bloco `search` e retorna o dicionário no formato XCom."""
    active_searchers = searchers if searchers is not None else _build_default_searchers()

    sources = subsearch.sources
    term_list = _resolve_terms(subsearch)
    result_as_email = bool(not (specs.report.discord or specs.report.slack))

    dou_result: Dict[str, Any] = {}
    inlabs_result: Dict[str, Any] = {}
    qd_result: Dict[str, Any] = {}
    doesp_result: Dict[str, Any] = {}
    sources_used: List[str] = []

    if "DOU" in sources:
        dou_result = active_searchers["DOU"].exec_search(
            term_list=term_list,
            dou_sections=subsearch.dou_sections,
            search_date=subsearch.date,
            field=subsearch.field,
            is_exact_search=subsearch.is_exact_search,
            ignore_signature_match=subsearch.ignore_signature_match,
            force_rematch=subsearch.force_rematch,
            department=subsearch.department,
            department_ignore=subsearch.department_ignore,
            terms_ignore=subsearch.terms_ignore,
            pubtype=subsearch.pubtype,
            reference_date=reference_date,
        )
        sources_used.append("API do DOU")
    elif "INLABS" in sources and _use_inlabs_fallback(subsearch, reference_date, searchers):
        inlabs_result, fallback_source = _run_inlabs_fallback(
            subsearch, term_list, reference_date, active_searchers
        )
        sources_used.append(fallback_source)
    elif "INLABS" in sources:
        terms = _parse_term_list(term_list)
        inlabs_result = active_searchers["INLABS"].exec_search(
            ai_config=specs.ai_config,
            terms=terms,
            dou_sections=subsearch.dou_sections,
            search_date=subsearch.date,
            department=subsearch.department,
            department_ignore=subsearch.department_ignore,
            terms_ignore=subsearch.terms_ignore,
            ignore_signature_match=subsearch.ignore_signature_match,
            full_text=subsearch.full_text,
            text_length=subsearch.text_length,
            use_summary=subsearch.use_summary,
            ignore_attachments=subsearch.ignore_attachments,
            ignore_inline_tables=subsearch.ignore_inline_tables,
            min_table_rows=subsearch.min_table_rows,
            ai_search_config=subsearch.ai_search_config,
            show_relevancy=subsearch.show_relevancy,
            pubtype=subsearch.pubtype,
            reference_date=reference_date,
        )
        sources_used.append("INLABS")

    if "QD" in sources:
        qd_result = active_searchers["QD"].exec_search(
            territory_id=subsearch.territory_id,
            term_list=term_list,
            is_exact_search=subsearch.is_exact_search,
            reference_date=reference_date,
            excerpt_size=subsearch.excerpt_size,
            number_of_excerpts=subsearch.number_of_excerpts,
            result_as_email=result_as_email,
        )
        sources_used.append("QD")

    if "DOESP" in sources:
        doesp_result = active_searchers["DOESP"].exec_search(
            term_list=term_list,
            journals=subsearch.journals,
            search_date=subsearch.date,
            ignore_signature_match=subsearch.ignore_signature_match,
            force_rematch=subsearch.force_rematch,
            department=subsearch.department,
            department_ignore=subsearch.department_ignore,
            terms_ignore=subsearch.terms_ignore,
            pubtype=subsearch.pubtype,
            reference_date=reference_date,
        )
        sources_used.append("DOESP")

    if "DOU" in sources and "QD" in sources:
        result = _merge_results(qd_result, dou_result)
    elif "INLABS" in sources and "QD" in sources:
        result = _merge_results(qd_result, inlabs_result)
    elif "DOESP" in sources and "QD" in sources:
        result = _merge_results(qd_result, doesp_result)
    elif "DOU" in sources:
        result = dou_result
    elif "INLABS" in sources:
        result = inlabs_result
    elif "DOESP" in sources:
        result = doesp_result
    else:
        result = qd_result

    return {
        "result": result,
        "header": subsearch.header,
        "department": subsearch.department,
        "department_ignore": subsearch.department_ignore,
        "pubtype": subsearch.pubtype,
        "source_used": " + ".join(dict.fromkeys(sources_used)) if sources_used else "",
    }


def run_routine(
    yaml_source: Union[str, Path, Dict[str, Any]],
    execution_date: Union[date, datetime, str, None] = None,
    searchers: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Executa todos os blocos `search` de uma rotina e retorna os resultados XCom."""
    specs = load_specs(yaml_source)
    reference_date = parse_reference_date(execution_date)
    active_searchers = searchers if searchers is not None else _build_default_searchers()

    return [
        run_search_block(
            specs=specs,
            subsearch=subsearch,
            reference_date=reference_date,
            searchers=active_searchers,
        )
        for subsearch in specs.search
    ]
