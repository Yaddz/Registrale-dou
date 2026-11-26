"""Sprint 11: busca confiável sem INLABS local, cobertura por seção e rotina vazia."""

from __future__ import annotations

from datetime import date, datetime
import logging
from pathlib import Path
import sys

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = REPO_ROOT / "rodou_dashboard"
for p in (REPO_ROOT, DASHBOARD_DIR, Path(__file__).resolve().parent):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import rotina_teste  # noqa: E402
from app import create_app  # noqa: E402
from app.models import JobRun, db  # noqa: E402
from app.runtime import pdf_archiver, pdf_search, pg_portable, scheduler  # noqa: E402
from app.runtime.executor import LocalExecutor  # noqa: E402
from app.runtime.paths import _EMPTY_MAIN_ROUTINE_YAML  # noqa: E402
from app.runtime.runner import (  # noqa: E402
    NoMonitoredCompanies,
    load_specs,
    routine_has_no_terms,
    run_routine,
    run_search_block,
)
from app.services import inlabs_service  # noqa: E402

DAY = date(2026, 11, 23)  # segunda-feira
SATURDAY = date(2026, 11, 21)
BIO = "00097446000186"


@pytest.fixture(autouse=True)
def _sem_inlabs_local(monkeypatch):
    """Ambiente do app instalado: sem INLABS_DB_URL e sem binários do Postgres portátil."""
    monkeypatch.delenv("INLABS_DB_URL", raising=False)
    monkeypatch.setenv("REGISTRALE_INLABS_FALLBACK", "pdf")
    monkeypatch.setattr(pg_portable, "get_pg_bin_dir", lambda: None)
    pg_portable.reset_portable_postgres_for_tests()
    inlabs_service.reset_inlabs_state_for_tests()
    yield
    pg_portable.reset_portable_postgres_for_tests()
    inlabs_service.reset_inlabs_state_for_tests()


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


def _specs(department=None, sections=None):
    block = {
        "header": "ROTINA",
        "terms": [BIO],
        "dou_sections": sections or ["SECAO_1", "SECAO_2", "SECAO_3", "EDICAO_EXTRA"],
        "date": "DIA",
        "sources": ["INLABS"],
        "force_rematch": True,
    }
    if department:
        block["department"] = department
    return load_specs({"dag": {"id": "t", "description": "t", "schedule": None, "search": [block], "report": {"emails": [], "subject": "t"}}})


# ─── INLABS ausente ──────────────────────────────────────────────────────────


def test_engine_ausente_levanta_erro_proprio_e_avisa_uma_vez(caplog):
    with caplog.at_level(logging.WARNING, logger=inlabs_service.logger.name):
        for _ in range(5):
            with pytest.raises(inlabs_service.InlabsUnavailable):
                inlabs_service.get_inlabs_postgres_engine()
    avisos = [r for r in caplog.records if "INLABS local não instalado" in r.getMessage()]
    assert len(avisos) == 1
    assert inlabs_service.is_inlabs_local_available() is False


def test_chamadores_tratam_inlabs_ausente_sem_traceback(caplog):
    with caplog.at_level(logging.WARNING):
        assert inlabs_service.is_date_loaded("2026-11-23") == (False, 0)
        assert inlabs_service.get_downloaded_dates("2026-11-01", "2026-11-30") == set()
        assert pdf_search.inlabs_has_date(DAY) is False
    ruidosos = [r for r in caplog.records if "NoneType" in r.getMessage() or "Erro ao" in r.getMessage()]
    assert ruidosos == []


def test_telas_inlabs_mostram_contingencia_em_vez_de_erro_500(tmp_path, monkeypatch):
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("REGISTRALE_DB_PATH", str(tmp_path / "data" / "database.db"))
    app = create_app({"TESTING": True})
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = {"username": "admin", "role": "master"}

    stats = client.get("/api/inlabs_stats?refresh=1")
    assert stats.status_code == 200
    body = stats.get_json()
    assert body["status"] == "unavailable"
    assert "contingência" in body["message"]

    from unittest.mock import patch

    with patch("app.services.inlabs_service.check_inlabs_portal_status", return_value=(True, "ok")):
        st = client.get("/api/status?refresh=1").get_json()["inlabs_status"]
    assert st["local_available"] is False
    assert "contingência" in st["local_message"]

    check = client.get("/api/routines/check_date?date=2026-11-23")
    assert check.status_code == 200
    assert check.get_json()["already_loaded"] is False


# ─── Fonte efetiva e contingência ────────────────────────────────────────────


