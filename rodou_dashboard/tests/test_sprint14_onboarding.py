from unittest.mock import MagicMock, patch

from app.models import Company, Settings, db


def test_first_run_status_includes_onboarding_for_fresh_install(auth_client):
    r = auth_client.get("/api/admin/first_run_status")
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "success"
    ob = data["onboarding"]
    assert ob["completed"] is False
    assert ob["should_open"] is True
    assert ob["current_step"] == 1
    assert ob["total_steps"] == 9


def test_onboarding_legacy_upgrade_does_not_force_reopen(auth_client, app):
    from app.services.access_service import mark_access_onboarding_done

    with app.app_context():
        rec = Settings(key="pdf_onboarding_done")
        rec.set_value(True)
        db.session.add(rec)
        db.session.commit()
        mark_access_onboarding_done()

    r = auth_client.get("/api/admin/onboarding")
    assert r.status_code == 200
    ob = r.get_json()["onboarding"]
    assert ob["completed"] is True
    assert ob["should_open"] is False


def test_onboarding_advance_resume_and_reopen_preserves_data(auth_client, app):
    # Avança até o passo 5 e define fonte manual
    for step in range(1, 5):
        resp = auth_client.post(
            "/api/admin/onboarding",
            json={"action": "advance", "step": step},
        )
        assert resp.status_code == 200
        assert resp.get_json()["onboarding"]["current_step"] == step + 1

    r_src = auth_client.post(
        "/api/admin/onboarding",
        json={"action": "set_source", "company_source": "manual"},
    )
    assert r_src.status_code == 200
    assert r_src.get_json()["onboarding"]["company_source"] == "manual"

    # Simula reabertura do painel: deve retomar exatamente no passo 5
    r_resume = auth_client.get("/api/admin/first_run_status")
    ob = r_resume.get_json()["onboarding"]
    assert ob["current_step"] == 5
    assert ob["should_open"] is True
    assert ob["company_source"] == "manual"

    # Cadastra uma empresa sintética antes de concluir
    with app.app_context():
        db.session.add(
            Company(
                nome="Empresa Teste S14",
                cnpj="24.684.423/0001-00",
                cnpj_norm="24684423000100",
                status=True,
                origem="Manual",
            )
        )
        db.session.commit()

    # Conclui no passo 9
    r_done = auth_client.post("/api/admin/onboarding", json={"action": "complete"})
    assert r_done.status_code == 200
    assert r_done.get_json()["onboarding"]["completed"] is True
    assert r_done.get_json()["onboarding"]["should_open"] is False

    # Reabre ("Refazer configuração inicial"): volta ao passo 1 sem apagar empresa
    r_reopen = auth_client.post(
        "/api/admin/onboarding",
        json={"action": "reopen", "step": 1},
    )
    assert r_reopen.status_code == 200
    ob2 = r_reopen.get_json()["onboarding"]
    assert ob2["completed"] is False
    assert ob2["current_step"] == 1
    assert ob2["should_open"] is True

    with app.app_context():
        assert Company.query.filter_by(cnpj_norm="24684423000100").count() == 1


def test_onboarding_skip_all_leaves_zero_pending_integrations(auth_client):
    for step in range(1, 9):
        r = auth_client.post(
            "/api/admin/onboarding",
            json={"action": "skip", "step": step},
        )
        assert r.status_code == 200
        ob = r.get_json()["onboarding"]
        if step == 4:
            # Passo 4: pular mantém a rotina padrão ativa e só avança.
            assert step not in ob["skipped_steps"]
        else:
            assert step in ob["skipped_steps"]
        assert ob["current_step"] == step + 1

    r_done = auth_client.post("/api/admin/onboarding", json={"action": "complete"})
    assert r_done.status_code == 200

    # Nenhuma integração pode ficar pendente quando tudo foi pulado
    r_status = auth_client.get("/api/system/integrations_status")
    assert r_status.status_code == 200
    payload = r_status.get_json()
    assert payload["pending_count"] == 0
    assert payload["all_configured"] is True
    for item in payload["integrations"]:
        if item["id"] == "main_dag":
            # Passo 4 pulado mantém a rotina padrão ativa (configurada, nunca pendente).
            assert item["status"] == "configured"
        else:
            assert item["status"] in ("disabled", "unavailable")


