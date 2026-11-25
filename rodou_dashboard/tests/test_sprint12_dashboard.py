"""Testes offline do Sprint 12: estado dos interruptores, desativado != pendente, SMTP desligado e atividade."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from rodou_dashboard.app import create_app
from rodou_dashboard.app.models import Company, JobRun, Mention, Settings, db


@pytest.fixture
def app_ctx(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("REGISTRALE_DISABLE_SCHEDULER", "1")
    monkeypatch.delenv("INLABS_DB_URL", raising=False)

    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        yield app, data_dir


def _login_master(client):
    with client.session_transaction() as sess:
        sess["user"] = {"username": "admin", "role": "master"}
        sess["expires_at"] = 9999999999


def test_switches_persist_partial_updates_and_gestaoclick_default_off(app_ctx):
    app, _ = app_ctx
    client = app.test_client()
    _login_master(client)

    # Padrão do GestãoClick quando chave ausente = False
    r0 = client.get("/api/settings")
    assert r0.status_code == 200
    s0 = r0.get_json()["settings"]
    assert s0["api_keys"]["gestaoclick_auto_sync"] is False
    assert s0["google_sheets"]["auto_sync"] is False
    assert s0["google_sheets"]["delete_obsolete"] is False
    assert s0["smtp"]["enabled"] is False  # desligado por padrão (1.3.2)

    # Salva SMTP completo primeiro
    r_smtp = client.post(
        "/api/save_settings",
        json={
            "smtp": {
                "enabled": True,
                "server": "smtp.exemplo.com",
                "port": "587",
                "user": "bot@exemplo.com",
                "password": "segredo",
                "from_email": "bot@exemplo.com",
            }
        },
    )
    assert r_smtp.status_code == 200

    # Atualização parcial de cada interruptor (sem enviar os outros campos)
    for payload in [
        {"smtp": {"enabled": False}},
        {"google_sheets": {"auto_sync": True}},
        {"google_sheets": {"delete_obsolete": True}},
        {"api_keys": {"gestaoclick_auto_sync": True}},
        {"pdf_archive": {"enabled": False}},
    ]:
        resp = client.post("/api/save_settings", json=payload)
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "success"

    # Toggle de login_required
    r_acc = client.post("/api/admin/access_settings", json={"login_required": True})
    assert r_acc.status_code == 200
    assert r_acc.get_json()["login_required"] is True

    # Verifica que os valores sobreviveram e que campos de SMTP não foram apagados
    r1 = client.get("/api/settings")
    assert r1.status_code == 200
    s1 = r1.get_json()["settings"]
    assert s1["smtp"]["enabled"] is False
    assert s1["smtp"]["server"] == "smtp.exemplo.com"
    assert s1["smtp"]["user"] == "bot@exemplo.com"
    assert s1["google_sheets"]["auto_sync"] is True
    assert s1["google_sheets"]["delete_obsolete"] is True
    assert s1["api_keys"]["gestaoclick_auto_sync"] is True
    assert s1["pdf_archive"]["enabled"] is False


def test_integrations_status_disabled_is_not_pending(app_ctx):
    app, _ = app_ctx
    client = app.test_client()
    _login_master(client)

    # Desliga SMTP, Sheets, GestãoClick, PDF; simula INLABS local indisponível
    client.post(
        "/api/save_settings",
        json={
            "smtp": {"enabled": False},
            "google_sheets": {"auto_sync": False},
            "api_keys": {"gestaoclick_auto_sync": False},
            "pdf_archive": {"enabled": False},
        },
    )

    with patch("rodou_dashboard.app.services.inlabs_service.is_inlabs_local_available", return_value=False):
        r = client.get("/api/system/integrations_status")
        assert r.status_code == 200
        data = r.get_json()
        assert data["pending_count"] == 0
        assert data["all_configured"] is True
        by_id = {i["id"]: i for i in data["integrations"]}
        assert by_id["smtp"]["status"] == "disabled"
        assert by_id["google_sheets"]["status"] == "disabled"
        assert by_id["gestaoclick"]["status"] == "disabled"
        assert by_id["pdf_archive"]["status"] == "disabled"
        assert by_id["inlabs"]["status"] == "unavailable"

        # Se ligar Google Sheets sem credenciais, vira pendência
        client.post("/api/save_settings", json={"google_sheets": {"auto_sync": True}})
        r2 = client.get("/api/system/integrations_status")
        data2 = r2.get_json()
        assert data2["pending_count"] == 1
        assert data2["all_configured"] is False
        assert data2["next_pending"]["id"] == "google_sheets"


def test_smtp_disabled_allows_routines_without_email_and_blocks_sends(app_ctx):
    app, _ = app_ctx
    client = app.test_client()
    _login_master(client)

    # Com SMTP ligado, exige e-mail nas duas rotas
    client.post("/api/save_settings", json={"smtp": {"enabled": True}})
    r_fail1 = client.post(
        "/api/routines",
        json={
            "name": "Teste Sem Email",
            "schedule": "0 8 * * MON-FRI",
            "terms": ["00.000.000"],
            "sections": ["SECAO_1"],
            "emails": [],
            "source": "DOU",
        },
    )
    assert r_fail1.status_code == 400
    assert "e-mail" in r_fail1.get_json()["message"].lower()

    r_fail2 = client.post(
        "/api/system/configure_main_dag",
        json={"emails": [], "subject": "Teste"},
    )
    assert r_fail2.status_code == 400

    # Desliga SMTP -> salva rotina sem e-mail e bloqueia envios manuais/teste
    client.post("/api/save_settings", json={"smtp": {"enabled": False}})
    r_ok1 = client.post(
        "/api/routines",
        json={
            "name": "Teste Sem Email",
            "schedule": "0 8 * * MON-FRI",
            "terms": ["00.000.000"],
            "sections": ["SECAO_1"],
            "emails": [],
            "source": "DOU",
        },
    )
    assert r_ok1.status_code == 200

    r_ok2 = client.post(
        "/api/system/configure_main_dag",
        json={"emails": [], "subject": "Teste"},
    )
    assert r_ok2.status_code == 200

    r_test = client.post("/api/test_smtp", json={"test_email": "a@b.com"})
    assert r_test.status_code == 400
    assert "desativado" in r_test.get_json()["message"].lower()

    r_send = client.post("/api/send_email", json={"to_emails": ["a@b.com"], "subject": "Oi", "body_html": "<p>Oi</p>"})
    assert r_send.status_code == 400
    assert "desativado" in r_send.get_json()["message"].lower()


def test_activity_endpoint_and_cache_invalidation(app_ctx):
    app, _ = app_ctx
    client = app.test_client()
    _login_master(client)

    # 1. Ocioso
    r_idle = client.get("/api/activity")
    assert r_idle.status_code == 200
    d_idle = r_idle.get_json()
    assert d_idle["busy"] is False
    assert d_idle["state"] == "idle"
    assert d_idle["label"] == "Ocioso"

    # 2. Job rodando
    job = JobRun(
        id="run-123",
        rotina="Pesquisa_cnpj.yaml",
        data="2026-11-23",
        status="running",
        inicio="2026-11-23T08:00:00",
    )
    db.session.add(job)
    db.session.commit()

    r_run = client.get("/api/activity")
    d_run = r_run.get_json()
    assert d_run["busy"] is True
    assert d_run["state"] == "running"
    assert "Pesquisa_cnpj" in d_run["label"]
    assert "2026-11-23" in d_run["label"]

    # 3. Job concluído com pendências (partial)
    job.status = "partial"
    db.session.commit()
    r_part = client.get("/api/activity")
    d_part = r_part.get_json()
    assert d_part["busy"] is False
    assert d_part["state"] == "partial"
    assert "pendências" in d_part["label"].lower()

    # 4. Limpar banco invalida caches e zera KPIs imediatamente
    db.session.add(Company(nome="Teste Ltda", cnpj="24.684.423/0001-00", cnpj_norm="24684423000100", status=True))
    db.session.add(
        Mention(
            id="m-s12-1",
            empresa="Teste Ltda",
            cnpj="24.684.423/0001-00",
            cnpj_norm="24684423000100",
            data="23/11/2026",
            secao="Seção 1",
            trecho="...",
            link="https://in.gov.br/1",
        )
    )
    db.session.commit()

    r_clear = client.post("/api/admin/clear_data", json={"type": "mentions"})
    assert r_clear.status_code == 200
    r_status = client.get("/api/status?refresh=1")
    assert r_status.status_code == 200
    assert r_status.get_json()["kpis"]["mencoes_total"] == 0