def test_rotina_inlabs_sem_postgres_vai_direto_para_a_contingencia():
    specs = _specs()
    inlabs, dou = _Recorder(exc=AssertionError("não deve tocar o banco do INLABS")), _Recorder()
    pdf_calls = []

    def pdf(terms, sections, ref_date, **kw):
        pdf_calls.append(ref_date)
        return {}, []

    out = run_search_block(specs, specs.search[0], DAY, searchers={"DOU": dou, "INLABS": inlabs, "INLABS_FALLBACK": pdf})
    assert pdf_calls == [DAY]
    assert inlabs.calls == []
    assert out["source_used"] == "PDF integral + API do DOU"
    assert [c["section"] for c in out["coverage"]] == ["SECAO_1", "SECAO_2", "SECAO_3", "EDICAO_EXTRA"]
    assert out["incomplete"] is False


def test_modo_api_registra_api_do_dou_e_seccoes_cobertas(monkeypatch):
    monkeypatch.setenv("REGISTRALE_INLABS_FALLBACK", "api")
    specs = _specs()
    dou = _Recorder()
    out = run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": dou, "INLABS": _Recorder(), "INLABS_FALLBACK": lambda *a, **k: ({}, []),
    })
    assert out["source_used"] == "API do DOU"
    assert len(dou.calls) == 1
    assert {c["source"] for c in out["coverage"]} == {"API do DOU"}


# ─── PDF incompleto e cobertura por seção ────────────────────────────────────


def test_secao_com_falha_no_pdf_e_coberta_pela_api():
    specs = _specs()
    dou = _Recorder()

    def pdf(terms, sections, ref_date, report=None, **kw):
        report["sections"] = {
            "1": {"status": "pdf", "detail": ""},
            "2": {"status": "falhou", "detail": "Seção 2 (jornal 529): timeout"},
            "3": {"status": "pdf", "detail": ""},
            "extra": {"status": "ausente", "detail": "sem edição publicada no dia"},
        }
        return {}, ["2"]

    out = run_search_block(specs, specs.search[0], DAY, searchers={"DOU": dou, "INLABS": _Recorder(), "INLABS_FALLBACK": pdf})
    assert [[getattr(s, "value", s) for s in c["dou_sections"]] for c in dou.calls] == [["SECAO_2"]]
    cov = {c["section"]: c for c in out["coverage"]}
    assert cov["SECAO_2"]["status"] == "coberta" and cov["SECAO_2"]["source"] == "API do DOU"
    assert cov["SECAO_1"]["source"] == "PDF integral"
    assert cov["EDICAO_EXTRA"]["status"] == "sem_edicao"
    assert out["incomplete"] is False


def test_secao_sem_cobertura_de_nenhuma_fonte_fica_pendente():
    specs = _specs()

    def pdf(terms, sections, ref_date, report=None, **kw):
        report["sections"] = {"2": {"status": "falhou", "detail": "portal fora do ar"}}
        return {}, ["2"]

    out = run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": _Recorder(exc=RuntimeError("api fora")), "INLABS": _Recorder(), "INLABS_FALLBACK": pdf,
    })
    cov = {c["section"]: c for c in out["coverage"]}
    assert cov["SECAO_2"]["status"] == "pendente"
    assert "api fora" in cov["SECAO_2"]["detail"]
    assert out["incomplete"] is True


def test_pdf_e_api_fora_do_ar_deixa_todas_as_secoes_pendentes():
    specs = _specs()

    def pdf(*a, **k):
        raise RuntimeError("captcha")

    out = run_search_block(specs, specs.search[0], DAY, searchers={
        "DOU": _Recorder(exc=RuntimeError("api fora")), "INLABS": _Recorder(), "INLABS_FALLBACK": pdf,
    })
    assert out["incomplete"] is True
    assert {c["status"] for c in out["coverage"]} == {"pendente"}


def _fake_ensure(present, errors=None):
    def _ensure(date_iso, sections):
        return [(s, 1, Path(f"{s}.pdf")) for s in present if s in sections], list(errors or [])
    return _ensure


def test_pdf_ausente_em_dia_util_e_falha_mas_em_fim_de_semana_nao():
    kw = dict(ensure_pdfs=_fake_ensure(["1"]), extract_text=lambda p: [])
    rep = {}
    _res, failed = pdf_search.search_day_via_pdf([BIO], None, DAY, report=rep, **kw)
    assert failed == ["2", "3"]  # Extra é eventual: ausente não é falha
    assert rep["sections"]["extra"]["status"] == "ausente"
    assert rep["sections"]["2"]["status"] == "falhou"

    _res, failed_sat = pdf_search.search_day_via_pdf([BIO], None, SATURDAY, report={}, **kw)
    assert failed_sat == []


def test_erro_explicito_de_secao_continua_sendo_falha():
    rep = {}
    _res, failed = pdf_search.search_day_via_pdf(
        [BIO], ["SECAO_1", "SECAO_2"], SATURDAY, report=rep,
        ensure_pdfs=_fake_ensure(["1"], ["Seção 2 (jornal 529): timeout"]), extract_text=lambda p: [],
    )
    assert failed == ["2"]
    assert "timeout" in rep["sections"]["2"]["detail"]