def test_onboarding_invalid_action_and_role_guard(client, auth_client):
    r_bad = auth_client.post("/api/admin/onboarding", json={"action": "invalida"})
    assert r_bad.status_code == 400

    with client.session_transaction() as sess:
        sess["user"] = {"username": "leitor", "role": "user"}

    r_forbidden = client.post("/api/admin/onboarding", json={"action": "complete"})
    assert r_forbidden.status_code == 403

    r_gc_forbidden = client.post("/api/gestaoclick/test", json={})
    assert r_gc_forbidden.status_code == 403


def test_gestaoclick_test_endpoint_offline(auth_client):
    # Sem credenciais
    r_empty = auth_client.post("/api/gestaoclick/test", json={})
    assert r_empty.status_code == 400

    # Mock de sucesso
    mock_ok = MagicMock(status_code=200, content=b'{"meta":{"total_registros":42}}')
    mock_ok.json.return_value = {"meta": {"total_registros": 42}}
    with patch("requests.get", return_value=mock_ok):
        r_ok = auth_client.post(
            "/api/gestaoclick/test",
            json={
                "gestaoclick_access_token": "tok-1",
                "gestaoclick_secret_token": "sec-1",
            },
        )
    assert r_ok.status_code == 200
    assert r_ok.get_json()["total"] == 42

    # Mock de 401
    mock_401 = MagicMock(status_code=401, content=b"")
    with patch("requests.get", return_value=mock_401):
        r_401 = auth_client.post(
            "/api/gestaoclick/test",
            json={
                "gestaoclick_access_token": "bad",
                "gestaoclick_secret_token": "bad",
            },
        )
    assert r_401.status_code == 400


def test_onboarding_endpoints_do_not_leak_secrets(auth_client, app):
    with app.app_context():
        rec = Settings(key="global_settings")
        rec.set_value(
            {
                "smtp": {"enabled": True, "server": "smtp.ex.com", "user": "u@ex.com", "password": "SUPER_SECRET_SMTP"},
                "api_keys": {"gestaoclick_access_token": "SECRET_GC_ACCESS", "gestaoclick_secret_token": "SECRET_GC_KEY"},
                "inlabs": {"user": "inlabs@ex.com", "password": "SUPER_SECRET_INLABS"},
            }
        )
        db.session.add(rec)
        db.session.commit()

    r1 = auth_client.get("/api/admin/first_run_status")
    r2 = auth_client.get("/api/admin/onboarding")
    for body in (r1.get_data(as_text=True), r2.get_data(as_text=True)):
        assert "SUPER_SECRET_SMTP" not in body
        assert "SECRET_GC_ACCESS" not in body
        assert "SECRET_GC_KEY" not in body
        assert "SUPER_SECRET_INLABS" not in body


def _main_settings(app):
    with app.app_context():
        rec = Settings.query.filter_by(key="main_dag_settings").first()
        return dict(rec.get_value()) if rec else {}


def _global_settings(app):
    with app.app_context():
        rec = Settings.query.filter_by(key="global_settings").first()
        return dict(rec.get_value()) if rec else {}


def test_configure_main_dag_step4_saves_without_emails_on_clean_install(auth_client, app):
    """Achado 1: o passo 4 manda só os campos da rotina, sem e-mails, com SMTP nunca configurado."""
    r = auth_client.post(
        "/api/system/configure_main_dag",
        json={"schedule": "0 12 * * MON-FRI", "sections": ["SECAO_1", "SECAO_2", "SECAO_3", "EDICAO_EXTRA"], "organs": [], "is_exact_search": False, "active": True},
    )
    assert r.status_code == 200, r.get_json()
    main = _main_settings(app)
    assert main["schedule"] == "0 12 * * MON-FRI"
    assert main["active"] is True


def test_configure_main_dag_requires_emails_only_when_sent_with_smtp_on(auth_client):
    # Modal de Configurações: manda tudo junto, com SMTP ligado e sem e-mails -> 400
    r = auth_client.post(
        "/api/system/configure_main_dag",
        json={"emails": [], "subject": "x", "schedule": "0 8 * * MON-FRI", "active": True, "smtp": {"enabled": True}},
    )
    assert r.status_code == 400
    # Com SMTP desligado, e-mails vazios são aceitos
    r2 = auth_client.post(
        "/api/system/configure_main_dag",
        json={"emails": [], "subject": "x", "schedule": "0 8 * * MON-FRI", "active": True, "smtp": {"enabled": False}},
    )
    assert r2.status_code == 200


