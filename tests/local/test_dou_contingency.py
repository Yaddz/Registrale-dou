"""Rotina de fonte DOU com o portal fora do ar: contingência pelo PDF integral e pendências."""

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

from app.runtime.dou_resilient import DouPortalUnavailable  # noqa: E402
from app.runtime.runner import load_specs, run_search_block  # noqa: E402

DAY = date(2026, 11, 26)
A = "24684423000136"
B = "00097446000186"
C = "07021336000180"


@pytest.fixture(autouse=True)
def _pdf_mode(monkeypatch):
    monkeypatch.setenv("REGISTRALE_INLABS_FALLBACK", "pdf")


def _dou_specs(terms=(A, B, C)):
    return load_specs({
        "dag": {
            "id": "pesquisa_cnpj",
            "description": "teste",
            "schedule": None,
            "search": [{
                "header": "SINCRONIZAÇÃO AUTOMÁTICA - PARTE 1",
                "terms": list(terms),
                "dou_sections": ["SECAO_1", "SECAO_3"],
                "date": "DIA",
                "force_rematch": True,
            }],
            "report": {"emails": [], "subject": "t"},
        }
    })


def _pub(pid):
    return {"id": pid, "date": "26/11/2026", "title": "t", "href": "h", "abstract": "a", "section": "do1"}


class _FakeDOU:
    """Buscador da API: ``outcomes`` = sequência de respostas por chamada de ``exec_search``.

    Cada resposta é ``(resultado, failed_terms)`` ou uma exceção.
    """

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.failed_terms = []

    def exec_search(self, **kwargs):
        self.calls.append(kwargs)
        self.failed_terms = []
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, BaseException):
            raise outcome
        result, failed = outcome
        self.failed_terms = list(failed)
        return result


def _pdf(result=None, failed_sections=(), exc=None, seen=None):
    def fake_pdf(terms, sections, ref, confirm_with_api):
        if seen is not None:
            seen.append(list(terms))
        if exc:
            raise exc
        return result or {}, list(failed_sections)

    return fake_pdf


def _statuses(out):
    return {c["section"]: c["status"] for c in out["coverage"]}


def test_run_block_breaker_uses_pdf_and_reports_covered(caplog):
    specs = _dou_specs()
    partial = {"single_group": {A: {"single_department": [_pub("api-1")]}}}
    down = DouPortalUnavailable("ReadTimeout: 35 s", 3, failed_terms=[B, C], partial_result=partial)
    seen = []
    pdf_res = {"single_group": {C: {"single_department": [_pub("pdf-7")]}}}
    out = run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": _FakeDOU(down, ({}, [])), "INLABS_FALLBACK": _pdf(pdf_res, seen=seen),
    })
    assert seen == [[B, C]]  # só o que a API não respondeu
    group = out["result"]["single_group"]
    assert group[A]["single_department"][0]["id"] == "api-1"
    assert group[C]["single_department"][0]["id"] == "pdf-7"
    assert out["source_used"] == "API do DOU + PDF integral"
    assert _statuses(out) == {"SECAO_1": "coberta", "SECAO_3": "coberta"}
    assert out["incomplete"] is False
    assert "usando contingência PDF integral" in caplog.text


def test_run_block_breaker_and_pdf_failure_returns_pending_without_exception():
    specs = _dou_specs()
    down = DouPortalUnavailable("HTTPError: 502 Bad Gateway", 3, failed_terms=[A, B, C])
    out = run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": _FakeDOU(down), "INLABS_FALLBACK": _pdf(exc=RuntimeError("pesquisa.in.gov.br fora")),
    })
    assert out["result"] == {}
    assert _statuses(out) == {"SECAO_1": "pendente", "SECAO_3": "pendente"}
    assert out["incomplete"] is True
    assert "502" in out["coverage"][0]["detail"]


def test_run_block_contingency_off_marks_pending_with_reason(monkeypatch):
    monkeypatch.setenv("REGISTRALE_INLABS_FALLBACK", "off")
    specs = _dou_specs()
    down = DouPortalUnavailable("ReadTimeout: 35 s", 3, failed_terms=[A, B, C])
    out = run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": _FakeDOU(down), "INLABS_FALLBACK": lambda *a, **k: pytest.fail("contingência desligada"),
    })
    assert _statuses(out) == {"SECAO_1": "pendente", "SECAO_3": "pendente"}
    detail = out["coverage"][0]["detail"]
    assert detail.startswith("Portal do DOU indisponível: ReadTimeout: 35 s")
    assert "3 CNPJ(s) sem resposta do portal" in detail
    assert out["source_used"] == "API do DOU"