def test_filtro_de_orgao_descarta_o_que_so_o_pdf_achou():
    """Com `department`, o PDF não conhece órgãos: só vale o que a API confirma."""
    page = "Empresa 00.097.446/0001-86 citada"
    common = dict(ensure_pdfs=_fake_ensure(["1"]), extract_text=lambda p: [page])
    sem_filtro, _ = pdf_search.search_day_via_pdf([BIO], ["SECAO_1"], DAY, confirm_with_api=lambda t: {}, **common)
    assert BIO in sem_filtro["single_group"]
    com_filtro, _ = pdf_search.search_day_via_pdf(
        [BIO], ["SECAO_1"], DAY, confirm_with_api=lambda t: {}, strict_confirm=True, **common
    )
    assert com_filtro == {"single_group": {}}


def test_descoberta_de_paginas_distingue_sem_edicao_de_resposta_estranha():
    class Resp:
        status_code = 200

        def __init__(self, text):
            self.text, self.content = text, text.encode()

        def raise_for_status(self):
            pass

    class Sess:
        def __init__(self, text):
            self.text = text

        def request(self, *a, **k):
            return Resp(self.text)

    ok = pdf_archiver._discover_pesquisa_total_pages(Sess("...totalArquivos=156&x"), "24/11/2026", 515)
    assert ok == 156
    nada = pdf_archiver._discover_pesquisa_total_pages(Sess("<title>Página Inexistente</title>"), "22/11/2026", 515)
    assert nada == 0
    with pytest.raises(pdf_archiver.PdfArchiverError, match="inesperada"):
        pdf_archiver._discover_pesquisa_total_pages(Sess("<html>truncado"), "24/11/2026", 515)


# ─── Execução "com pendências" e rotina vazia ────────────────────────────────


@pytest.fixture()
def app_exec(tmp_path, monkeypatch):
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(tmp_path / "data"))
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 's11.db'}", "WTF_CSRF_ENABLED": False})
    with app.app_context():
        db.create_all()
    return app


def _routine(sources=("INLABS",)):
    return rotina_teste.build_test_routine(list(sources))


def test_execucao_com_secao_nao_coberta_termina_com_pendencias(app_exec):
    def pdf(terms, sections, ref_date, report=None, **kw):
        report["sections"] = {"3": {"status": "falhou", "detail": "portal"}}
        return {}, ["3"]

    searchers = {"DOU": _Recorder(exc=RuntimeError("api fora")), "INLABS": _Recorder(), "QD": _Recorder(),
                 "DOESP": _Recorder(), "INLABS_FALLBACK": pdf}
    ex = LocalExecutor(app=app_exec, max_workers=1, searchers=searchers)
    try:
        with app_exec.app_context():
            rid = ex.trigger(_routine(), date="2026-11-23")
            finished, states = ex.wait([rid], timeout=60)
            assert finished is True
            assert states[rid] == "partial"
            job = db.session.get(JobRun, rid)
            assert "Seção 3" in job.erro
    finally:
        ex.shutdown(wait=True)


def test_execucao_completa_continua_sucesso(app_exec):
    searchers = {"DOU": _Recorder(), "INLABS": _Recorder(), "QD": _Recorder(), "DOESP": _Recorder(),
                 "INLABS_FALLBACK": lambda *a, **k: ({}, [])}
    ex = LocalExecutor(app=app_exec, max_workers=1, searchers=searchers)
    try:
        with app_exec.app_context():
            rid = ex.trigger(_routine(), date="2026-11-23")
            _, states = ex.wait([rid], timeout=60)
            assert states[rid] == "success"
    finally:
        ex.shutdown(wait=True)


def test_rotina_sem_cnpjs_mostra_mensagem_em_vez_do_erro_do_pydantic(app_exec):
    ex = LocalExecutor(app=app_exec, max_workers=1)
    try:
        with app_exec.app_context():
            rid = ex.trigger(yaml.safe_load(_EMPTY_MAIN_ROUTINE_YAML), date="2026-11-23")
            _, states = ex.wait([rid], timeout=60)
            job = db.session.get(JobRun, rid)
            assert states[rid] == "failed"
            assert job.erro == "Nenhuma empresa monitorada: sincronize a planilha ou o GestãoClick."
            assert "validation" not in job.erro.lower()
    finally:
        ex.shutdown(wait=True)


