"""Executor de buscas em memória usando o núcleo `src/` sem Airflow.

Reproduz os argumentos e o formato de retorno (XCom de `exec_search_N`)
de `DouDigestDagGenerator.perform_searches`.
"""

from __future__ import annotations

import ast
import logging
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


class NoMonitoredCompanies(ValueError):
    """Rotina sem termos de busca (nenhuma empresa monitorada)."""


NO_COMPANIES_MESSAGE = "Nenhuma empresa monitorada: sincronize a planilha ou o GestãoClick."


def routine_has_no_terms(yaml_source: Union[str, Path, Dict[str, Any]]) -> bool:
    """True se todos os blocos de busca têm ``terms`` vazio e nenhum outro critério.

    Esse é o estado da rotina principal antes da primeira sincronização; o
    Pydantic o rejeitaria com um erro técnico.
    """
    import yaml as _yaml

    try:
        if isinstance(yaml_source, dict):
            data = yaml_source
        else:
            with open(os.fspath(yaml_source), "r", encoding="utf-8") as fh:
                data = _yaml.safe_load(fh) or {}
        blocks = (data.get("dag") or {}).get("search") or []
        if isinstance(blocks, dict):
            blocks = [blocks]
    except Exception:
        return False
    if not blocks:
        return True  # rotina sem nenhum bloco de busca
    return all(
        isinstance(b, dict)
        and "terms" in b
        and isinstance(b.get("terms"), list)
        and not [t for t in b["terms"] if t]
        and not b.get("department")
        and not b.get("pubtype")
        for b in blocks
    )


def _expand_organ_filters_in_memory(data: Dict[str, Any]) -> Dict[str, Any]:
    """Expande siglas de órgão em `dag.search[].department` em memória sem alterar o YAML em disco."""
    import copy
    from ..services.organ_aliases import expand_organ_filters

    dag_section = data.get("dag")
    if not isinstance(dag_section, dict):
        return data
    search = dag_section.get("search")
    if not search:
        return data

    cloned = copy.deepcopy(data)
    blocks = cloned["dag"]["search"]
    if isinstance(blocks, dict):
        if blocks.get("department"):
            blocks["department"] = expand_organ_filters(blocks["department"])
    elif isinstance(blocks, list):
        for block in blocks:
            if isinstance(block, dict) and block.get("department"):
                block["department"] = expand_organ_filters(block["department"])
    return cloned


def load_specs(yaml_source: Union[str, Path, Dict[str, Any]]) -> Any:
    """Carrega um arquivo YAML ou dicionário em memória para `DAGConfig`."""
    _ensure_src_imports()
    from parsers import YAMLParser
    from schemas import RoDouConfig

    if isinstance(yaml_source, dict):
        data = yaml_source
    else:
        data = YAMLParser(os.fspath(yaml_source)).read()
    expanded = _expand_organ_filters_in_memory(data) if isinstance(data, dict) else data
    return RoDouConfig(**expanded).dag


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
    from searchers import DOESPSearcher, INLABSSearcher, QDSearcher

    from .dou_resilient import ResilientDOUSearcher
    from .pdf_search import search_day_via_pdf

    return {
        # Limite de tempo por CNPJ e parada antecipada com o portal fora (ver dou_resilient.py)
        "DOU": ResilientDOUSearcher(),
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


_SECTION_LABELS = {
    "1": ("SECAO_1", "Seção 1"),
    "2": ("SECAO_2", "Seção 2"),
    "3": ("SECAO_3", "Seção 3"),
    "extra": ("EDICAO_EXTRA", "Edição Extra"),
}
_SECTION_KEY_BY_NAME = {name: key for key, (name, _label) in _SECTION_LABELS.items()}


def _coverage_entry(key: str, status: str, source: str, detail: str = "") -> Dict[str, str]:
    """Linha de cobertura de uma seção: ``status`` = coberta | sem_edicao | pendente."""
    name, label = _SECTION_LABELS.get(key, (key, key))
    return {"section": name, "label": label, "status": status, "source": source, "detail": detail}


def _api_coverage(keys: List[str], source: str, error: Optional[str] = None) -> List[Dict[str, str]]:
    if error:
        return [_coverage_entry(k, "pendente", source, f"API do DOU falhou: {error}") for k in keys]
    return [_coverage_entry(k, "coberta", source) for k in keys]


def _accepted_kwargs(fn: Any) -> Optional[set]:
    """Nomes de parâmetros nomeados que ``fn`` aceita; ``None`` se aceita ``**kwargs`` (tudo)."""
    import inspect

    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return None
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params):
        return None
    return {p.name for p in params if p.kind in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)}


