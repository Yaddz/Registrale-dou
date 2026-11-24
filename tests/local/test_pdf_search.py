"""Testes offline da fonte alternativa ao INLABS (texto do PDF integral do DOU)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = REPO_ROOT / "rodou_dashboard"
for p in (REPO_ROOT, DASHBOARD_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.runtime import pdf_search  # noqa: E402
from app.runtime.pdf_search import (  # noqa: E402
    normalize_page_text,
    scan_pages_for_terms,
    search_day_via_pdf,
    section_keys_from_dou_sections,
)
from app.runtime.runner import load_specs, run_search_block  # noqa: E402

DAY = date(2026, 11, 3)
SURGITEC = "24684423000136"
BIO = "00097446000186"
OTHER = "07021336000180"

PAGE_1 = (
    "RESOLUÇÃO-RE Nº 4.264, DE 28 DE OUTUBRO DE 2026\n"
    "A GERENTE-GERAL ... resolve:\n"
    "Bio Engenharia e Indústria de Implantes Ortopédicos Ltda / 00.097.446/0001-86\n"
)
PAGE_2 = (
    "PORTARIA Nº 12, DE 1º DE NOVEMBRO DE 2026\n"
    "Surgitec Ltda CNPJ 24.684.423/0004-\n89 filial\n"
    "pagamento no valor de R$ 07.021.336,00 (sete milhões)\n"
)


@pytest.fixture(autouse=True)
def _pdf_mode(monkeypatch):
    monkeypatch.setenv("REGISTRALE_INLABS_FALLBACK", "pdf")


def test_normalize_joins_broken_numbers():
    assert normalize_page_text("24.684.423/0004-\n89") == "24.684.423/0004-89"
    assert normalize_page_text("Ltda /\n24.684.423 , a") == "Ltda / 24.684.423 , a"


def test_section_keys_from_yaml():
    assert section_keys_from_dou_sections(["SECAO_1", "SECAO_3", "EDICAO_EXTRA"]) == ["1", "3", "extra"]
    assert section_keys_from_dou_sections([]) == ["1", "2", "3", "extra"]


def test_scan_finds_full_branch_and_ignores_money():
    hits = scan_pages_for_terms([PAGE_1, PAGE_2], [SURGITEC, BIO, OTHER])
    assert set(hits) == {SURGITEC, BIO}
    assert hits[SURGITEC][0]["page"] == 2
    assert hits[SURGITEC][0]["matched"] == ["24.684.423/0004-89"]
    assert hits[BIO][0]["title"].startswith("RESOLUÇÃO-RE Nº 4.264")
    assert "<span class='highlight'" in hits[BIO][0]["abstract"]


def test_scan_root_only_anvisa_format():
    hits = scan_pages_for_terms(["Surgitec Ltda / 24.684.423, a sua"], [SURGITEC])
    assert hits[SURGITEC][0]["matched"] == ["24.684.423"]
    assert hits[SURGITEC][0]["root_only"] is True


def _fake_pdfs(files, errors=None):
    def _ensure(date_iso, sections):
        assert date_iso == "2026-11-03"
        return [(sec, jornal, Path(name)) for sec, jornal, name in files if sec in sections], errors or []
    return _ensure


def test_search_day_uses_api_link_when_confirmed_and_pdf_link_otherwise():
    texts = {"s1.pdf": [PAGE_1, PAGE_2]}
    api_pub = {"section": "DOU - Seção 1", "title": "RESOLUÇÃO-RE Nº 4.264", "href": "https://www.in.gov.br/web/dou/-/x",
               "abstract": "...", "date": "03/11/2026", "id": "741179349"}
    asked = []

    def confirm(terms):
        asked.append(sorted(terms))
        return {"single_group": {BIO: {"single_department": [api_pub]}}}

    result, failed = search_day_via_pdf(
        [SURGITEC, BIO, OTHER], ["SECAO_1"], DAY,
        confirm_with_api=confirm,
        ensure_pdfs=_fake_pdfs([("1", 515, "s1.pdf")]),
        extract_text=lambda p: texts[p.name],
    )
    assert failed == []
    assert asked == [sorted([SURGITEC, BIO])]  # só as empresas achadas vão para a API
    group = result["single_group"]
    assert group[BIO]["single_department"] == [api_pub]
    pdf_pub = group[SURGITEC]["single_department"][0]
    assert pdf_pub["href"] == (
        "https://pesquisa.in.gov.br/imprensa/jsp/visualiza/index.jsp?data=03/11/2026&jornal=515&pagina=2"
    )
    assert pdf_pub["section"] == "DOU - Seção 1"
    assert pdf_pub["date"] == "03/11/2026"
    assert OTHER not in group


def test_search_day_reports_failed_sections_and_survives_api_error():
    def confirm(_terms):
        raise TimeoutError("API fora")

    result, failed = search_day_via_pdf(
        [BIO], ["SECAO_1", "SECAO_3"], DAY,
        confirm_with_api=confirm,
        ensure_pdfs=_fake_pdfs([("1", 515, "s1.pdf")], errors=["Seção 3 (jornal 530): timeout"]),
        extract_text=lambda p: [PAGE_1],
    )
    assert failed == ["3"]
    assert result["single_group"][BIO]["single_department"][0]["id"] == "pdf-2026-11-03-515-1"


# ─── Integração com o runner ─────────────────────────────────────────────────


def _inlabs_specs():
    return load_specs({
        "dag": {
            "id": "pesquisa_teste",
            "description": "teste",
            "schedule": None,
            "search": [{
                "header": "MONITORAMENTO",
                "terms": [BIO, SURGITEC],
                "dou_sections": ["SECAO_1", "SECAO_3"],
                "date": "DIA",
                "sources": ["INLABS"],
                "force_rematch": True,
            }],
            "report": {"emails": [], "subject": "t"},
        }
    })


class _Recorder:
    def __init__(self, result=None, exc=None):
        self.calls = []
        self.result = result or {}
        self.exc = exc

    def exec_search(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return self.result


def test_runner_uses_inlabs_when_day_is_loaded():
    specs = _inlabs_specs()
    inlabs = _Recorder(result={"single_group": {"x": {}}})
    out = run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": _Recorder(), "INLABS": inlabs,
        "INLABS_FALLBACK": lambda *a, **k: pytest.fail("não deveria usar o PDF"),
        "INLABS_HAS_DATE": lambda d: True,
    })
    assert len(inlabs.calls) == 1
    assert out["result"] == {"single_group": {"x": {}}}


def test_runner_falls_back_to_pdf_and_completes_failed_sections_with_api():
    specs = _inlabs_specs()
    pdf_res = {"single_group": {BIO: {"single_department": [{"id": "pdf-1", "date": "03/11/2026"}]}}}
    api_res = {"single_group": {SURGITEC: {"single_department": [{"id": "api-9", "date": "03/11/2026"}]}}}
    dou = _Recorder(result=api_res)
    seen = {}

    def fake_pdf(terms, sections, ref, confirm_with_api):
        seen["terms"], seen["sections"] = terms, sections
        return pdf_res, ["3"]

    out = run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": dou, "INLABS": _Recorder(exc=AssertionError("INLABS vazio não deve ser consultado")),
        "INLABS_FALLBACK": fake_pdf, "INLABS_HAS_DATE": lambda d: False,
    })
    assert seen["terms"] == [BIO, SURGITEC]
    assert dou.calls[0]["dou_sections"] == ["SECAO_3"]
    assert dou.calls[0]["force_rematch"] is True
    group = out["result"]["single_group"]
    assert group[BIO]["single_department"][0]["id"] == "pdf-1"
    assert group[SURGITEC]["single_department"][0]["id"] == "api-9"


def test_runner_uses_full_api_when_pdf_unavailable():
    specs = _inlabs_specs()
    dou = _Recorder(result={"single_group": {}})

    def broken_pdf(*a, **k):
        raise RuntimeError("pesquisa.in.gov.br fora")

    run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": dou, "INLABS": _Recorder(), "INLABS_FALLBACK": broken_pdf, "INLABS_HAS_DATE": lambda d: False,
    })
    assert len(dou.calls) == 1
    assert dou.calls[0]["term_list"] == [BIO, SURGITEC]


def test_runner_api_mode_skips_pdf(monkeypatch):
    monkeypatch.setenv("REGISTRALE_INLABS_FALLBACK", "api")
    specs = _inlabs_specs()
    dou = _Recorder(result={"single_group": {}})
    run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": dou, "INLABS": _Recorder(),
        "INLABS_FALLBACK": lambda *a, **k: pytest.fail("modo api não usa PDF"),
        "INLABS_HAS_DATE": lambda d: False,
    })
    assert len(dou.calls) == 1


def test_runner_off_mode_keeps_inlabs(monkeypatch):
    monkeypatch.setenv("REGISTRALE_INLABS_FALLBACK", "off")
    specs = _inlabs_specs()
    inlabs = _Recorder()
    run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": _Recorder(), "INLABS": inlabs, "INLABS_FALLBACK": lambda *a, **k: pytest.fail("off"),
        "INLABS_HAS_DATE": lambda d: False,
    })
    assert len(inlabs.calls) == 1


def test_injected_searchers_without_fallback_keep_old_behavior():
    specs = _inlabs_specs()
    inlabs = _Recorder()
    run_search_block(specs, specs.search[0], DAY, searchers={"DOU": _Recorder(), "INLABS": inlabs})
    assert len(inlabs.calls) == 1


def test_fallback_mode_reads_env(monkeypatch):
    monkeypatch.setenv("REGISTRALE_INLABS_FALLBACK", "API")
    assert pdf_search.get_fallback_mode() == "api"
    monkeypatch.setenv("REGISTRALE_INLABS_FALLBACK", "lixo")
    assert pdf_search.get_fallback_mode() == "pdf"


def test_default_searchers_import_outside_pytest():
    """Sem o conftest, `src/` importa `ro_dou_src.*`: o runner precisa criar o alias."""
    import subprocess

    code = (
        "import sys; sys.path.insert(0, 'rodou_dashboard'); "
        "from app.runtime.runner import _build_default_searchers; "
        "s = _build_default_searchers(); assert 'INLABS_FALLBACK' in s and 'INLABS' in s"
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]


def test_pdf_archiver_normalize_section_key_accepts_yaml_names():
    from app.runtime.pdf_archiver import normalize_section_key

    assert normalize_section_key("SECAO_1") == "1"
    assert normalize_section_key("SECAO_2") == "2"
    assert normalize_section_key("SECAO_3") == "3"
    assert normalize_section_key("EDICAO_EXTRA") == "extra"
    assert normalize_section_key("EDICAO_SUPLEMENTAR") == "extra"


def test_runner_records_source_used_in_each_mode(monkeypatch):
    specs = _inlabs_specs()

    # 1. INLABS com o dia carregado
    out_inlabs = run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": _Recorder(), "INLABS": _Recorder(),
        "INLABS_FALLBACK": lambda *a, **k: ({}, []),
        "INLABS_HAS_DATE": lambda d: True,
    })
    assert out_inlabs["source_used"] == "INLABS"

    # 2. Fallback PDF integral + API do DOU
    monkeypatch.setenv("REGISTRALE_INLABS_FALLBACK", "pdf")
    out_pdf = run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": _Recorder(), "INLABS": _Recorder(),
        "INLABS_FALLBACK": lambda *a, **k: ({"single_group": {}}, []),
        "INLABS_HAS_DATE": lambda d: False,
    })
    assert out_pdf["source_used"] == "PDF integral + API do DOU"

    # 3. Fallback PDF falha (ex.: captcha/timeout) -> cai para API do DOU
    def broken_pdf(*a, **k):
        raise RuntimeError("captcha exigido no visualizador")

    out_api_after_err = run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": _Recorder(), "INLABS": _Recorder(),
        "INLABS_FALLBACK": broken_pdf,
        "INLABS_HAS_DATE": lambda d: False,
    })
    assert out_api_after_err["source_used"] == "API do DOU"


def test_history_and_settings_and_status_ui_for_inlabs_fallback(tmp_path, monkeypatch):
    from unittest.mock import patch
    from app import create_app
    from app.models import JobRun, SyncHistory, db
    from app.routes.dags import watch_dag_and_update_mentions

    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("REGISTRALE_DB_PATH", str(tmp_path / "data" / "database.db"))

    app = create_app({"TESTING": True})
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = {"username": "admin", "role": "master"}

    # Salvar e ler inlabs_fallback em Configurações
    bad_resp = client.post("/api/save_settings", json={"inlabs_fallback": "invalido"})
    assert bad_resp.status_code == 400

    ok_resp = client.post("/api/save_settings", json={"inlabs_fallback": "api"})
    assert ok_resp.status_code == 200
    get_resp = client.get("/api/settings")
    assert get_resp.status_code == 200
    assert get_resp.get_json()["settings"]["inlabs_fallback"] == "api"

    client.post("/api/save_settings", json={"inlabs_fallback": "pdf"})

    # /api/status exibe status do portal INLABS e fonte de contingência ativa
    with patch("app.services.inlabs_service.check_inlabs_portal_status", return_value=(False, "Portal INLABS em Manutenção Programada")), \
         patch("app.services.inlabs_service.is_date_loaded", return_value=(False, 0)):
        st_resp = client.get("/api/status?refresh=1")
    assert st_resp.status_code == 200
    inlabs_st = st_resp.get_json()["inlabs_status"]
    assert inlabs_st["portal_ok"] is False
    assert "Manutenção" in inlabs_st["portal_message"]
    assert inlabs_st["today_loaded"] is False
    assert inlabs_st["fallback_mode"] == "pdf"
    assert inlabs_st["fallback_label"] == "PDF integral + API do DOU"

    # Histórico de execução registra a fonte efetiva vinda de JobRun
    with app.app_context():
        job = JobRun(id="run-pdf-1", rotina="Pesquisa_cnpj.yaml", data="2026-11-03", status="success")
        job.set_resultado([{"result": {}, "header": "H", "source_used": "PDF integral + API do DOU"}])
        db.session.add(job)
        db.session.commit()

    with patch("app.runtime.executor.LocalExecutor.wait", return_value=(True, {"run-pdf-1": "success"})):
        watch_dag_and_update_mentions(
            app.app_context(),
            [{"dag_id": "pesquisa_cnpj_anvisa", "dag_run_id": "run-pdf-1"}],
            "Pesquisa_cnpj.yaml",
            logical_date="2026-11-03",
        )

    with app.app_context():
        hist = SyncHistory.query.order_by(SyncHistory.id.desc()).first()
        assert hist is not None
        assert "PDF integral + API do DOU" in hist.detalhes


def test_windows_ci_has_outside_pytest_smoke_check():
    yml = (REPO_ROOT / ".github" / "workflows" / "windows-build.yml").read_text(encoding="utf-8")
    assert "_build_default_searchers" in yml
    assert "registrale" in yml
    assert "/login" in yml


@pytest.mark.live
def test_live_fallback_pdf_matches_baseline_day(tmp_path, monkeypatch):
    """Tarefa 5: run_routine de um dia da baseline com REGISTRALE_INLABS_FALLBACK=pdf sem INLABS."""
    import json
    from app.routes.dags import extract_mentions_from_results
    from app.runtime.runner import _build_default_searchers, run_routine

    monkeypatch.setenv("REGISTRALE_INLABS_FALLBACK", "pdf")
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("REGISTRALE_PDF_DIR", str(tmp_path / "pdfs"))

    searchers = _build_default_searchers()
    searchers["INLABS_HAS_DATE"] = lambda _d: False

    results = run_routine(REPO_ROOT / "dag_confs" / "Pesquisa_cnpj.yaml", execution_date="2026-11-16", searchers=searchers)
    assert results
    assert all(b.get("source_used") == "PDF integral + API do DOU" for b in results)

    mentions = extract_mentions_from_results([b["result"] for b in results], cnpj_map={})
    with open(REPO_ROOT / "tests" / "fixtures" / "baseline" / "nov2026_mentions.json", "r", encoding="utf-8") as fh:
        baseline = json.load(fh)
    expected = [m for m in baseline if m["data"] == "16/11/2026"]

    assert expected
    assert {(m["cnpj_norm"], m["link"]) for m in mentions} == {(m["cnpj_norm"], m["link"]) for m in expected}