def test_rotina_sem_blocos_ou_com_termos_vazios_e_detectada():
    assert routine_has_no_terms(yaml.safe_load(_EMPTY_MAIN_ROUTINE_YAML)) is True
    assert routine_has_no_terms({"dag": {"search": []}}) is True
    com_termos = yaml.safe_load(_EMPTY_MAIN_ROUTINE_YAML)
    com_termos["dag"]["search"][0]["terms"] = [BIO]
    assert routine_has_no_terms(com_termos) is False
    with pytest.raises(NoMonitoredCompanies):
        run_routine(yaml.safe_load(_EMPTY_MAIN_ROUTINE_YAML), execution_date="2026-11-23", searchers={})


def test_disparo_manual_de_rotina_vazia_responde_400_com_a_mensagem(tmp_path, monkeypatch):
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("REGISTRALE_DB_PATH", str(tmp_path / "data" / "database.db"))
    app = create_app({"TESTING": True})
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = {"username": "admin", "role": "master"}
    resp = client.post("/api/routines/trigger/Pesquisa_cnpj.yaml", json={})
    assert resp.status_code == 400
    assert "Nenhuma empresa monitorada" in resp.get_json()["message"]


def test_reconstrucao_com_zero_cnpjs_grava_rotina_que_a_busca_entende(tmp_path, monkeypatch):
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("REGISTRALE_DB_PATH", str(tmp_path / "data" / "database.db"))
    app = create_app({"TESTING": True})
    with app.app_context():
        from app.services.dag_config_service import get_base_yaml_path, rebuild_yaml_from_db

        rebuild_yaml_from_db()
        data = yaml.safe_load(Path(get_base_yaml_path()).read_text(encoding="utf-8"))
    assert routine_has_no_terms(data) is True
    bloco = data["dag"]["search"][0]
    assert bloco["department"] == [] and bloco["is_exact_search"] is False
    assert bloco["dou_sections"] == ["SECAO_1", "SECAO_2", "SECAO_3", "EDICAO_EXTRA"]


# ─── Padrões da baseline ─────────────────────────────────────────────────────


def test_rotina_semeada_usa_os_padroes_da_baseline():
    bloco = yaml.safe_load(_EMPTY_MAIN_ROUTINE_YAML)["dag"]["search"][0]
    assert bloco["is_exact_search"] is False
    assert bloco["field"] == "TUDO"
    assert bloco["department"] == []
    assert bloco["dou_sections"] == ["SECAO_1", "SECAO_2", "SECAO_3", "EDICAO_EXTRA"]


def test_rotina_de_teste_segue_a_baseline_e_tem_16_empresas():
    r = rotina_teste.build_test_routine(["INLABS"])
    bloco = r["dag"]["search"][0]
    assert len(bloco["terms"]) == 16
    assert bloco["department"] == [] and bloco["is_exact_search"] is False
    assert len(rotina_teste.load_expected_mentions()) == 26


# ─── Resíduo do Airflow no SMTP ──────────────────────────────────────────────


def test_salvar_smtp_nao_grava_chaves_airflow(tmp_path, monkeypatch):
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("REGISTRALE_DB_PATH", str(tmp_path / "data" / "database.db"))
    app = create_app({"TESTING": True})
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = {"username": "admin", "role": "master"}
    import os
    antes = {k: v for k, v in os.environ.items() if k.startswith("AIRFLOW__SMTP")}
    resp = client.post("/api/save_settings", json={"smtp": {"server": "smtp.exemplo.com", "port": "587", "user": "a@b.c", "password": "x", "enabled": True}})
    assert resp.status_code == 200
    env_file = tmp_path / "data" / ".env"
    assert "AIRFLOW__SMTP" not in (env_file.read_text(encoding="utf-8") if env_file.exists() else "")
    assert {k: v for k, v in os.environ.items() if k.startswith("AIRFLOW__SMTP")} == antes


# ─── Nova tentativa do dia ───────────────────────────────────────────────────


class _FakeSched:
    running = True

    def __init__(self):
        self.jobs = []
        self.scheduler = self

    def add_job(self, func, **kw):
        self.jobs.append((func, kw))


def _freeze(monkeypatch, hour):
    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 24, hour, 5, tzinfo=tz)

    monkeypatch.setattr(scheduler, "datetime", FakeDT)


def test_pendencia_agenda_nova_tentativa_com_referencia_textual(monkeypatch):
    fake = _FakeSched()
    monkeypatch.setattr(scheduler, "get_scheduler", lambda: fake)
    _freeze(monkeypatch, 10)
    assert scheduler._schedule_retry("Pesquisa_cnpj.yaml", 1) is True
    func, kw = fake.jobs[0]
    assert isinstance(func, str) and func.endswith(":_run_scheduled_routine")
    assert kw["args"] == ["Pesquisa_cnpj.yaml", 1, "2026-11-24"] and kw["id"].startswith("retry::")


