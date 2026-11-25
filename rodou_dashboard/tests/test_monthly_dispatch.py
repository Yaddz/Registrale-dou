"""A busca mensal dispara um run por dia útil mesmo numa thread sem app context.

Regressão do hotfix "buscas sem resultado": o executor sem `app` vinculado
resolvia o app por `flask.current_app`, que não existe na thread de fundo da
busca mensal; todos os disparos falhavam em silêncio e a busca terminava como
"Nenhuma menção encontrada".
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

import pytest
import yaml
from flask import Flask
from flask.testing import FlaskClient

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from rodou_dashboard.app import create_app
from rodou_dashboard.app.models import SyncHistory, User, db
from rodou_dashboard.app.routes import dags
from rodou_dashboard.app.runtime.executor import LocalExecutor
from rodou_dashboard.app.services import dag_config_service, holiday_service, inlabs_service

BUSINESS_DAYS = ["2026-11-03", "2026-11-04", "2026-11-05"]


class FakeExecutor(LocalExecutor):
    """Executor sem `app` vinculado: resolve o app como o LocalExecutor real."""

    def __init__(self, fail_with: Optional[Exception] = None) -> None:
        super().__init__(app=None, max_workers=1)
        self.fail_with = fail_with
        self.triggered: list[tuple[Any, Optional[str]]] = []

    def trigger(self, routine: Any, date: Optional[str] = None, **conf: Any) -> str:
        self._resolve_app()  # levanta RuntimeError fora de app context
        if self.fail_with is not None:
            raise self.fail_with
        self.triggered.append((routine, date))
        return f"local__fake__{date}__{len(self.triggered)}"

    def wait(self, run_ids: Any, timeout: Optional[float] = None) -> tuple[bool, dict[str, str]]:
        return True, {r: "success" for r in run_ids}

    def result(self, run_id: str, routine: Any = None) -> list[Any]:
        return []


class CapturedThread:
    """Substitui `threading.Thread`: guarda o alvo para rodar fora da requisição."""

    started: list["CapturedThread"] = []

    def __init__(self, target: Callable[..., Any], args: tuple = (), kwargs: Optional[dict] = None, daemon: bool = False) -> None:
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}

    def start(self) -> None:
        CapturedThread.started.append(self)

    def run(self) -> None:
        self.target(*self.args, **self.kwargs)


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Flask]:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("REGISTRALE_DB_PATH", str(data_dir / "database.db"))
    monkeypatch.setenv("FLASK_ENV", "testing")
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
        routine = {
            "dag": {
                "id": "pesquisa_cnpj_anvisa",
                "search": [{"header": "MONITORAMENTO", "terms": ["24.684.423"], "dou_sections": ["SECAO_1"]}],
                "report": {"emails": []},
            }
        }
        Path(dag_config_service.get_base_yaml_path()).write_text(yaml.safe_dump(routine, allow_unicode=True), encoding="utf-8")
    yield app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    test_client = app.test_client()
    with test_client.session_transaction() as sess:
        sess["user"] = {"username": "admin", "role": "master"}
        sess["expires_at"] = 9999999999
    return test_client


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch) -> None:
    CapturedThread.started = []
    monkeypatch.setattr("threading.Thread", CapturedThread)
    monkeypatch.setattr(holiday_service, "get_business_days_for_month", lambda year, month, cap_today=True: list(BUSINESS_DAYS))
    monkeypatch.setattr(inlabs_service, "enforce_inlabs_retention_limit", lambda max_days=120, protected_dates=None: None)
    monkeypatch.setattr(dags, "_summarize_coverage_from_runs", lambda run_ids: ("", []))
    monkeypatch.setattr(dags, "_extract_sources_used_from_runs", lambda run_ids: "")
    monkeypatch.setattr(dags, "fetch_mentions_from_dag_run", lambda dag_id, run_id, cnpj_map=None: [])


def _run_monthly(client: FlaskClient, mode: str) -> None:
    resp = client.post("/api/routines/trigger_monthly", json={"year": 2026, "month": 11, "mode": mode, "routines": ["Pesquisa_cnpj.yaml"]})
    assert resp.status_code == 200, resp.get_json()
    assert len(CapturedThread.started) == 1
    # Roda o corpo da thread FORA de qualquer requisição/app context, como em produção.
    CapturedThread.started[0].run()


def _events(app: Flask) -> list[tuple[str, str]]:
    with app.app_context():
        return [(h.evento, h.detalhes or "") for h in SyncHistory.query.order_by(SyncHistory.id).all()]


def test_monthly_api_dou_dispatches_one_run_per_business_day(app: Flask, client: FlaskClient, patched: None, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeExecutor()
    monkeypatch.setattr(dags, "get_executor", lambda app=None: fake)
    monkeypatch.setattr(inlabs_service, "get_downloaded_dates", lambda start=None, end=None: set())

    _run_monthly(client, "api_dou_only")

    assert [d for _, d in fake.triggered] == BUSINESS_DAYS
    assert all(isinstance(r, dict) and r["dag"]["id"].startswith("temp_monthly_dou_") for r, _ in fake.triggered)
    evts = [e for e, _ in _events(app)]
    assert "Erro (Busca Mensal)" not in evts
    assert any(e == "Busca Mensal Concluída" or e == "E-mail desativado" for e in evts)


def test_monthly_inlabs_phase_dispatches_one_run_per_business_day(app: Flask, client: FlaskClient, patched: None, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeExecutor()
    monkeypatch.setattr(dags, "get_executor", lambda app=None: fake)
    monkeypatch.setattr(inlabs_service, "get_downloaded_dates", lambda start=None, end=None: set(BUSINESS_DAYS))

    _run_monthly(client, "full")

    assert [d for _, d in fake.triggered] == BUSINESS_DAYS
    assert "Erro (Busca Mensal)" not in [e for e, _ in _events(app)]


def test_monthly_dispatch_failure_records_error_event(app: Flask, client: FlaskClient, patched: None, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeExecutor(fail_with=RuntimeError("falha simulada no disparo"))
    monkeypatch.setattr(dags, "get_executor", lambda app=None: fake)
    monkeypatch.setattr(inlabs_service, "get_downloaded_dates", lambda start=None, end=None: set())

    _run_monthly(client, "api_dou_only")

    events = _events(app)
    errors = [d for e, d in events if e == "Erro (Busca Mensal)"]
    assert errors and any("falha simulada no disparo" in d for d in errors)
    assert not any(e == "Busca Mensal Concluída" and "Nenhuma menção" in d for e, d in events)