def _run_inlabs_fallback(
    subsearch: Any,
    term_list: Any,
    reference_date: date,
    active_searchers: Dict[str, Any],
) -> tuple[Dict[str, Any], str, List[Dict[str, str]], List[str]]:
    """PDF integral do dia (confirmado na API) ou, se configurado/necessário, só a API.

    Retorna ``(resultado_xcom, fonte_efetiva, cobertura_por_seção, avisos)``. Seção que
    nenhuma fonte cobriu aparece como ``pendente`` (a execução termina "com pendências").
    """
    import logging

    from .pdf_search import FALLBACK_API, get_fallback_mode, search_day_via_pdf, section_keys_from_dou_sections

    log = logging.getLogger(__name__)
    terms = _parse_term_list(term_list)
    terms = [terms] if isinstance(terms, str) else list(terms or [])
    dou = active_searchers["DOU"]
    pdf_search = active_searchers.get("INLABS_FALLBACK", search_day_via_pdf)
    if not callable(pdf_search):
        pdf_search = search_day_via_pdf
    all_keys = section_keys_from_dou_sections(subsearch.dou_sections)

    date_spec = str(getattr(subsearch.date, "value", subsearch.date) or "DIA").upper()
    if get_fallback_mode() == FALLBACK_API or date_spec != "DIA":
        log.info("INLABS sem %s: buscando via API do DOU.", reference_date)
        try:
            result = _dou_api_search(subsearch, terms, reference_date, dou)
        except Exception as exc:
            log.error("API do DOU falhou em %s: %s", reference_date, exc)
            return {}, "API do DOU", _api_coverage(all_keys, "API do DOU", str(exc)), []
        return result, "API do DOU", _api_coverage(all_keys, "API do DOU"), []

    report: Dict[str, Any] = {}
    pdf_kwargs: Dict[str, Any] = {
        "confirm_with_api": lambda hit_terms: _dou_api_search(subsearch, hit_terms, reference_date, dou),
        "report": report,
        "strict_confirm": bool(subsearch.department),
    }
    # Buscador injetado (testes) pode não aceitar ``report``/``strict_confirm``: confere a
    # assinatura em vez de capturar TypeError, que também vem de dentro do PDF (ex.: arquivo corrompido).
    accepted = _accepted_kwargs(pdf_search)
    if accepted is not None:
        pdf_kwargs = {k: v for k, v in pdf_kwargs.items() if k in accepted}
    try:
        result, failed_sections = pdf_search(
            terms,
            subsearch.dou_sections,
            reference_date,
            **pdf_kwargs,
        )
    except Exception as exc:
        log.warning("PDF integral de %s indisponível (%s): buscando via API do DOU.", reference_date, exc)
        try:
            result = _dou_api_search(subsearch, terms, reference_date, dou)
        except Exception as api_exc:
            log.error("API do DOU também falhou em %s: %s", reference_date, api_exc)
            return {}, "API do DOU", _api_coverage(all_keys, "API do DOU", str(api_exc)), []
        return result, "API do DOU", _api_coverage(all_keys, "API do DOU"), []

    sections_report = report.get("sections") or {}
    coverage: List[Dict[str, str]] = []
    for key in all_keys:
        info = sections_report.get(key)
        if key in failed_sections:
            continue  # decidido abaixo, conforme a API cobrir ou não
        if info and info.get("status") == "ausente":
            coverage.append(_coverage_entry(key, "sem_edicao", "PDF integral", info.get("detail", "")))
        else:
            coverage.append(_coverage_entry(key, "coberta", "PDF integral"))

    if failed_sections:
        missing = [_SECTION_LABELS[s][0] for s in failed_sections if s in _SECTION_LABELS]
        log.warning("PDF de %s sem as seções %s: completando via API do DOU.", reference_date, missing)
        try:
            api_part = _dou_api_search(subsearch, terms, reference_date, dou, dou_sections=missing)
            result = _merge_term_results(result, api_part)
            for key in failed_sections:
                info = sections_report.get(key) or {}
                why = info.get("detail", "")
                if info.get("provisional"):
                    # Hoje, seção ainda sem PDF: a API responder vazio não prova "sem menções",
                    # a edição pode não ter sido publicada. Fica pendente (nova tentativa no dia).
                    coverage.append(_coverage_entry(
                        key, "pendente", "API do DOU",
                        "cobertura provisória pela API: a edição pode não ter sido publicada ainda",
                    ))
                else:
                    coverage.append(_coverage_entry(key, "coberta", "API do DOU", f"PDF sem a seção ({why})" if why else ""))
        except Exception as exc:
            log.error("API do DOU também falhou para %s em %s: %s", missing, reference_date, exc)
            for key in failed_sections:
                why = (sections_report.get(key) or {}).get("detail", "")
                coverage.append(_coverage_entry(key, "pendente", "API do DOU", f"{why}; API do DOU falhou: {exc}"))
    coverage.sort(key=lambda c: list(_SECTION_KEY_BY_NAME).index(c["section"]) if c["section"] in _SECTION_KEY_BY_NAME else 99)
    source = "PDF integral + API do DOU"
    return result, source, coverage, list(report.get("notes") or [])


