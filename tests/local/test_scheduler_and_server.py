"""Testes offline do Sprint 3: servidor waitress, lock, scheduler, paths, logs e erro SMTP."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import time
from unittest.mock import MagicMock

import pytest

from rodou_dashboard.app import create_app
from rodou_dashboard.app.models import Mention, Settings, SyncHistory, db
from rodou_dashboard.app.runtime import paths
from rodou_dashboard.app.runtime.logging_setup import (
    configure_logging,
    list_log_files,
    read_log_tail,
    run_log_context,
)
from rodou_dashboard.app.runtime.scheduler import (
    RegistraleScheduler,
    init_scheduler,
    shutdown_scheduler,
)
from rodou_dashboard.app.runtime.server import InstanceLockError, acquire_instance_lock


@pytest.fixture
def local_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    routines_dir = data_dir / "rotinas"
    logs_dir = data_dir / "logs"
    sessions_dir = data_dir / "sessions"
    data_dir.mkdir(parents=True)
    routines_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)
    sessions_dir.mkdir(parents=True)

    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("REGISTRALE_ROUTINES_DIR", str(routines_dir))
    monkeypatch.setenv("REGISTRALE_LOGS_DIR", str(logs_dir))
    monkeypatch.setenv("REGISTRALE_DB_PATH", str(data_dir / "database.db"))
    monkeypatch.setenv("REGISTRALE_SCHEDULER_DB_PATH", str(data_dir / "scheduler_jobs.db"))
    monkeypatch.setenv("SESSION_FILE_DIR", str(sessions_dir))
    return tmp_path


class TestPathsAndLock:
    def test_platformdirs_used_in_local_mode_without_override(self, tmp_path, monkeypatch):
        import platformdirs

        monkeypatch.delenv("REGISTRALE_DATA_DIR", raising=False)
        monkeypatch.delenv("DATA_DIR", raising=False)
        monkeypatch.delenv("REGISTRALE_LOGS_DIR", raising=False)
        monkeypatch.delenv("LOGS_DIR", raising=False)
        fake_user_dir = tmp_path / "AppData" / "Local" / "Registrale"
        monkeypatch.setattr(platformdirs, "user_data_dir", lambda appname, appauthor=False: str(fake_user_dir))

        resolved = paths.get_data_dir(create=True)
        assert resolved == fake_user_dir.resolve()
        assert resolved.is_dir()
        assert paths.get_logs_dir(create=False) == resolved / "logs"
        assert paths.get_inlabs_dir(create=False) == resolved / "inlabs"

    def test_instance_lock_blocks_second_instance(self, tmp_path):
        lock_file = tmp_path / "registrale.lock"
        with acquire_instance_lock(lock_file):
            with pytest.raises(InstanceLockError):
                with acquire_instance_lock(lock_file):
                    pass

        # Após liberar, pode adquirir novamente
        with acquire_instance_lock(lock_file):
            assert lock_file.exists()


class TestLoggingAndAdminEndpoint:
    def test_rotating_log_and_run_log_context(self, local_env):
        logs_dir = local_env / "data" / "logs"
        log_file = configure_logging(logs_dir=logs_dir, max_bytes=200, backup_count=2)
        assert log_file == (logs_dir / "registrale.log").resolve()

        test_logger = logging.getLogger("registrale.test")
        for i in range(15):
            test_logger.info("Linha de teste de rotação %d - %s", i, "x" * 30)

        assert log_file.exists()
        assert (logs_dir / "registrale.log.1").exists()

        with run_log_context("local__rotina__2026-11-23__abc123", run_logs_dir=logs_dir / "runs") as run_log:
            test_logger.info("Mensagem exclusiva da execução")

        assert run_log.exists()
        assert "Mensagem exclusiva da execução" in run_log.read_text(encoding="utf-8")

        files = list_log_files(logs_dir=logs_dir)
        paths_list = [f["path"] for f in files]
        assert "registrale.log" in paths_list
        assert f"runs/{run_log.name}" in paths_list

        with pytest.raises(ValueError):
            read_log_tail("../database.db", logs_dir=logs_dir)

    def test_admin_logs_endpoint(self, local_env):
        logs_dir = local_env / "data" / "logs"
        configure_logging(logs_dir=logs_dir)
        logging.getLogger("registrale.api").info("Entrada de log para o painel")

        app = create_app({"TESTING": True})
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user"] = {"username": "admin", "role": "master"}

        resp = client.get("/api/admin/logs?file=registrale.log&lines=50")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["status"] == "success"
        assert any(f["path"] == "registrale.log" for f in payload["files"])
        assert "Entrada de log para o painel" in payload["tail"]["content"]


class TestScheduler:
    def test_scheduler_loads_routines_and_sheets_and_reloads_on_change(self, local_env):
        routines_dir = local_env / "data" / "rotinas"
        (routines_dir / "Pesquisa_cnpj.yaml").write_text(
            "dag:\n"
            "  id: pesquisa_cnpj_anvisa\n"
            "  schedule: '0 8 * * MON-FRI'\n"
            "  active: true\n"
            "  search:\n"
            "    - header: TEST\n"
            "      terms: ['00097446000186']\n",
            encoding="utf-8",
        )
        (routines_dir / "pausada.yaml").write_text(
            "dag:\n"
            "  id: rotina_pausada\n"
            "  schedule: '0 9 * * *'\n"
            "  active: false\n"
            "  search:\n"
            "    - header: PAUSADA\n"
            "      terms: ['abc']\n",
            encoding="utf-8",
        )

        app = create_app({"TESTING": True})
        with app.app_context():
            s_rec = Settings(key="global_settings")
            s_rec.set_value(
                {
                    "google_sheets": {
                        "auto_sync": True,
                        "sync_interval": 30,
                        "spreadsheet_url": "https://docs.google.com/spreadsheets/d/fake",
                        "credentials_json": '{"type":"service_account"}',
                    }
                }
            )
            db.session.add(s_rec)
            db.session.commit()

        sched = init_scheduler(app, start=True)
        try:
            jobs = {j["id"]: j for j in sched.list_jobs()}
            assert "routine::Pesquisa_cnpj.yaml" in jobs
            assert "routine::pausada.yaml" not in jobs
            assert "sheets_auto_sync" in jobs
            assert jobs["sheets_auto_sync"]["name"] == "sheets_sync|30"
        finally:
            shutdown_scheduler(wait=False)

    def test_misfire_executes_once_on_startup_after_restart(self, local_env, monkeypatch):
        routines_dir = local_env / "data" / "rotinas"
        (routines_dir / "Pesquisa_cnpj.yaml").write_text(
            "dag:\n"
            "  id: pesquisa_cnpj_anvisa\n"
            "  schedule: '0 8 * * *'\n"
            "  active: true\n"
            "  search:\n"
            "    - header: TEST\n"
            "      terms: ['00097446000186']\n",
            encoding="utf-8",
        )

        app = create_app({"TESTING": True})
        jobs_db = local_env / "data" / "scheduler_jobs.db"

        executed = []
        import rodou_dashboard.app.runtime.scheduler as sched_mod

        monkeypatch.setattr(sched_mod, "_run_scheduled_routine", lambda rf: executed.append(rf))

        # 1. Cria job persistido, encerra e simula passagem de tempo (PC desligado às 8h)
        s1 = RegistraleScheduler(app, db_path=jobs_db)
        s1.start()
        s1.reload()
        s1.shutdown(wait=True)
        assert executed == []

        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

        store = SQLAlchemyJobStore(url=f"sqlite:///{jobs_db}")
        store.start(s1.scheduler, "default")
        job = store.lookup_job("routine::Pesquisa_cnpj.yaml")
        assert job is not None
        job.next_run_time = datetime.now(timezone(timedelta(hours=-3))) - timedelta(hours=2)
        store.update_job(job)
        store.shutdown()

        # 2. Ao reiniciar ("ligar o PC"), deve disparar a execução perdida uma única vez
        s2 = init_scheduler(app, db_path=jobs_db, start=True)
        try:
            deadline = time.monotonic() + 5.0
            while not executed and time.monotonic() < deadline:
                time.sleep(0.05)
            assert executed == ["Pesquisa_cnpj.yaml"]
        finally:
            shutdown_scheduler(wait=False)


class TestSmtpErrorLabel:
    def test_watch_routine_smtp_error_saves_mentions_and_labels_error(self, local_env, monkeypatch):
        from rodou_dashboard.app.routes import dags as dags_mod
        from rodou_dashboard.app.services import email_service

        app = create_app({"TESTING": True})

        class FakeExecutor:
            def wait(self, run_ids, timeout=1800):
                return True, {rid: "success" for rid in run_ids}

            def result(self, run_id, routine=None):
                return [
                    {
                        "group_name": "single_group",
                        "search_report": {
                            "00097446000186": {
                                "ANVISA": [
                                    {
                                        "title": "RESOLUÇÃO-RE",
                                        "href": "https://www.in.gov.br/web/dou/-/x-1",
                                        "abstract": "Empresa 00.097.446/0001-86 citada.",
                                        "date": "23/11/2026",
                                        "section": "Seção 1",
                                        "matched_cnpj": "00097446000186",
                                        "is_branch": False,
                                        "root_only": False,
                                    }
                                ]
                            }
                        },
                    }
                ]

        monkeypatch.setattr(dags_mod, "get_executor", lambda: FakeExecutor())

        class FailingSender:
            def __init__(self, *args, **kwargs):
                pass

            def send_custom_email(self, *args, **kwargs):
                raise RuntimeError("SMTP connection refused")

        monkeypatch.setattr(email_service, "EmailSender", FailingSender)

        # SMTP ligado e com servidor (desligado é o padrão desde a 1.3.2)
        with app.app_context():
            rec = Settings.query.filter_by(key="global_settings").first() or Settings(key="global_settings")
            val = rec.get_value() if rec.id else {}
            val = val if isinstance(val, dict) else {}
            val["smtp"] = {"enabled": True, "server": "smtp.exemplo.com", "port": "587", "user": "u@exemplo.com"}
            rec.set_value(val)
            db.session.add(rec)
            db.session.commit()

        dags_mod.watch_dag_and_update_mentions(
            app.app_context(),
            [{"dag_id": "pesquisa_cnpj_anvisa", "dag_run_id": "local__test__1"}],
            "Pesquisa_cnpj.yaml",
            routine_emails=["analista@exemplo.com"],
            logical_date="2026-11-23",
        )

        with app.app_context():
            assert Mention.query.count() == 1
            events = [h.evento for h in SyncHistory.query.order_by(SyncHistory.id.asc()).all()]
            assert "Erro Envio E-mail" in events
            assert "Busca Concluída" in events
            assert events.index("Busca Concluída") < events.index("Erro Envio E-mail")
            assert "Erro (Busca Mensal)" not in events
