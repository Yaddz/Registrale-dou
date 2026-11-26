"""Nova tentativa automática do dia, de ponta a ponta e offline (Etapa 6 simulada).

Cadeia exercitada com as peças reais: ``scheduler._run_scheduled_routine`` →
``LocalExecutor`` (thread real, ``runner.run_search_block`` real) →
``watch_dag_and_update_mentions`` (grava menções, monta e envia o e-mail) →
``_pending_in_runs`` → ``_schedule_retry`` num ``RegistraleScheduler`` real
(APScheduler + jobstore SQLite, pausado) → o job agendado é executado pelo
mesmo ``run_job`` que o APScheduler usa, inclusive a regra de ``misfire``.

O que é simulado: o relógio (``datetime.now`` do agendador e do APScheduler),
a fonte do DOU (buscadores injetados no executor) e o servidor SMTP.
Nada acessa a rede nem dorme.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import email
from pathlib import Path
import smtplib
import sys
from typing import Any, Dict, List, Optional

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1].parent
LOCAL_DIR = Path(__file__).resolve().parent
for p in (REPO_ROOT, LOCAL_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_MISSED  # noqa: E402
import apscheduler.executors.base as aps_base  # noqa: E402

import rotina_teste  # noqa: E402
from rodou_dashboard.app import create_app  # noqa: E402
from rodou_dashboard.app.models import JobRun, Mention, Settings, SyncHistory, db  # noqa: E402
from rodou_dashboard.app.runtime import executor as executor_mod  # noqa: E402
from rodou_dashboard.app.runtime import pg_portable  # noqa: E402
from rodou_dashboard.app.runtime import scheduler  # noqa: E402
from rodou_dashboard.app.runtime.executor import LocalExecutor  # noqa: E402
from rodou_dashboard.app.services import inlabs_service  # noqa: E402

BRT = timezone(timedelta(hours=-3))
DAY = "2026-11-24"  # terça-feira
DAY_BR = "24/11/2026"
ROUTINE = "Pesquisa_cnpj.yaml"
RETRY_JOB_ID = f"retry::{ROUTINE}"
DEST = "analista@example.com"

TERMS = rotina_teste.test_terms()
CNPJ_A, CNPJ_B = TERMS[0], TERMS[1]


def _pub(pub_id: str, section: str, cnpj: str) -> Dict[str, Any]:
    fmt = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    return {
        "id": pub_id,
        "section": section,
        "date": DAY_BR,
        "abstract": f"Ato de teste {pub_id} referente ao CNPJ {fmt}.",
        "href": f"https://www.in.gov.br/web/dou/-/{pub_id}",
        "title": f"Ato {pub_id}",
    }


PUB_SECAO_1 = _pub("ato-secao1-111", "DOU - Seção 1", CNPJ_A)
PUB_EXTRA = _pub("ato-extra-222", "DOU - Edição Extra", CNPJ_B)


# ─── Relógio simulado ──────────────────────────────────────────────────────────


class Clock:
    """Relógio único para o agendador do app e para o APScheduler."""

    def __init__(self) -> None:
        self.now = datetime(2026, 11, 24, 14, 5, tzinfo=BRT)

    def set(self, hour: int, minute: int = 5, day: int = 24) -> datetime:
        self.now = datetime(2026, 11, day, hour, minute, tzinfo=BRT)
        return self.now


def _fake_datetime(clock: Clock) -> type:
    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return clock.now.astimezone(tz) if tz is not None else clock.now.replace(tzinfo=None)

    return FakeDateTime


# ─── Fonte do DOU simulada ────────────────────────────────────────────────────


class FakeSource:
    """PDF integral do dia + API do DOU.

    ``extra_publicada=False`` reproduz o caso das 14h: a Edição Extra ainda não
    saiu no PDF e a API responde vazio, o que não prova "sem menções" (cobertura
    provisória → execução ``partial``).
    """

    def __init__(self) -> None:
        self.extra_publicada = False
        self.pdf_calls = 0
        self.api_calls = 0

    def pdf(self, terms, sections, ref_date, report=None, confirm_with_api=None, strict_confirm=False):
        self.pdf_calls += 1
        pubs_by_term: Dict[str, Dict[str, List[Dict[str, Any]]]] = {CNPJ_A: {"Órgão de teste": [dict(PUB_SECAO_1)]}}
        if self.extra_publicada:
            pubs_by_term[CNPJ_B] = {"Órgão de teste": [dict(PUB_EXTRA)]}
            return {"single_group": pubs_by_term}, []
        if report is not None:
            report["sections"] = {"extra": {"status": "falhou", "provisional": True, "detail": "PDF da Edição Extra ainda não publicado"}}
        return {"single_group": pubs_by_term}, ["extra"]

    def exec_search(self, **kwargs):  # API do DOU (completa seções que faltaram no PDF)
        self.api_calls += 1
        return {}


class _Unused:
    def exec_search(self, **kwargs):
        raise AssertionError("buscador que não deveria ser usado")


# ─── SMTP simulado ────────────────────────────────────────────────────────────


class SmtpBox:
    def __init__(self) -> None:
        self.sent: List[str] = []
        self.fail = False

    def factory(self):
        box = self

        class FakeSMTP:
            def __init__(self, *a, **k):
                pass

            def starttls(self):
                pass

            def login(self, *a):
                pass

            def sendmail(self, frm, to, raw):
                if box.fail:
                    raise smtplib.SMTPServerDisconnected("servidor SMTP simulado fora do ar")
                box.sent.append(raw)

            def quit(self):
                pass

        return FakeSMTP

    def bodies(self) -> List[str]:
        out = []
        for raw in self.sent:
            msg = email.message_from_string(raw)
            html = "".join(
                part.get_payload(decode=True).decode("utf-8", errors="replace")
                for part in msg.walk()
                if part.get_content_type() == "text/html"
            )
            out.append(html)
        return out


# ─── Ambiente ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def env(tmp_path, monkeypatch):
    # Sem INLABS local (instalação padrão) e contingência pelo PDF integral.
    monkeypatch.delenv("INLABS_DB_URL", raising=False)
    monkeypatch.setenv("REGISTRALE_INLABS_FALLBACK", "pdf")
    monkeypatch.setattr(pg_portable, "get_pg_bin_dir", lambda: None)
    pg_portable.reset_portable_postgres_for_tests()
    inlabs_service.reset_inlabs_state_for_tests()

    data_dir = tmp_path / "data"
    routines = tmp_path / "rotinas"
    pdfs = tmp_path / "pdfs"
    for d in (data_dir, routines, pdfs):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("REGISTRALE_DB_PATH", str(data_dir / "database.db"))
    monkeypatch.setenv("REGISTRALE_ROUTINES_DIR", str(routines))
    monkeypatch.setenv("REGISTRALE_PDF_DIR", str(pdfs))  # nunca a pasta real de PDFs

    routine = rotina_teste.build_test_routine(["INLABS"], routine_id="Pesquisa_cnpj")
    routine["dag"]["report"]["emails"] = [DEST]
    (routines / ROUTINE).write_text(yaml.safe_dump(routine, allow_unicode=True), encoding="utf-8")

    app = create_app({"TESTING": True})
    with app.app_context():
        db.create_all()
        rec = Settings.query.filter_by(key="global_settings").first() or Settings(key="global_settings")
        rec.set_value({"smtp": {"enabled": True, "server": "smtp.example.com", "port": "587",
                                "user": "remetente@example.com", "from_email": "remetente@example.com"}})
        db.session.add(rec)
        db.session.commit()

    clock = Clock()
    monkeypatch.setattr(scheduler, "datetime", _fake_datetime(clock))
    monkeypatch.setattr(scheduler, "_APP_REF", app)
    monkeypatch.setattr(scheduler, "_run_scheduled_pdf_archive", lambda d: None)  # arquivamento baixa PDFs reais

    source = FakeSource()
    searchers = {
        "DOU": source, "INLABS": _Unused(), "QD": _Unused(), "DOESP": _Unused(),
        "INLABS_FALLBACK": source.pdf, "INLABS_HAS_DATE": lambda d: False,
    }
    ex = LocalExecutor(app=app, max_workers=1, searchers=searchers)
    monkeypatch.setattr(executor_mod, "_LOCAL_EXECUTOR_INSTANCE", ex)

    sched = scheduler.RegistraleScheduler(app, db_path=tmp_path / "scheduler_jobs.db")
    sched.start()
    sched.scheduler.pause()  # nada roda pelo relógio real; os jobs são disparados pelo teste
    monkeypatch.setattr(scheduler, "_SCHEDULER_INSTANCE", sched)

    smtp = SmtpBox()
    monkeypatch.setattr(smtplib, "SMTP", smtp.factory())

    yield {"app": app, "clock": clock, "source": source, "sched": sched, "smtp": smtp, "executor": ex}

    sched.scheduler.remove_all_jobs()  # job vencido pelo relógio real não pode disparar no desligamento
    sched.shutdown(wait=False)
    ex.shutdown(wait=True)
    pg_portable.reset_portable_postgres_for_tests()
    inlabs_service.reset_inlabs_state_for_tests()


def _retry_job(env) -> Optional[Any]:
    return env["sched"].scheduler.get_job(RETRY_JOB_ID)


def _fire_retry(env, delay_seconds: int = 30) -> List[Any]:
    """Dispara o job de nova tentativa como o APScheduler faria no horário (+ ``delay_seconds``)."""
    job = _retry_job(env)
    assert job is not None, "nenhuma nova tentativa agendada"
    run_time = job.next_run_time
    env["sched"].scheduler.remove_job(job.id)  # job de data única sai do jobstore ao disparar
    fire_at = run_time + timedelta(seconds=delay_seconds)
    env["clock"].now = fire_at.astimezone(BRT)

    class ApsNow(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return fire_at.astimezone(tz) if tz is not None else fire_at.replace(tzinfo=None)

    original = aps_base.datetime
    aps_base.datetime = ApsNow
    try:
        return aps_base.run_job(job, "default", [run_time], "apscheduler.executors.default")
    finally:
        aps_base.datetime = original


def _runs(env) -> List[JobRun]:
    with env["app"].app_context():
        return JobRun.query.order_by(JobRun.inicio).all()


def _events(env, evento: str) -> List[str]:
    with env["app"].app_context():
        return [h.detalhes for h in SyncHistory.query.filter_by(evento=evento).order_by(SyncHistory.id).all()]


def _mention_ids(env) -> set:
    with env["app"].app_context():
        return {m.id for m in Mention.query.all()}


ID_SECAO_1 = f"{CNPJ_A}_{PUB_SECAO_1['id']}"
ID_EXTRA = f"{CNPJ_B}_{PUB_EXTRA['id']}"


# ─── 1. Cadeia feliz ──────────────────────────────────────────────────────────


def test_cadeia_feliz_partial_as_14h_retry_as_15h_conclui_e_avisa_so_o_novo(env):
    env["clock"].set(14, 5)
    scheduler._run_scheduled_routine(ROUTINE)

    runs = _runs(env)
    assert [r.status for r in runs] == ["partial"]
    assert "Edição Extra" in (runs[0].erro or "")
    # Com o e-mail enviado, o histórico registra "E-mail Enviado" + "Busca com Pendências"
    # ("Busca Concluída com Pendências" é o nome usado quando não há envio; ver teste 3).
    pendencias = _events(env, "Busca com Pendências")
    assert len(pendencias) == 1 and "Edição Extra" in pendencias[0] and "incompleto" in pendencias[0]
    assert len(_events(env, "E-mail Enviado")) == 1
    assert "Nova tentativa automática em 1 hora" in _events(env, "Busca Incompleta")[0]

    job = _retry_job(env)
    assert job is not None
    assert job.next_run_time.astimezone(BRT) == datetime(2026, 11, 24, 15, 5, tzinfo=BRT)
    assert list(job.args) == [ROUTINE, 1, DAY]  # tentativa 1/4
    assert job.misfire_grace_time == scheduler.RETRY_MISFIRE_GRACE_SECONDS
    assert job.func_ref == "rodou_dashboard.app.runtime.scheduler:_run_scheduled_routine"

    # 1º e-mail: a menção da Seção 1 já encontrada
    bodies = env["smtp"].bodies()
    assert len(bodies) == 1 and PUB_SECAO_1["href"] in bodies[0]
    assert _mention_ids(env) == {ID_SECAO_1}

    # 15h: a Edição Extra saiu
    env["source"].extra_publicada = True
    events = _fire_retry(env)
    assert [e.code for e in events] == [EVENT_JOB_EXECUTED]

    runs = _runs(env)
    assert [r.status for r in runs] == ["partial", "success"]
    assert _retry_job(env) is None  # sem nova tentativa
    assert len(_events(env, "Busca Incompleta")) == 1
    assert _mention_ids(env) == {ID_SECAO_1, ID_EXTRA}

    # 2º e-mail: só a menção nova; a da Seção 1 não se repete
    bodies = env["smtp"].bodies()
    assert len(bodies) == 2
    assert PUB_EXTRA["href"] in bodies[1]
    assert PUB_SECAO_1["href"] not in bodies[1]


# ─── 2. Limite de tentativas ─────────────────────────────────────────────────


def test_fonte_sempre_incompleta_faz_exatamente_4_novas_tentativas(env):
    env["clock"].set(10, 5)
    scheduler._run_scheduled_routine(ROUTINE)

    attempts = []
    while _retry_job(env) is not None:
        attempts.append(_retry_job(env).args[1])
        assert len(attempts) <= scheduler.RETRY_MAX_ATTEMPTS, "agendou além do limite"
        _fire_retry(env)

    assert attempts == [1, 2, 3, 4]
    assert scheduler.RETRY_MAX_ATTEMPTS == 4
    assert [r.status for r in _runs(env)] == ["partial"] * 5  # original + 4 novas tentativas
    incompletas = _events(env, "Busca Incompleta")
    assert len(incompletas) == 5
    assert all("Nova tentativa automática em 1 hora" in d for d in incompletas[:4])
    assert "Sem novas tentativas hoje" in incompletas[4]
    assert env["clock"].now.hour == 14  # última tentativa às 14h05, bem antes do corte das 22h
    # Só o primeiro e-mail sai: as novas tentativas não acharam nada novo.
    assert len(env["smtp"].sent) == 1


# ─── 3. Corte das 22h ─────────────────────────────────────────────────────────


def test_partial_as_21h10_nao_agenda_nova_tentativa(env):
    env["clock"].set(21, 10)
    env["smtp"].fail = True  # sem envio, o histórico usa "Busca Concluída com Pendências"
    scheduler._run_scheduled_routine(ROUTINE)

    assert [r.status for r in _runs(env)] == ["partial"]
    pendencias = _events(env, "Busca Concluída com Pendências")
    assert len(pendencias) == 1 and "INCOMPLETO" in pendencias[0]
    assert _mention_ids(env) == {ID_SECAO_1}
    assert _retry_job(env) is None  # 22h10 >= 22h
    assert "Sem novas tentativas hoje" in _events(env, "Busca Incompleta")[0]


# ─── 4. PC desligado ──────────────────────────────────────────────────────────


def test_nova_tentativa_perdida_com_pc_desligado_nao_roda_no_dia_seguinte(env):
    env["clock"].set(14, 5)
    scheduler._run_scheduled_routine(ROUTINE)
    assert _retry_job(env) is not None
    pdf_calls = env["source"].pdf_calls

    # O PC ficou desligado das 15h às 8h do dia seguinte: o APScheduler acorda com o job vencido.
    run_time = _retry_job(env).next_run_time
    atraso = (datetime(2026, 11, 25, 8, 0, tzinfo=BRT) - run_time).total_seconds()
    events = _fire_retry(env, delay_seconds=int(atraso))
    assert [e.code for e in events] == [EVENT_JOB_MISSED]
    assert env["source"].pdf_calls == pdf_calls  # nada foi executado
    assert len(_runs(env)) == 1

    # Mesmo que o job fosse disparado (ex.: grace maior no futuro), a data do dia o barra.
    env["clock"].set(8, 0, day=25)
    scheduler._run_scheduled_routine(ROUTINE, 1, DAY)
    assert len(_runs(env)) == 1 and env["source"].pdf_calls == pdf_calls

    # Dentro da folga (atraso de 5 min) a nova tentativa roda normalmente.
    env["clock"].set(14, 5)
    scheduler._run_scheduled_routine(ROUTINE)
    assert _retry_job(env) is not None
    events = _fire_retry(env, delay_seconds=300)
    assert [e.code for e in events] == [EVENT_JOB_EXECUTED]
    assert env["source"].pdf_calls == pdf_calls + 2


# ─── 5. SMTP falhando na nova tentativa ─────────────────────────────────────────


def test_smtp_falhando_na_nova_tentativa_preserva_as_mencoes(env):
    env["clock"].set(14, 5)
    scheduler._run_scheduled_routine(ROUTINE)
    assert len(env["smtp"].sent) == 1

    env["source"].extra_publicada = True
    env["smtp"].fail = True
    _fire_retry(env)

    assert [r.status for r in _runs(env)] == ["partial", "success"]
    assert _mention_ids(env) == {ID_SECAO_1, ID_EXTRA}  # gravadas antes do envio
    assert len(env["smtp"].sent) == 1  # o 2º envio falhou
    erros = _events(env, "Erro Envio E-mail")
    assert len(erros) == 1
    assert _retry_job(env) is None
    # A conclusão foi registrada antes do erro de e-mail (Etapa 2).
    with env["app"].app_context():
        eventos = [h.evento for h in SyncHistory.query.order_by(SyncHistory.id).all()]
    assert "Busca Concluída" in eventos
    assert eventos.index("Busca Concluída") < eventos.index("Erro Envio E-mail")