def test_configure_main_dag_partial_update_keeps_schedule_and_active(auth_client, app):
    """Achado 3: o passo 7 (só emails/subject) não desfaz horário nem 'active' do passo 4."""
    r1 = auth_client.post(
        "/api/system/configure_main_dag",
        json={"schedule": "0 12 * * MON-FRI", "active": False},
    )
    assert r1.status_code == 200
    r2 = auth_client.post(
        "/api/system/configure_main_dag",
        json={"emails": "teste@exemplo.com", "subject": "Assunto S14"},
    )
    assert r2.status_code == 200, r2.get_json()
    main = _main_settings(app)
    assert main["schedule"] == "0 12 * * MON-FRI"
    assert main["active"] is False
    assert main["subject"] == "Assunto S14"
    assert main["emails"] == ["teste@exemplo.com"]


def test_onboarding_skip_step4_keeps_default_routine_active(auth_client, app):
    """Achado 4: pular a rotina inicial mantém a rotina semeada ativa e só avança."""
    r = auth_client.post("/api/admin/onboarding", json={"action": "skip", "step": 4})
    assert r.status_code == 200
    assert r.get_json()["onboarding"]["current_step"] == 5
    assert _main_settings(app).get("active", True) is not False
    act = auth_client.get("/api/activity").get_json()
    assert act.get("next_search")


def test_onboarding_reopen_skip_keeps_configured_integrations(auth_client, app):
    """Achado 5: na reabertura, 'pular' não desativa integração já ligada."""
    assert auth_client.post("/api/save_settings", json={"smtp": {"enabled": True, "server": "smtp.exemplo.com", "port": "587", "user": "u@exemplo.com", "password": "x"}}).status_code == 200
    assert auth_client.post("/api/save_settings", json={"api_keys": {"gestaoclick_auto_sync": True}}).status_code == 200
    auth_client.post("/api/admin/onboarding", json={"action": "complete"})
    ob = auth_client.post("/api/admin/onboarding", json={"action": "reopen", "step": 6}).get_json()["onboarding"]
    assert ob["reopened"] is True

    r6 = auth_client.post("/api/admin/onboarding", json={"action": "skip", "step": 6}).get_json()["onboarding"]
    assert r6["current_step"] == 7 and r6["deactivated"] is False and 6 not in r6["skipped_steps"]
    r7 = auth_client.post("/api/admin/onboarding", json={"action": "skip", "step": 7}).get_json()["onboarding"]
    assert r7["deactivated"] is False
    gs = _global_settings(app)
    assert gs["smtp"]["enabled"] is True
    assert gs["api_keys"]["gestaoclick_auto_sync"] is True

    # Integração não configurada continua sendo desativada ao pular (não fica pendente)
    r5 = auth_client.post("/api/admin/onboarding", json={"action": "skip", "step": 8}).get_json()["onboarding"]
    assert r5["deactivated"] is True
    # Concluir encerra a reabertura
    done = auth_client.post("/api/admin/onboarding", json={"action": "complete"}).get_json()["onboarding"]
    assert done["reopened"] is False


def test_onboarding_html_switches_are_labels():
    """Achado 2: nenhum interruptor do assistente pode ser <span class="dash-switch"> sem label."""
    import re
    from pathlib import Path

    html = (Path(__file__).resolve().parents[1] / "templates" / "index.html").read_text(encoding="utf-8")
    start = html.index("<!-- Passo 4")
    end = html.index("<!-- Passo 8")
    wizard = html[start:end]
    assert 'dash-switch' in wizard
    assert not re.search(r'<span[^>]*class="dash-switch', wizard)
    for model in ("onboardingRoutine.is_exact_search", "onboardingSheets.auto_sync", "onboardingGc.auto_sync", "onboardingSmtp.enabled"):
        idx = wizard.index(f'x-model="{model}"')
        assert wizard.rindex("<label", 0, idx) > wizard.rindex("</label>", 0, idx)