def test_nova_tentativa_respeita_o_limite_do_dia(monkeypatch):
    fake = _FakeSched()
    monkeypatch.setattr(scheduler, "get_scheduler", lambda: fake)
    _freeze(monkeypatch, 22)
    assert scheduler._schedule_retry("Pesquisa_cnpj.yaml", 1) is False
    _freeze(monkeypatch, 9)
    assert scheduler._schedule_retry("Pesquisa_cnpj.yaml", scheduler.RETRY_MAX_ATTEMPTS + 1) is False
    assert fake.jobs == []


# ─── Correções pós-revisão ───────────────────────────────────────────────────


def test_typeerror_dentro_do_pdf_cai_na_api_e_o_pdf_roda_uma_vez():
    """Bloqueador: TypeError do PDF (ex.: arquivo corrompido) não pode ser confundido com
    'buscador sem o parâmetro report'; a API do DOU cobre o dia."""
    specs = _specs()
    calls = []

    def pdf(terms, sections, ref_date, report=None, strict_confirm=False, confirm_with_api=None):
        calls.append(1)
        raise TypeError("'NoneType' object is not iterable")  # vindo de dentro do PdfReader

    dou = _Recorder()
    out = run_search_block(specs, specs.search[0], DAY, searchers={"DOU": dou, "INLABS": _Recorder(), "INLABS_FALLBACK": pdf})
    assert calls == [1]
    assert len(dou.calls) == 1
    assert out["source_used"] == "API do DOU"
    assert {c["status"] for c in out["coverage"]} == {"coberta"}


def test_buscador_injetado_sem_report_continua_funcionando():
    specs = _specs()
    seen = []

    def pdf(terms, sections, ref_date, confirm_with_api=None):
        seen.append(1)
        return {}, []

    out = run_search_block(specs, specs.search[0], DAY, searchers={"DOU": _Recorder(), "INLABS": _Recorder(), "INLABS_FALLBACK": pdf})
    assert seen == [1] and out["source_used"] == "PDF integral + API do DOU"


def test_hoje_sem_pdf_fica_provisorio_e_dias_passados_continuam_cobertos(monkeypatch):
    monkeypatch.setattr(pdf_search, "_today_brt", lambda: DAY)
    monkeypatch.setattr(pdf_search, "_is_business_day", lambda d: True)
    specs = _specs()

    def pdf(terms, sections, ref_date, **kw):
        return pdf_search.search_day_via_pdf(
            terms, sections, ref_date, ensure_pdfs=_fake_ensure([]), extract_text=lambda p: [], **kw
        )

    dou = _Recorder()
    hoje = run_search_block(specs, specs.search[0], DAY, searchers={"DOU": dou, "INLABS": _Recorder(), "INLABS_FALLBACK": pdf})
    cov = {c["section"]: c for c in hoje["coverage"]}
    assert cov["SECAO_1"]["status"] == "pendente" and cov["SECAO_1"]["source"] == "API do DOU"
    assert "pode não ter sido publicada" in cov["SECAO_1"]["detail"]
    assert cov["EDICAO_EXTRA"]["status"] == "sem_edicao"
    assert hoje["incomplete"] is True and len(dou.calls) == 1  # a API ainda é consultada

    # dia passado: a API é a fonte definitiva
    monkeypatch.setattr(pdf_search, "_today_brt", lambda: date(2026, 11, 24))
    passado = run_search_block(specs, specs.search[0], DAY, searchers={"DOU": _Recorder(), "INLABS": _Recorder(), "INLABS_FALLBACK": pdf})
    assert {c["status"] for c in passado["coverage"] if c["section"] != "EDICAO_EXTRA"} == {"coberta"}
    assert passado["incomplete"] is False


def test_hoje_provisorio_deixa_execucao_partial_e_agenda_nova_tentativa(app_exec, monkeypatch):
    monkeypatch.setattr(pdf_search, "_today_brt", lambda: DAY)
    monkeypatch.setattr(pdf_search, "_is_business_day", lambda d: True)

    def pdf(terms, sections, ref_date, **kw):
        return pdf_search.search_day_via_pdf(
            terms, sections, ref_date, ensure_pdfs=_fake_ensure([]), extract_text=lambda p: [], **kw
        )

    searchers = {"DOU": _Recorder(), "INLABS": _Recorder(), "QD": _Recorder(), "DOESP": _Recorder(), "INLABS_FALLBACK": pdf}
    ex = LocalExecutor(app=app_exec, max_workers=1, searchers=searchers)
    try:
        with app_exec.app_context():
            rid = ex.trigger(_routine(), date="2026-11-23")
            _, states = ex.wait([rid], timeout=60)
            assert states[rid] == "partial"
            assert scheduler._pending_in_runs([rid]) is True
    finally:
        ex.shutdown(wait=True)


