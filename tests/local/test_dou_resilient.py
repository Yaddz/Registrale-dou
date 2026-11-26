"""Testes do buscador da API do DOU com limite por termo e circuit breaker."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = REPO_ROOT / "rodou_dashboard"
for p in (REPO_ROOT, DASHBOARD_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.runtime import dou_resilient  # noqa: E402
from app.runtime.dou_resilient import DouPortalUnavailable, ResilientDOUSearcher  # noqa: E402

DAY = date(2026, 11, 26)
CNPJ_A = "24684423000136"
CNPJ_B = "00097446000186"
CNPJ_C = "07021336000180"
CNPJ_D = "11222333000181"
ROOT = {CNPJ_A: "24.684.423", CNPJ_B: "00.097.446", CNPJ_C: "07.021.336", CNPJ_D: "11.222.333"}


class _FakeHook:
    """``search_text`` falso: ``plan[consulta]`` é uma lista de respostas (exceção ou lista)."""

    def __init__(self, plan):
        self.plan = {k: list(v) for k, v in plan.items()}
        self.calls = []

    def search_text(self, search_term, **_kwargs):
        self.calls.append(search_term)
        queue = self.plan.get(search_term) or [[]]
        outcome = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.fixture
def sleeps(monkeypatch):
    seen = []
    monkeypatch.setattr(dou_resilient.time, "sleep", lambda s: seen.append(s) if s else None)  # 0 = intervalo de raspagem zerado
    monkeypatch.setattr(ResilientDOUSearcher, "SCRAPPING_INTERVAL", 0)
    for name in ("REGISTRALE_DOU_TERM_RETRIES", "REGISTRALE_DOU_TERM_RETRY_SLEEP", "REGISTRALE_DOU_BREAKER"):
        monkeypatch.delenv(name, raising=False)
    return seen


def _searcher(monkeypatch, plan):
    searcher = ResilientDOUSearcher()
    hook = _FakeHook(plan)
    monkeypatch.setattr(searcher, "dou_hook", hook)
    return searcher, hook


def _run(searcher, terms):
    return searcher.exec_search(
        term_list=terms,
        dou_sections=["SECAO_1"],
        search_date="DIA",
        field="TUDO",
        is_exact_search=True,
        ignore_signature_match=False,
        force_rematch=True,
        department=[],
        department_ignore=[],
        terms_ignore=[],
        pubtype=[],
        reference_date=DAY,
    )


def test_search_isolated_failure_returns_empty_and_records_term(monkeypatch, sleeps):
    timeout = requests.exceptions.ReadTimeout("35 s")
    searcher, hook = _searcher(monkeypatch, {ROOT[CNPJ_A]: [timeout]})
    out = _run(searcher, [CNPJ_A, CNPJ_B])
    assert not out.get("single_group")
    assert searcher.failed_terms == [CNPJ_A]
    assert hook.calls == [ROOT[CNPJ_A], ROOT[CNPJ_A], ROOT[CNPJ_B]]  # 1 nova tentativa só
    assert sleeps == [10.0]
    assert searcher.consecutive_failures == 0  # o sucesso de B zerou o contador


def test_search_three_consecutive_failures_raise_portal_unavailable(monkeypatch, sleeps):
    err = requests.exceptions.HTTPError("502 Server Error: Bad Gateway")
    searcher, hook = _searcher(monkeypatch, {ROOT[c]: [err] for c in (CNPJ_A, CNPJ_B, CNPJ_C, CNPJ_D)})
    with pytest.raises(DouPortalUnavailable) as info:
        _run(searcher, [CNPJ_A, CNPJ_B, CNPJ_C, CNPJ_D])
    assert "502" in str(info.value)
    assert info.value.failed_terms == [CNPJ_A, CNPJ_B, CNPJ_C]
    assert ROOT[CNPJ_D] not in hook.calls  # parou antes do 4º CNPJ
    assert len(hook.calls) == 6


def test_search_success_resets_consecutive_counter(monkeypatch, sleeps):
    err = requests.exceptions.ConnectionError("recusada")
    plan = {ROOT[CNPJ_A]: [err], ROOT[CNPJ_B]: [err], ROOT[CNPJ_C]: [[]], ROOT[CNPJ_D]: [err]}
    searcher, _hook = _searcher(monkeypatch, plan)
    _run(searcher, [CNPJ_A, CNPJ_B, CNPJ_C, CNPJ_D])  # 2 falhas, sucesso, 1 falha: não abre o breaker
    assert searcher.failed_terms == [CNPJ_A, CNPJ_B, CNPJ_D]
    assert searcher.consecutive_failures == 1


def test_exec_search_new_call_resets_failed_terms_and_counter(monkeypatch, sleeps):
    err = requests.exceptions.ReadTimeout("35 s")
    searcher, hook = _searcher(monkeypatch, {ROOT[CNPJ_A]: [err], ROOT[CNPJ_B]: [err]})
    _run(searcher, [CNPJ_A, CNPJ_B])
    assert searcher.consecutive_failures == 2
    hook.plan = {}
    _run(searcher, [CNPJ_C])
    assert searcher.failed_terms == []
    assert searcher.consecutive_failures == 0


def test_search_ssl_error_without_retry(monkeypatch, sleeps):
    ssl = requests.exceptions.SSLError("certificado inválido")
    searcher, hook = _searcher(monkeypatch, {ROOT[CNPJ_A]: [ssl]})
    _run(searcher, [CNPJ_A])
    assert hook.calls == [ROOT[CNPJ_A]]
    assert sleeps == []
    assert searcher.failed_terms == [CNPJ_A]


def test_search_env_configures_retries_sleep_and_breaker(monkeypatch, sleeps):
    monkeypatch.setenv("REGISTRALE_DOU_TERM_RETRIES", "0")
    monkeypatch.setenv("REGISTRALE_DOU_TERM_RETRY_SLEEP", "3")
    monkeypatch.setenv("REGISTRALE_DOU_BREAKER", "1")
    err = requests.exceptions.ReadTimeout("35 s")
    searcher, hook = _searcher(monkeypatch, {ROOT[CNPJ_A]: [err]})
    with pytest.raises(DouPortalUnavailable):
        _run(searcher, [CNPJ_A, CNPJ_B])
    assert hook.calls == [ROOT[CNPJ_A]]
    assert sleeps == []


def test_search_retry_success_returns_results(monkeypatch, sleeps):
    item = {"abstract": "Empresa CNPJ 24.684.423/0001-36", "section": "do1", "hierarchyStr": "", "arttype": "Portaria",
            "title": "t", "href": "h", "date": "26/11/2026", "id": "1", "hierarchyList": []}
    err = requests.exceptions.ReadTimeout("35 s")
    searcher, hook = _searcher(monkeypatch, {ROOT[CNPJ_A]: [err, [item]]})
    out = _run(searcher, [CNPJ_A])
    assert hook.calls == [ROOT[CNPJ_A], ROOT[CNPJ_A]]
    assert searcher.failed_terms == []
    assert CNPJ_A in out["single_group"]


def test_default_searchers_use_resilient_dou():
    from app.runtime.runner import _build_default_searchers

    assert isinstance(_build_default_searchers()["DOU"], ResilientDOUSearcher)