def _dou_contingency_enabled(active_searchers: Dict[str, Any]) -> bool:
    """Mesma condição de ``_use_inlabs_fallback``, sem perguntar se o INLABS tem o dia."""
    if "INLABS_FALLBACK" not in active_searchers:
        return False
    from .pdf_search import FALLBACK_OFF, get_fallback_mode

    return get_fallback_mode() != FALLBACK_OFF


def _unanswered_detail(terms: List[str]) -> str:
    shown = ", ".join(terms[:5])
    more = f" e mais {len(terms) - 5}" if len(terms) > 5 else ""
    return f"{len(terms)} CNPJ(s) sem resposta do portal: {shown}{more}"


def _run_dou_with_contingency(
    subsearch: Any,
    term_list: Any,
    reference_date: date,
    active_searchers: Dict[str, Any],
) -> tuple[Dict[str, Any], str, List[Dict[str, str]], List[str]]:
    """Rotina de fonte DOU: API do DOU e, para o que ela não respondeu, o PDF integral.

    * Portal fora (``DouPortalUnavailable`` ou erro de rede que escapou do buscador): os termos
      sem resposta vão para ``_run_inlabs_fallback`` (PDF integral do dia).
    * Falhas isoladas (``failed_terms``): só esses termos vão ao PDF; o resultado é mesclado.
    * Contingência desligada ou também sem resposta: nenhuma exceção; as seções do bloco ficam
      ``pendente`` com o motivo (execução "com pendências" e nova tentativa automática).

    Retorna ``(resultado_xcom, fonte_efetiva, cobertura_por_seção, avisos)``.
    """
    import requests

    from .dou_resilient import DouPortalUnavailable
    from .pdf_search import section_keys_from_dou_sections

    log = logging.getLogger(__name__)
    keys = section_keys_from_dou_sections(subsearch.dou_sections)
    dou = active_searchers["DOU"]
    portal_error = ""
    try:
        result = dou.exec_search(
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
        unanswered = [str(t) for t in (getattr(dou, "failed_terms", None) or [])]
    except DouPortalUnavailable as exc:
        result = exc.partial_result or {}
        portal_error = exc.last_error or str(exc)
        unanswered = [str(t) for t in exc.failed_terms]
    except requests.exceptions.RequestException as exc:
        # Rede de segurança: buscador sem o breaker (ou erro fora da busca por termo).
        result = {}
        portal_error = f"{type(exc).__name__}: {exc}"
        unanswered = []
    if portal_error and not unanswered:
        parsed = _parse_term_list(term_list)
        unanswered = [parsed] if isinstance(parsed, str) else [str(t) for t in (parsed or [])]

    if not portal_error and not unanswered:
        return result, "API do DOU", _api_coverage(keys, "API do DOU"), []

    reason = _unanswered_detail(unanswered) if unanswered else ""
    if portal_error:
        reason = f"Portal do DOU indisponível: {portal_error}" + (f"; {reason}" if reason else "")

    if not unanswered or not _dou_contingency_enabled(active_searchers):
        if portal_error:
            log.error("API do DOU indisponível (%s) e contingência desligada: seções pendentes.", portal_error)
        else:
            log.warning("%s; contingência desligada: seções pendentes.", reason)
        return result, "API do DOU", [_coverage_entry(k, "pendente", "API do DOU", reason) for k in keys], []

    if portal_error:
        log.warning("API do DOU indisponível (%s): usando contingência PDF integral.", portal_error)
    else:
        log.warning("%s: usando contingência PDF integral para esses termos.", reason)
    fb_result, fb_source, fb_coverage, notes = _run_inlabs_fallback(
        subsearch, unanswered, reference_date, active_searchers
    )
    result = _merge_term_results(result, fb_result)
    source = " + ".join(dict.fromkeys(["API do DOU", *fb_source.split(" + ")]))
    still_failed = [str(t) for t in (getattr(dou, "failed_terms", None) or [])]
    if fb_source == "API do DOU" and still_failed:
        # Contingência sem PDF (modo ``api`` ou PDF fora) e a API de novo sem resposta.
        detail = "; ".join(d for d in (reason, _unanswered_detail(still_failed)) if d)
        return result, source, [_coverage_entry(k, "pendente", source, detail) for k in keys], notes

    by_section = {c.get("section"): c for c in fb_coverage}
    coverage: List[Dict[str, str]] = []
    for key in keys:
        fb = by_section.get(_SECTION_LABELS.get(key, (key, key))[0]) or {}
        status = fb.get("status") or "pendente"
        if status == "pendente":
            detail = "; ".join(d for d in (reason, fb.get("detail", "")) if d)
            coverage.append(_coverage_entry(key, "pendente", fb.get("source") or source, detail))
        elif status == "sem_edicao":
            coverage.append(_coverage_entry(key, "sem_edicao", fb.get("source") or source, fb.get("detail", "")))
        else:
            coverage.append(_coverage_entry(key, "coberta", source, fb.get("detail", "")))
    return result, source, coverage, notes


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
    if isinstance(term_list, list) and not term_list:
        # Lista de termos explícita e vazia (ex.: rotina principal antes da
        # primeira sincronização). Para o upstream "sem termos" significa
        # "todas as publicações do órgão", o que gravaria cada ato da ANVISA
        # como menção. `terms` ausente (None) segue a regra do upstream.
        logging.getLogger(__name__).info(
            "Bloco '%s' sem termos de busca: busca pulada.", subsearch.header
        )
        return {
            "result": {},
            "header": subsearch.header,
            "department": subsearch.department,
            "department_ignore": subsearch.department_ignore,
            "pubtype": subsearch.pubtype,
            "source_used": "",
        }
    result_as_email = bool(not (specs.report.discord or specs.report.slack))

    dou_result: Dict[str, Any] = {}
    inlabs_result: Dict[str, Any] = {}
    qd_result: Dict[str, Any] = {}
    doesp_result: Dict[str, Any] = {}
    sources_used: List[str] = []
    coverage: List[Dict[str, str]] = []
    notes: List[str] = []

    if "DOU" in sources:
        dou_result, dou_source, coverage, notes = _run_dou_with_contingency(
            subsearch, term_list, reference_date, active_searchers
        )
        sources_used.append(dou_source)
    elif "INLABS" in sources and _use_inlabs_fallback(subsearch, reference_date, searchers):
        inlabs_result, fallback_source, coverage, notes = _run_inlabs_fallback(
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
        from .pdf_search import section_keys_from_dou_sections
        coverage = _api_coverage(section_keys_from_dou_sections(subsearch.dou_sections), "INLABS")

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
        "coverage": coverage,
        "notes": notes,
        "incomplete": any(c.get("status") == "pendente" for c in coverage),
    }


def run_routine(
    yaml_source: Union[str, Path, Dict[str, Any]],
    execution_date: Union[date, datetime, str, None] = None,
    searchers: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Executa todos os blocos `search` de uma rotina e retorna os resultados XCom."""
    if routine_has_no_terms(yaml_source):
        raise NoMonitoredCompanies(NO_COMPANIES_MESSAGE)
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