def test_extra_do_pdf_e_da_api_casam_na_deduplicacao(app_exec):
    from app.models import Mention
    from app.routes.dags import reconcile_mentions_across_sources

    with app_exec.app_context():
        db.session.add(Mention(**_mention(f"{BIO}_pdf-2026-11-23-600-3", "https://pesquisa.in.gov.br/x", secao="DOU - Edição Extra")))
        db.session.commit()
        api = _mention(f"{BIO}_555", "https://www.in.gov.br/web/dou/-/extra-555", secao="DOU - Seção: 1 - Extra A")
        kept, notified = reconcile_mentions_across_sources([api])
        assert [m["id"] for m in kept] == [api["id"]] and notified == {api["id"]}


def test_filtro_de_orgao_registra_avisos_na_cobertura():
    page = "Empresa 00.097.446/0001-86 citada"
    common = dict(ensure_pdfs=_fake_ensure(["1"]), extract_text=lambda p: [page])
    rep = {}
    pdf_search.search_day_via_pdf([BIO], ["SECAO_1"], DAY, confirm_with_api=lambda t: {}, strict_confirm=True, report=rep, **common)
    assert any("fora do filtro de órgão" in n for n in rep["notes"])

    def api_fora(_t):
        raise RuntimeError("api fora")

    rep2 = {}
    res, _ = pdf_search.search_day_via_pdf([BIO], ["SECAO_1"], DAY, confirm_with_api=api_fora, strict_confirm=True, report=rep2, **common)
    assert BIO in res["single_group"]
    assert any("SEM aplicar o filtro de órgão" in n for n in rep2["notes"])


def test_descoberta_so_aceita_inexistente_como_sem_edicao():
    class Resp:
        status_code = 200

        def __init__(self, text):
            self.text, self.content = text, text.encode()

        def raise_for_status(self):
            pass

    class Sess:
        def request(self, *a, **k):
            return Resp("<html>Edição não encontrada</html>")

    with pytest.raises(pdf_archiver.PdfArchiverError):
        pdf_archiver._discover_pesquisa_total_pages(Sess(), "20/11/2026", 515)


# Deduplicação entre fontes e e-mail da nova tentativa


def _mention(mid, source_href, secao="DOU - Seção 2", data="23/11/2026", norm=BIO):
    return {"id": mid, "empresa": "Empresa", "cnpj": norm, "cnpj_norm": norm, "secao": secao, "data": data,
            "detected_at": "2026-11-23 09:00:00", "trecho": "t", "link": source_href}


def test_mencao_do_pdf_substituida_pela_da_api_nao_duplica_nem_reenvia(app_exec):
    from app.models import Mention
    from app.routes.dags import reconcile_mentions_across_sources

    with app_exec.app_context():
        db.session.add(Mention(**_mention(f"{BIO}_pdf-2026-11-23-529-10", "https://pesquisa.in.gov.br/x")))
        db.session.commit()
        api = _mention(f"{BIO}_999888", "https://www.in.gov.br/web/dou/-/ato-999888")
        kept, notified = reconcile_mentions_across_sources([api])
        db.session.commit()
        assert [m["id"] for m in kept] == [api["id"]] and notified == {api["id"]}
        assert [m.id for m in Mention.query.all()] == []  # a de PDF saiu; a da API entra na gravação

        # inverso: já existe a da API e chega a do PDF -> descartada
        db.session.add(Mention(**api))
        db.session.commit()
        kept2, _ = reconcile_mentions_across_sources([_mention(f"{BIO}_pdf-2026-11-23-529-10", "https://pesquisa.in.gov.br/x")])
        assert kept2 == []

        # atos distintos da mesma empresa/seção/dia continuam distintos
        kept3, _ = reconcile_mentions_across_sources([_mention(f"{BIO}_777", "https://www.in.gov.br/web/dou/-/outro")])
        assert len(kept3) == 1


def test_nova_tentativa_com_id_da_api_apos_pdf_gera_uma_mencao_e_nenhum_email(app_exec):
    from unittest.mock import MagicMock, patch
    from app.models import Mention
    from app.routes.dags import watch_dag_and_update_mentions

    with app_exec.app_context():
        db.session.add(Mention(**_mention(f"{BIO}_pdf-2026-11-23-529-10", "https://pesquisa.in.gov.br/x")))
        job = JobRun(id="retry-run", rotina="r", data="2026-11-23", status="success")
        job.set_resultado([{"result": {"single_group": {BIO: {"d": [{
            "id": "999888", "section": "DOU - Seção 2", "date": "23/11/2026", "abstract": "texto 00.097.446/0001-86",
            "href": "https://www.in.gov.br/web/dou/-/ato-999888", "title": "Ato"}]}}}, "header": "H"}])
        db.session.add(job)
        db.session.commit()

    sender = MagicMock()
    with patch("app.runtime.executor.LocalExecutor.wait", return_value=(True, {"retry-run": "success"})), \
         patch("app.services.email_service.is_smtp_enabled", return_value=True), \
         patch("app.services.email_service.EmailSender", return_value=sender):
        watch_dag_and_update_mentions(
            app_exec.app_context(), [{"dag_id": "r", "dag_run_id": "retry-run"}], "Pesquisa_cnpj.yaml",
            routine_emails=["a@b.c"], logical_date="2026-11-23", notify_only_new=True,
        )
    sender.send_custom_email.assert_not_called()
    with app_exec.app_context():
        rows = Mention.query.all()
        assert len(rows) == 1 and rows[0].id == f"{BIO}_999888"


