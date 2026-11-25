"""Ajustes 1.3.2: SMTP desligado por padrão, avisos só de problema real e menções por raiz."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import pytest
from flask import Flask
from flask.testing import FlaskClient

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from rodou_dashboard.app import create_app
from rodou_dashboard.app.models import Company, Mention, Settings, SyncHistory, User, db
from rodou_dashboard.app.routes.companies import cnpj_root_key, get_companies_data
from rodou_dashboard.app.routes.dags import watch_dag_and_update_mentions
from rodou_dashboard.app.services.email_service import (
    SMTP_NOT_READY_EVENT,
    EmailSender,
    SmtpNotConfiguredError,
    ensure_smtp_enabled_flag,
    is_smtp_enabled,
    is_smtp_ready,
)
from rodou_dashboard.app.services.health_alerts import (
    BRASILIA_TZ,
    HISTORY_DATE_FORMAT,
    HistoryRow,
    compute_health_alerts,
)

NOW = datetime(2026, 11, 25, 16, 0, 0, tzinfo=BRASILIA_TZ)


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Flask]:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("REGISTRALE_DB_PATH", str(data_dir / "database.db"))
    monkeypatch.setenv("REGISTRALE_DISABLE_SCHEDULER", "1")
    monkeypatch.delenv("INLABS_DB_URL", raising=False)
    monkeypatch.delenv("REGISTRALE_ROUTINES_DIR", raising=False)
    monkeypatch.delenv("DAG_CONFS_DIR", raising=False)
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username="admin").first():
            admin = User(username="admin", role="master")
            admin.set_password("admin")
            db.session.add(admin)
            db.session.commit()
        yield app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    test_client = app.test_client()
    with test_client.session_transaction() as sess:
        sess["user"] = {"username": "admin", "role": "master"}
        sess["expires_at"] = 9999999999
    return test_client


def _global_smtp() -> dict:
    rec = Settings.query.filter_by(key="global_settings").first()
    return (rec.get_value() or {}).get("smtp", {}) if rec else {}


def _set_global(value: dict) -> None:
    rec = Settings.query.filter_by(key="global_settings").first()
    if rec is None:
        rec = Settings(key="global_settings")
        db.session.add(rec)
    rec.set_value(value)
    db.session.commit()


# --- SMTP -----------------------------------------------------------------

def test_is_smtp_enabled_without_key_is_false() -> None:
    assert is_smtp_enabled({}) is False
    assert is_smtp_enabled({"server": "smtp.ex.com", "user": "u"}) is False
    assert is_smtp_enabled({"enabled": True}) is True


def test_smtp_enabled_without_server_is_not_ready() -> None:
    assert is_smtp_ready({"enabled": True, "server": ""}) is False
    assert is_smtp_ready({"enabled": True, "server": "smtp.ex.com"}) is True
    assert is_smtp_ready({"enabled": False, "server": "smtp.ex.com"}) is False


def test_send_without_server_raises_instead_of_using_localhost() -> None:
    with pytest.raises(SmtpNotConfiguredError):
        EmailSender({"enabled": True, "server": ""}).send_custom_email(["a@ex.com"], "x", "<p>x</p>")


def test_new_install_smtp_disabled(app: Flask) -> None:
    assert is_smtp_enabled() is False
    _set_global({"smtp": {"server": "", "user": ""}})
    assert ensure_smtp_enabled_flag() is True
    assert _global_smtp()["enabled"] is False


def test_ensure_flag_keeps_legacy_configured_install_enabled(app: Flask) -> None:
    _set_global({"smtp": {"server": "smtp.ex.com", "user": "u@ex.com"}})
    assert ensure_smtp_enabled_flag() is True
    assert _global_smtp()["enabled"] is True
    _set_global({"smtp": {"enabled": False, "server": "smtp.ex.com", "user": "u@ex.com"}})
    assert ensure_smtp_enabled_flag() is False
    assert _global_smtp()["enabled"] is False


def test_clear_data_writes_smtp_disabled(app: Flask, client: FlaskClient) -> None:
    _set_global({"smtp": {"server": "", "user": ""}})
    resp = client.post("/api/admin/clear_data", json={"type": "all"})
    assert resp.status_code == 200, resp.get_json()
    assert _global_smtp()["enabled"] is False


def test_routine_saves_without_email_when_smtp_disabled(app: Flask, client: FlaskClient) -> None:
    _set_global({"smtp": {"enabled": False}})
    resp = client.post("/api/system/configure_main_dag", json={
        "emails": [], "subject": "", "schedule": "0 8 * * MON-FRI", "active": True,
    })
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["status"] == "success"


def test_search_with_smtp_on_without_server_logs_single_clear_event(app: Flask) -> None:
    _set_global({"smtp": {"enabled": True, "server": ""}})
    fake = [{
        "id": "m-1", "empresa": "EMPRESA", "cnpj": "24.684.423/0001-01", "cnpj_norm": "24684423000101",
        "secao": "DO1", "data": "24/11/2026", "trecho": "x", "link": "https://www.in.gov.br/web/dou/-/x",
    }]
    with patch("rodou_dashboard.app.runtime.executor.LocalExecutor.wait", return_value=None), \
         patch("rodou_dashboard.app.routes.dags.fetch_mentions_from_dag_run", return_value=fake), \
         patch("rodou_dashboard.app.services.email_service.EmailSender.send_custom_email") as send:
        watch_dag_and_update_mentions(
            app.app_context(), [{"dag_id": "Pesquisa_cnpj.yaml", "dag_run_id": "run-1"}],
            "Pesquisa_cnpj.yaml", ["dest@ex.com"], "Assunto", "2026-11-24",
        )
        send.assert_not_called()
    events = [h.evento for h in SyncHistory.query.all()]
    assert events.count(SMTP_NOT_READY_EVENT) == 1
    assert "Erro Envio E-mail" not in events
    assert Mention.query.count() == 1


# --- Avisos da Visão geral -----------------------------------------------

def _row(evento: str, when: datetime, detalhes: str = "detalhe") -> HistoryRow:
    return HistoryRow(data=when.strftime(HISTORY_DATE_FORMAT), evento=evento, detalhes=detalhes)


def test_disabled_integrations_generate_no_alert() -> None:
    settings = {
        "smtp": {"enabled": False, "server": ""},
        "google_sheets": {"auto_sync": False},
        "api_keys": {"gestaoclick_auto_sync": False},
    }
    assert compute_health_alerts(settings, {"active": True, "emails": []}, [], NOW) == []


def test_enabled_integration_without_credentials_generates_alert() -> None:
    settings = {
        "smtp": {"enabled": True, "server": ""},
        "google_sheets": {"auto_sync": True, "credentials_json": "", "spreadsheet_url": "x"},
        "api_keys": {"gestaoclick_auto_sync": True, "gestaoclick_access_token": "a"},
    }
    ids = {a.id for a in compute_health_alerts(settings, {"active": True, "emails": []}, [], NOW)}
    assert ids == {"smtp_no_server", "main_dag_no_emails", "sheets_missing_credentials", "gestaoclick_missing_tokens"}


def test_recent_history_error_generates_alert_and_old_one_does_not() -> None:
    rows = [
        _row("Erro (Busca Mensal)", NOW - timedelta(hours=2)),
        _row("Erro Envio E-mail", NOW - timedelta(hours=30)),
        _row("Busca Concluída", NOW - timedelta(minutes=5)),
    ]
    alerts = compute_health_alerts({"smtp": {"enabled": False}}, {"active": True, "emails": []}, rows, NOW)
    assert [a.id for a in alerts] == ["monthly_search_error"]
    assert alerts[0].settings_tab == "logs"


def test_new_error_changes_alert_key() -> None:
    first = compute_health_alerts({}, {}, [_row("Erro Sync GestãoClick", NOW - timedelta(hours=3))], NOW)
    second = compute_health_alerts({}, {}, [_row("Erro Sync GestãoClick", NOW - timedelta(hours=1))], NOW)
    assert first[0].key != second[0].key


def test_health_alerts_route_empty_when_all_fine(app: Flask, client: FlaskClient) -> None:
    _set_global({"smtp": {"enabled": False}})
    data = client.get("/api/system/health_alerts").get_json()
    assert data == {"status": "ok", "alerts": []}


def test_health_alerts_route_reports_smtp_without_server(app: Flask, client: FlaskClient) -> None:
    _set_global({"smtp": {"enabled": True, "server": ""}})
    data = client.get("/api/system/health_alerts").get_json()
    assert "smtp_no_server" in [a["id"] for a in data["alerts"]]


# --- Contagem de menções por raiz ---------------------------------------

def test_cnpj_root_key_accepts_alphanumeric_and_root_only() -> None:
    assert cnpj_root_key("24.684.423/0001-00") == "24684423"
    assert cnpj_root_key("24684423") == "24684423"
    assert cnpj_root_key("12.ABC.345/01DE-35") == "12ABC345"
    assert cnpj_root_key("123") == ""


def test_company_mentions_count_by_root(app: Flask) -> None:
    db.session.add(Company(nome="SURGITEC", cnpj="24.684.423/0001-00", cnpj_norm="24684423000100", status=True))
    db.session.add(Company(nome="OUTRA", cnpj="11.222.333/0001-81", cnpj_norm="11222333000181", status=True))
    db.session.add(Mention(id="matriz", cnpj="24.684.423/0001-00", cnpj_norm="24684423000100"))
    db.session.add(Mention(id="filial", cnpj="24.684.423/0002-81", cnpj_norm="24684423000281"))
    db.session.add(Mention(id="raiz", cnpj="24.684.423", cnpj_norm="24684423"))
    db.session.commit()

    counts = {c["nome"]: c["total_mencoes"] for c in get_companies_data()}
    assert counts == {"SURGITEC": 3, "OUTRA": 0}


def test_email_errors_ignored_when_smtp_disabled() -> None:
    rows = [_row("Erro Envio E-mail", NOW - timedelta(hours=1))]
    assert compute_health_alerts({"smtp": {"enabled": False}}, {}, rows, NOW) == []
    on = compute_health_alerts({"smtp": {"enabled": True, "server": "smtp.ex.com"}}, {"active": True, "emails": ["a@ex.com"]}, rows, NOW)
    assert [a.id for a in on] == ["email_send_error"]
