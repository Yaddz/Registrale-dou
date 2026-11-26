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

from datetime import datetime, timedelta
from rodou_dashboard.app import create_app
from rodou_dashboard.app.models import Company, Settings, SyncHistory, db
from rodou_dashboard.app.services import sync_cnpj, sync_state

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
    monkeypatch.setenv("REGISTRALE_DB_PATH", str(data_dir / "database.db"))
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("REGISTRALE_DISABLE_SCHEDULER", "1")
    for var in ("INLABS_DB_URL", "REGISTRALE_ROUTINES_DIR", "DAG_CONFS_DIR",
                "BASE_URL", "ACCESS_TOKEN", "SECRET_ACCESS_TOKEN", "YAML_PATH"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(sync_cnpj, "load_dotenv", None)
    app = create_app()
    app.config["TESTING"] = True
    sync_state.reset_sync_state()
    with app.app_context():
        yield app
    sync_state.reset_sync_state()


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


def _seed_gc_settings() -> None:
    Settings.query.filter_by(key="global_settings").delete()
    rec = Settings(key="global_settings")
    rec.set_value({"api_keys": {"gestaoclick_access_token": "tok", "gestaoclick_secret_token": "sec"}})
    db.session.add(rec)
    db.session.commit()


def test_rota_sync_duplicada_retorna_409_e_chama_uma_vez(app_ctx):
    _seed_gc_settings()
    client = app_ctx.test_client()
    with client.session_transaction() as sess:
        sess["user"] = {"username": "admin", "role": "master"}
        sess["expires_at"] = time.time() + 1800

    gate = threading.Event()
    entered = threading.Event()
    calls = 0

    def slow_sync():
        nonlocal calls
        calls += 1
        entered.set()
        gate.wait(timeout=5)
        return {"total_api": 1, "unicos": 1, "repetidos": 0, "novas": 1, "atualizadas": 0, "sem_mudanca": 0, "ignoradas": 0}

    with patch.object(sync_cnpj, "executar_sincronizacao", side_effect=slow_sync):
        resp1 = client.post("/api/sync")
        assert resp1.status_code == 200
        assert entered.wait(timeout=3)

        resp2 = client.post("/api/sync")
        assert resp2.status_code == 409
        assert "andamento" in resp2.get_json()["message"]

        gate.set()
        # Aguarda a thread liberar o estado
        deadline = time.time() + 3
        while sync_state.get_sync_state()["running"] and time.time() < deadline:
            time.sleep(0.01)

    assert calls == 1


def test_agendada_nao_roda_com_manual_em_andamento(app_ctx):
    from rodou_dashboard.app.runtime import scheduler as sched_mod

    assert sync_state.try_start_sync() is True
    try:
        with patch.object(sched_mod, "_get_app", return_value=app_ctx), \
                patch.object(sync_cnpj, "executar_sincronizacao") as mock_exec:
            sched_mod._run_scheduled_gestaoclick_sync()
        mock_exec.assert_not_called()
    finally:
        sync_state.finish_sync()


def test_planilha_manda_sobre_gestaoclick_em_qualquer_ordem(app_ctx):
    from rodou_dashboard.app.services import sheets_service

    # 1) GestãoClick cadastra empresa A; Manual já existe para empresa M
    _seed_manual()
    sync_cnpj.salvar_clientes_no_banco([
        {"nome": "Empresa A (ERP)", "cnpj": "11.111.111/0001-11", "status": False},
        {"nome": "Empresa M (ERP)", "cnpj": "33.333.333/0001-33", "status": True},
    ])
    assert Company.query.filter_by(cnpj_norm="11111111000111").first().origem == "GestãoClick"

    # 2) Planilha atualiza empresa A (muda nome, status=True e assume origem 'Google Sheets') e cria empresa B
    sheet_rows = [
        {"nome": "Empresa A (Planilha)", "cnpj": "11.111.111/0001-11", "cnpj_norm": "11111111000111"},
        {"nome": "Empresa B (Planilha)", "cnpj": "44.444.444/0001-44", "cnpj_norm": "44444444000144"},
    ]
    Settings.query.filter_by(key="global_settings").delete()
    rec = Settings(key="global_settings")
    rec.set_value({"google_sheets": {"spreadsheet_url": "https://docs.google.com/spreadsheets/d/abc", "credentials_json": "{}"}})
    db.session.add(rec)
    db.session.commit()

    with patch.object(sheets_service, "fetch_and_parse_sheet_api", return_value=sheet_rows):
        sheets_service.executar_sincronizacao_sheets(app=app_ctx)

    comp_a = Company.query.filter_by(cnpj_norm="11111111000111").first()
    comp_b = Company.query.filter_by(cnpj_norm="44444444000144").first()
    assert comp_a.nome == "Empresa A (Planilha)"
    assert comp_a.status is True
    assert comp_a.origem == "Google Sheets"
    assert comp_b.origem == "Google Sheets"

    # 3) GestãoClick roda depois com dados diferentes: NÃO altera A, B nem Manual
    stats = sync_cnpj.salvar_clientes_no_banco([
        {"nome": "Empresa A (Sobrescrita)", "cnpj": "11.111.111/0001-11", "status": False},
        {"nome": "Empresa B (Sobrescrita)", "cnpj": "44.444.444/0001-44", "status": False},
        {"nome": "Empresa M (Sobrescrita)", "cnpj": "33.333.333/0001-33", "status": False},
    ])
    assert stats["novas"] == 0
    assert stats["atualizadas"] == 0
    assert stats["ignoradas"] == 3
    assert Company.query.filter_by(cnpj_norm="11111111000111").first().nome == "Empresa A (Planilha)"
    assert Company.query.filter_by(cnpj_norm="44444444000144").first().nome == "Empresa B (Planilha)"
    assert Company.query.filter_by(cnpj_norm="33333333000133").first().nome == "Manual Protegida"


def test_deduplicacao_e_contagens_honestas(app_ctx):
    # Repetidos: 11... tem [ativo, inativo] -> ativo vence; 22... tem [inativo, ativo] -> ativo vence;
    # 55... tem [inativo, inativo] -> último vence.
    lote1 = [
        {"nome": "E1 Ativa", "cnpj": "11.111.111/0001-11", "status": True},
        {"nome": "E1 Inativa", "cnpj": "11.111.111/0001-11", "status": False},
        {"nome": "E2 Inativa", "cnpj": "22.222.222/0001-22", "status": False},
        {"nome": "E2 Ativa", "cnpj": "22.222.222/0001-22", "status": True},
        {"nome": "E5 Primeira", "cnpj": "55.555.555/0001-55", "status": False},
        {"nome": "E5 Ultima", "cnpj": "55.555.555/0001-55", "status": False},
    ]
    s1 = sync_cnpj.salvar_clientes_no_banco(lote1)
    assert s1 == {"total_api": 6, "unicos": 3, "repetidos": 3, "novas": 3, "atualizadas": 0, "sem_mudanca": 0, "ignoradas": 0}
    assert Company.query.filter_by(cnpj_norm="11111111000111").first().nome == "E1 Ativa"
    assert Company.query.filter_by(cnpj_norm="22222222000122").first().nome == "E2 Ativa"
    assert Company.query.filter_by(cnpj_norm="55555555000155").first().nome == "E5 Ultima"

    # Mesmos dados -> sem_mudanca == 3, atualizadas == 0
    s2 = sync_cnpj.salvar_clientes_no_banco(lote1)
    assert s2["atualizadas"] == 0
    assert s2["sem_mudanca"] == 3

    # Altera só 1 empresa
    lote2 = [
        {"nome": "E1 Ativa Alterada", "cnpj": "11.111.111/0001-11", "status": True},
        {"nome": "E2 Ativa", "cnpj": "22.222.222/0001-22", "status": True},
        {"nome": "E5 Ultima", "cnpj": "55.555.555/0001-55", "status": False},
    ]
    s3 = sync_cnpj.salvar_clientes_no_banco(lote2)
    assert s3["atualizadas"] == 1
    assert s3["sem_mudanca"] == 2
    resumo = sync_cnpj.format_sync_summary(s1)
    assert "3 clientes (3 repetidos na API): 3 novas, 0 atualizadas, 0 sem mudança, 0 preservadas." == resumo


def test_activity_e_health_alert_sync_travada_e_interrompida(app_ctx):
    from rodou_dashboard.app.runtime.server import reconcile_interrupted_syncs
    from rodou_dashboard.app.services.health_alerts import BRASILIA_TZ, compute_health_alerts

    t0 = datetime(2026, 11, 25, 14, 0, 0, tzinfo=BRASILIA_TZ)
    assert sync_state.try_start_sync(now=t0) is True

    client = app_ctx.test_client()
    with client.session_transaction() as sess:
        sess["user"] = {"username": "admin", "role": "master"}
        sess["expires_at"] = time.time() + 1800

    act = client.get("/api/activity").get_json()
    assert act["sync_active"] is True
    assert act["sync_started_at"] == t0.isoformat()
    assert act["sync_elapsed_s"] >= 0

    # Antes de 20 min -> sem alerta
    alerts_19 = compute_health_alerts({}, {"active": True, "emails": []}, [], now=t0 + timedelta(minutes=19))
    assert not any(a.id == "gestaoclick_sync_stalled" for a in alerts_19)

    # Após 21 min -> alerta com botão Resolver -> Configurações > Integrações
    alerts_21 = compute_health_alerts({}, {"active": True, "emails": []}, [], now=t0 + timedelta(minutes=21))
    stalled = [a for a in alerts_21 if a.id == "gestaoclick_sync_stalled"]
    assert len(stalled) == 1
    assert "21 min" in stalled[0].message
    assert stalled[0].settings_tab == "integrations"
    assert stalled[0].anchor == "gestaoclick-settings-card"
    sync_state.finish_sync()

    # Reconciliação na partida do servidor quando último evento ficou em 'Sincronização Iniciada'
    SyncHistory.log_event("Sincronização Iniciada", "Sincronização em segundo plano iniciada.")
    assert reconcile_interrupted_syncs(app_ctx) is True
    ultimo = SyncHistory.query.order_by(SyncHistory.id.desc()).first()
    assert ultimo.evento == "Erro Sync"
    assert "Sincronização interrompida (o programa foi fechado durante a sincronização)" in ultimo.detalhes
    # Segunda chamada não duplica
    assert reconcile_interrupted_syncs(app_ctx) is False