# Nova tentativa do dia: ponta a ponta


@pytest.fixture()
def sched_env(app_exec, tmp_path, monkeypatch):
    routines = tmp_path / "rotinas"
    routines.mkdir()
    (routines / "Pesquisa_cnpj.yaml").write_text(_EMPTY_MAIN_ROUTINE_YAML, encoding="utf-8")
    monkeypatch.setenv("REGISTRALE_ROUTINES_DIR", str(routines))
    monkeypatch.setattr(scheduler, "_APP_REF", app_exec)
    watched, retries = [], []

    class FakeExec:
        def trigger(self, yf, date=None, **kw):
            return "partial-run"

    monkeypatch.setattr("app.runtime.executor.get_executor", lambda app=None: FakeExec())
    monkeypatch.setattr("app.routes.dags.watch_dag_and_update_mentions", lambda *a, **kw: watched.append(kw))
    monkeypatch.setattr(scheduler, "_run_scheduled_pdf_archive", lambda d: None)
    monkeypatch.setattr(scheduler, "_schedule_retry", lambda f, n: retries.append((f, n)) or True)
    monkeypatch.setattr(scheduler, "_routine_is_active", lambda f: True)
    with app_exec.app_context():
        job = JobRun(id="partial-run", rotina="r", data="2026-11-24", status="partial")
        job.set_resultado([])
        db.session.add(job)
        db.session.commit()
    return watched, retries


def test_execucao_partial_agenda_a_nova_tentativa(sched_env):
    watched, retries = sched_env
    scheduler._run_scheduled_routine("Pesquisa_cnpj.yaml")
    assert retries == [("Pesquisa_cnpj.yaml", 1)]
    assert watched[0]["notify_only_new"] is False


def test_nova_tentativa_so_envia_email_de_mencoes_novas_e_encadeia(sched_env):
    watched, retries = sched_env
    hoje = datetime.now(scheduler._BRASILIA_TZ).strftime("%Y-%m-%d")
    scheduler._run_scheduled_routine("Pesquisa_cnpj.yaml", 1, hoje)
    assert watched[0]["notify_only_new"] is True
    assert retries == [("Pesquisa_cnpj.yaml", 2)]


def test_nova_tentativa_do_dia_anterior_ou_de_rotina_pausada_nao_roda(sched_env, monkeypatch):
    watched, retries = sched_env
    scheduler._run_scheduled_routine("Pesquisa_cnpj.yaml", 1, "2026-01-01")  # perdida: dispara no dia seguinte
    assert watched == [] and retries == []
    hoje = datetime.now(scheduler._BRASILIA_TZ).strftime("%Y-%m-%d")
    monkeypatch.setattr(scheduler, "_routine_is_active", lambda f: False)
    scheduler._run_scheduled_routine("Pesquisa_cnpj.yaml", 1, hoje)
    assert watched == [] and retries == []


def test_retry_usa_grace_curto_e_data_nos_argumentos(monkeypatch):
    fake = _FakeSched()
    monkeypatch.setattr(scheduler, "get_scheduler", lambda: fake)
    _freeze(monkeypatch, 10)
    scheduler._schedule_retry("Pesquisa_cnpj.yaml", 2)
    _f, kw = fake.jobs[0]
    assert kw["misfire_grace_time"] == scheduler.RETRY_MISFIRE_GRACE_SECONDS <= 900
    assert kw["args"] == ["Pesquisa_cnpj.yaml", 2, "2026-11-24"]


def test_sincronizacao_remove_retry_de_rotina_inativa(app_exec, tmp_path, monkeypatch):
    sched = scheduler.RegistraleScheduler(app_exec, db_path=tmp_path / "jobs.db")
    sched.scheduler.add_job("rodou_dashboard.app.runtime.scheduler:_run_scheduled_routine",
                            trigger="date", run_date=datetime(2030, 1, 1), args=["Pesquisa_cnpj.yaml", 1, "2030-01-01"],
                            id="retry::Pesquisa_cnpj.yaml")
    monkeypatch.setattr("app.services.dag_config_service.get_routines", lambda: [])
    with app_exec.app_context():
        sched._sync_routine_jobs()
    assert sched.scheduler.get_job("retry::Pesquisa_cnpj.yaml") is None


