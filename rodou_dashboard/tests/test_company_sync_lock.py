"""Sincronizações de empresas (planilha e GestãoClick) não gravam a rotina ao mesmo tempo."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from rodou_dashboard.app import create_app
from rodou_dashboard.app.models import Company, db
from rodou_dashboard.app.services import dag_config_service, sheets_service


@pytest.fixture
def app_ctx(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("REGISTRALE_DISABLE_SCHEDULER", "1")
    monkeypatch.delenv("INLABS_DB_URL", raising=False)
    monkeypatch.delenv("REGISTRALE_ROUTINES_DIR", raising=False)
    monkeypatch.delenv("DAG_CONFS_DIR", raising=False)
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        yield app


def test_sheets_sync_waits_for_running_gestaoclick_sync(app_ctx):
    """Com a trava tomada por outra sincronização, a da planilha espera ela terminar."""
    order: list[str] = []
    holder_ready = threading.Event()

    def other_sync():
        with dag_config_service.COMPANY_SYNC_LOCK:
            holder_ready.set()
            time.sleep(0.3)
            order.append("gestaoclick_fim")

    def fake_inner(app=None, config_override=None):
        order.append("sheets")
        return {"status": "success"}

    t = threading.Thread(target=other_sync)
    t.start()
    assert holder_ready.wait(2)
    with patch.object(sheets_service, "_executar_sincronizacao_sheets", side_effect=fake_inner):
        res = sheets_service.executar_sincronizacao_sheets(app=app_ctx)
    t.join(2)
    assert res == {"status": "success"}
    assert order == ["gestaoclick_fim", "sheets"]


def test_concurrent_rebuilds_leave_valid_routine_and_no_temp_files(app_ctx):
    """Várias reconstruções simultâneas não deixam o YAML truncado nem arquivos .tmp."""
    for i in range(30):
        db.session.add(Company(nome=f"Empresa {i}", cnpj=f"00.000.{i:03d}/0001-00", cnpj_norm=f"00000{i:03d}000100", origem="Manual", status=True))
    db.session.commit()

    app = app_ctx
    errors: list[BaseException] = []

    def worker():
        try:
            with app.app_context():
                dag_config_service.rebuild_yaml_from_db()
        except BaseException as exc:  # pragma: no cover - falha do teste
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)

    assert not errors
    base = Path(dag_config_service.get_base_yaml_path())
    data = yaml.safe_load(base.read_text(encoding="utf-8"))
    terms = data["dag"]["search"][0]["terms"]
    expected = {dag_config_service.normalize_cnpj(c.cnpj) for c in Company.query.filter_by(status=True).all()}
    assert len(expected) >= 30
    assert sorted(terms) == sorted(expected)
    assert not list(base.parent.glob("*.tmp"))
