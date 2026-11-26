"""A sincronização do GestãoClick grava as empresas no SQLite (regressão: só gerava JSON/YAML)."""

from __future__ import annotations

import json
import os
import sys
import time
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from rodou_dashboard.app import create_app
from rodou_dashboard.app.models import Company, Settings, SyncHistory, db
from rodou_dashboard.app.services import sync_cnpj

CLIENTES = [
    {"nome": "Empresa Nova", "cnpj": "11.111.111/0001-11", "status": True},
    {"nome": "Empresa Inativa", "cnpj": "22.222.222/0001-22", "status": False},
    {"nome": "Nome da API", "cnpj": "33.333.333/0001-33", "status": True},
]


@pytest.fixture
def app_ctx(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("REGISTRALE_DISABLE_SCHEDULER", "1")
    for var in ("INLABS_DB_URL", "REGISTRALE_ROUTINES_DIR", "DAG_CONFS_DIR",
                "BASE_URL", "ACCESS_TOKEN", "SECRET_ACCESS_TOKEN", "YAML_PATH"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(sync_cnpj, "load_dotenv", None)
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        yield app


def _seed_manual() -> None:
    db.session.add(Company(nome="Manual Protegida", cnpj="33.333.333/0001-33",
                           cnpj_norm="33333333000133", origem="Manual", status=True))
    db.session.commit()


def test_sync_salva_empresas_no_banco_e_preserva_manual(app_ctx):
    _seed_manual()
    sync_cnpj.atualizar_configuracoes("Pesquisa_cnpj.yaml", CLIENTES)

    por_cnpj = {c.cnpj_norm: c for c in Company.query.all()}
    assert por_cnpj["11111111000111"].origem == "GestãoClick"
    assert por_cnpj["11111111000111"].status is True
    assert por_cnpj["22222222000122"].status is False
    assert por_cnpj["33333333000133"].nome == "Manual Protegida"
    assert por_cnpj["33333333000133"].origem == "Manual"
    backup = Path(sync_cnpj._metadata_file())
    assert backup.parent == Path(os.environ["REGISTRALE_DATA_DIR"])
    assert len(json.loads(backup.read_text(encoding="utf-8"))) == 3


def test_rota_sync_grava_no_banco_pela_thread(app_ctx):
    """Fluxo do botão "Sincronizar": a thread de background precisa gravar no SQLite."""
    Settings.query.filter_by(key="global_settings").delete()
    rec = Settings(key="global_settings")
    rec.set_value({"api_keys": {"gestaoclick_access_token": "tok", "gestaoclick_secret_token": "sec"}})
    db.session.add(rec)
    db.session.commit()

    started: list[threading.Thread] = []
    real_thread = threading.Thread

    def capture_thread(*args, **kwargs):
        t = real_thread(*args, **kwargs)
        started.append(t)
        return t

    client = app_ctx.test_client()
    with client.session_transaction() as sess:
        sess["user"] = {"username": "admin", "role": "master"}
        sess["expires_at"] = time.time() + 1800
    with patch.object(sync_cnpj, "get_monitored_data", return_value=CLIENTES), \
            patch("threading.Thread", side_effect=capture_thread):
        resp = client.post("/api/sync")
        for t in started:
            t.join(10)

    assert resp.status_code == 200, resp.get_data(as_text=True)
    db.session.expire_all()
    assert Company.query.filter_by(cnpj_norm="11111111000111").count() == 1
    eventos = [h.evento for h in SyncHistory.query.all()]
    assert "Sincronização OK" in eventos


def test_get_routines_com_varios_blocos_nao_reconstroi_yaml(app_ctx):
    """Com mais de 1.500 empresas (vários blocos), listar rotinas não pode reconstruir o YAML
    a cada chamada: dentro do reload do agendador isso travava a sincronização."""
    from rodou_dashboard.app.services import dag_config_service

    clientes = [{"nome": f"E{i}", "cnpj": sync_cnpj.formatar_cnpj(f"{i:08d}000100"), "status": True}
                for i in range(1, 1601)]
    sync_cnpj.salvar_clientes_no_banco(clientes)
    dag_config_service.rebuild_yaml_from_db()
    dag_config_service.clear_routines_cache()
    with patch.object(dag_config_service, "rebuild_yaml_from_db") as rebuild:
        dag_config_service.get_routines()
    rebuild.assert_not_called()


def test_reload_do_agendador_e_reentrante(app_ctx, tmp_path):
    from rodou_dashboard.app.runtime.scheduler import RegistraleScheduler

    s = RegistraleScheduler(app_ctx, db_path=tmp_path / "jobs.db")
    done = threading.Event()

    def nested():
        with s._lock:
            with s._lock:
                done.set()

    t = threading.Thread(target=nested, daemon=True)
    t.start()
    t.join(2)
    assert done.is_set()