# ─── Correções pós-revisão conjunta: execuções órfãs e GestãoClick ───────────


def test_execucoes_orfas_viram_failed_na_inicializacao_e_o_indicador_volta_a_ocioso(tmp_path, monkeypatch):
    from app.models import SyncHistory
    from app.runtime.executor import ORPHAN_RUN_MESSAGE, recover_orphan_runs

    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("REGISTRALE_DB_PATH", str(tmp_path / "data" / "database.db"))
    app = create_app({"TESTING": True})
    with app.app_context():
        for rid, st in (("o1", "running"), ("o2", "queued"), ("ok", "success")):
            db.session.add(JobRun(id=rid, rotina="Pesquisa_cnpj", data="2026-11-24", status=st, inicio="2026-11-24T08:00:00-03:00"))
        db.session.commit()
    assert recover_orphan_runs(app) == 2  # equivalente ao que create_app faz ao subir
    with app.app_context():
        assert db.session.get(JobRun, "o1").status == "failed"
        assert db.session.get(JobRun, "o1").erro == ORPHAN_RUN_MESSAGE
        assert db.session.get(JobRun, "o2").status == "failed"
        assert db.session.get(JobRun, "ok").status == "success"
        assert any(h.evento == "Execução Interrompida" for h in SyncHistory.query.all())
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = {"username": "admin", "role": "master"}
    act = client.get("/api/activity").get_json()
    assert act["busy"] is False


def test_create_app_recupera_orfas_de_uma_sessao_anterior(tmp_path, monkeypatch):
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("REGISTRALE_DB_PATH", str(tmp_path / "data" / "database.db"))
    app = create_app({"TESTING": True})
    with app.app_context():
        db.session.add(JobRun(id="velha", rotina="r", status="running", inicio="2026-11-24T08:00:00-03:00"))
        db.session.commit()
    app2 = create_app({"TESTING": True})  # "reinício do servidor"
    with app2.app_context():
        assert db.session.get(JobRun, "velha").status == "failed"


def _settings_app(tmp_path, monkeypatch, api_keys):
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("REGISTRALE_DB_PATH", str(tmp_path / "data" / "database.db"))
    app = create_app({"TESTING": True})
    with app.app_context():
        from app.models import Settings

        rec = Settings.query.filter_by(key="global_settings").first() or Settings(key="global_settings")
        rec.set_value({"api_keys": api_keys})
        db.session.add(rec)
        db.session.commit()
    return app


def test_job_do_gestaoclick_so_existe_com_interruptor_ligado_e_chaves(tmp_path, monkeypatch):
    chaves = {"gestaoclick_access_token": "a", "gestaoclick_secret_token": "b"}
    app = _settings_app(tmp_path, monkeypatch, {**chaves, "gestaoclick_auto_sync": True})
    sched = scheduler.RegistraleScheduler(app, db_path=tmp_path / "jobs.db")
    with app.app_context():
        assert sched._sync_gestaoclick_job() is True
        job = sched.scheduler.get_job("gestaoclick_auto_sync")
        assert job is not None and job.name == "gestaoclick_sync|60"
        assert str(job.func_ref) == "rodou_dashboard.app.runtime.scheduler:_run_scheduled_gestaoclick_sync"
        # desligar remove o job
        from app.models import Settings

        rec = Settings.query.filter_by(key="global_settings").first()
        rec.set_value({"api_keys": {**chaves, "gestaoclick_auto_sync": False}})
        db.session.commit()
        assert sched._sync_gestaoclick_job() is False
        assert sched.scheduler.get_job("gestaoclick_auto_sync") is None
        # ligado, mas sem chaves: não agenda
        rec.set_value({"api_keys": {"gestaoclick_auto_sync": True}})
        db.session.commit()
        assert sched._sync_gestaoclick_job() is False


def test_execucao_agendada_do_gestaoclick_sincroniza_e_registra_no_historico(tmp_path, monkeypatch):
    from app.models import SyncHistory

    app = _settings_app(tmp_path, monkeypatch, {"gestaoclick_auto_sync": True})
    monkeypatch.setattr(scheduler, "_APP_REF", app)
    chamadas = []
    monkeypatch.setattr("app.services.sync_cnpj.executar_sincronizacao", lambda: chamadas.append("sync"))
    # A gravação no SQLite acontece dentro de executar_sincronizacao (sem passo extra via JSON).
    monkeypatch.setattr("app.services.dag_config_service.sync_json_to_db", lambda: chamadas.append("db"))
    scheduler._run_scheduled_gestaoclick_sync()
    assert chamadas == ["sync"]
    with app.app_context():
        assert any("GestãoClick" in (h.detalhes or "") for h in SyncHistory.query.all())
