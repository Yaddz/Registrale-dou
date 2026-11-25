"""Login opcional: abertura direta só neste computador e passo do primeiro acesso."""

from app.models import Settings, User, db as _db

REMOTE = {"REMOTE_ADDR": "192.168.0.20"}


def _seed_admin(app):
    with app.app_context():
        _db.create_all()
        if not User.query.filter_by(username="admin").first():
            admin = User(username="admin", role="master")
            admin.set_password("admin")
            _db.session.add(admin)
            _db.session.commit()


def _disable_login(auth_client):
    r = auth_client.post("/api/admin/access_settings", json={"login_required": False})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["login_required"] is False


def test_login_exigido_por_padrao(auth_client, client, app):
    r = auth_client.get("/api/admin/access_settings")
    data = r.get_json()
    assert data["login_required"] is True
    assert data["onboarding_done"] is False
    status = auth_client.get("/api/admin/first_run_status").get_json()
    assert status["needs_access_onboarding"] is True
    assert status["login_required"] is True


def test_sem_login_abre_direto_no_computador_local(auth_client, app):
    _disable_login(auth_client)
    fresh = app.test_client()
    r = fresh.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'href="/logout"' not in html
    assert "Tempo restante da sessão" not in html
    assert fresh.get("/login").status_code == 302
    api = fresh.get("/api/admin/access_settings")
    assert api.status_code == 200
    assert api.get_json()["login_required"] is False
    with app.app_context():
        assert Settings.query.filter_by(key="auth_onboarding_done").first().get_value() is True


def test_sem_login_nao_vale_para_outro_endereco(auth_client, app):
    _disable_login(auth_client)
    remote = app.test_client()
    r = remote.get("/", environ_base=REMOTE)
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert remote.get("/api/admin/access_settings", environ_base=REMOTE).status_code == 401


def test_sem_login_bloqueia_host_externo_dns_rebinding(auth_client, app):
    _disable_login(auth_client)
    r = app.test_client().get("/api/admin/access_settings", base_url="http://evil.example:5000")
    assert r.status_code == 401


def test_sem_login_recusa_alteracao_vinda_de_outro_site(auth_client, app):
    _disable_login(auth_client)
    c = app.test_client()
    r = c.post(
        "/api/admin/access_settings",
        json={"login_required": True},
        headers={"Origin": "https://site-malicioso.example"},
    )
    assert r.status_code == 403
    ok = c.post(
        "/api/admin/access_settings",
        json={"login_required": True},
        headers={"Origin": "http://localhost"},
    )
    assert ok.status_code == 200


def test_desligar_login_so_pelo_computador_local(client, app):
    _seed_admin(app)
    with client.session_transaction() as sess:
        sess["user"] = {"username": "admin", "role": "master"}
        sess["expires_at"] = 9999999999
    r = client.post("/api/admin/access_settings", json={"login_required": False}, environ_base=REMOTE)
    assert r.status_code == 400
    with app.app_context():
        assert Settings.query.filter_by(key="auth_settings").first() is None


def test_usuario_consulta_nao_altera_acesso(user_client):
    r = user_client.post("/api/admin/access_settings", json={"login_required": False})
    assert r.status_code == 403


def test_religar_login_derruba_sessao_aberta_sem_senha(auth_client, app):
    _disable_login(auth_client)
    c = app.test_client()
    assert c.get("/").status_code == 200  # sessão aberta sem senha
    with c.session_transaction() as sess:
        assert sess.get("auto_login") is True
    with app.app_context():
        rec = Settings.query.filter_by(key="auth_settings").first()
        rec.set_value({"require_login": True})
        _db.session.commit()
    r = c.get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_onboarding_marcado_ao_manter_login(auth_client):
    r = auth_client.post("/api/admin/access_settings", json={"login_required": True})
    assert r.status_code == 200
    status = auth_client.get("/api/admin/first_run_status").get_json()
    assert status["needs_access_onboarding"] is False
    assert status["login_required"] is True