def test_run_block_isolated_failure_sends_only_failed_terms_to_pdf_and_merges():
    specs = _dou_specs()
    api_res = {"single_group": {A: {"single_department": [_pub("api-1")]}}}
    pdf_res = {"single_group": {B: {"single_department": [_pub("pdf-2")]}}}
    seen = []
    dou = _FakeDOU((api_res, [B]), ({}, []))
    out = run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": dou, "INLABS_FALLBACK": _pdf(pdf_res, seen=seen),
    })
    assert seen == [[B]]
    assert dou.calls[0]["term_list"] == [A, B, C]
    group = out["result"]["single_group"]
    assert set(group) == {A, B}
    assert out["source_used"] == "API do DOU + PDF integral"
    assert _statuses(out) == {"SECAO_1": "coberta", "SECAO_3": "coberta"}


def test_run_block_isolated_failure_without_answer_lists_terms_in_pending():
    specs = _dou_specs()
    api_res = {"single_group": {A: {"single_department": [_pub("api-1")]}}}
    # PDF sem a Seção 3 e a API, ao completar, também cai.
    dou = _FakeDOU((api_res, [B, C]), DouPortalUnavailable("ReadTimeout: 35 s", 3, failed_terms=[B, C]))
    out = run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": dou, "INLABS_FALLBACK": _pdf({}, failed_sections=["3"]),
    })
    assert out["result"]["single_group"][A]["single_department"][0]["id"] == "api-1"
    assert _statuses(out) == {"SECAO_1": "coberta", "SECAO_3": "pendente"}
    pending = next(c for c in out["coverage"] if c["section"] == "SECAO_3")
    assert pending["detail"].startswith(f"2 CNPJ(s) sem resposta do portal: {B}, {C}")


def test_run_block_network_error_without_breaker_does_not_raise(monkeypatch):
    monkeypatch.setenv("REGISTRALE_INLABS_FALLBACK", "off")
    specs = _dou_specs()
    out = run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": _FakeDOU(requests.exceptions.ConnectionError("recusada")),
        "INLABS_FALLBACK": _pdf(),
    })
    assert out["incomplete"] is True
    assert "ConnectionError" in out["coverage"][0]["detail"]


def test_run_block_api_ok_keeps_api_source_and_coverage():
    specs = _dou_specs()
    out = run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": _FakeDOU(({"single_group": {}}, [])),
        "INLABS_FALLBACK": lambda *a, **k: pytest.fail("API respondeu: PDF não é necessário"),
    })
    assert out["source_used"] == "API do DOU"
    assert _statuses(out) == {"SECAO_1": "coberta", "SECAO_3": "coberta"}


def test_run_block_more_than_five_unanswered_terms_truncates_list(monkeypatch):
    monkeypatch.setenv("REGISTRALE_INLABS_FALLBACK", "off")
    terms = [f"{i:02d}.111.222/0001-{i:02d}" for i in range(7)]
    specs = _dou_specs(terms)
    down = DouPortalUnavailable("ReadTimeout", 3, failed_terms=terms)
    out = run_search_block(specs, specs.search[0], DAY, searchers={"DOU": _FakeDOU(down), "INLABS_FALLBACK": _pdf()})
    assert "7 CNPJ(s) sem resposta do portal" in out["coverage"][0]["detail"]
    assert out["coverage"][0]["detail"].endswith("e mais 2")


def test_executor_block_pending_by_portal_down_finishes_partial(tmp_path, monkeypatch):
    from app import create_app
    from app.models import JobRun, db
    from app.runtime.executor import LocalExecutor

    monkeypatch.setenv("REGISTRALE_INLABS_FALLBACK", "off")
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'exec.db'}",
        "WTF_CSRF_ENABLED": False,
    })
    with app.app_context():
        db.create_all()
    down = DouPortalUnavailable("ReadTimeout: 35 s", 3, failed_terms=[A])
    executor = LocalExecutor(app=app, max_workers=1, searchers={"DOU": _FakeDOU(down), "INLABS_FALLBACK": _pdf()})
    yaml_dict = {
        "dag": {
            "id": "pesquisa_cnpj", "description": "t", "schedule": None,
            "search": [{"header": "P1", "terms": [A], "dou_sections": ["SECAO_1"], "date": "DIA", "sources": ["DOU"]}],
            "report": {"emails": [], "subject": "t"},
        }
    }
    with app.app_context():
        run_id = executor.trigger(yaml_dict, date="2026-11-26")
        finished, states = executor.wait([run_id], timeout=10)
        assert finished is True
        assert states[run_id] == "partial"
        job = db.session.get(JobRun, run_id)
        assert job.status == "partial"
        assert "Seção 1" in (job.erro or "")
    executor.shutdown(wait=True)
