"""Testes offline do Sprint 2: runner, contrato XCom, LocalExecutor e rotas no modo local."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = REPO_ROOT / "rodou_dashboard"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "baseline"
DOU_API_FIXTURES_DIR = FIXTURES_DIR / "dou_api"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from app import create_app
from app.models import JobRun, Mention, db
from app.routes.dags import extract_mentions_from_results
from app.runtime.executor import LocalExecutor, get_executor, get_executor_mode, normalize_date_str
from app.runtime.runner import run_routine
from app.services.dag_config_service import get_last_search_time


def _make_dou_html(payload_json: dict, pagination_html: str = "") -> bytes:
    body = (
        "<html><body>"
        f"{pagination_html}"
        '<script id="_br_com_seatecnologia_in_buscadou_BuscaDouPortlet_params" type="application/json">'
        f"{json.dumps(payload_json, ensure_ascii=False)}"
        "</script>"
        "</body></html>"
    )
    return body.encode("utf-8")


def _load_dou_fixture(name: str) -> dict:
    with open(DOU_API_FIXTURES_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


def _memory_dou_yaml(terms, force_rematch=True):
    return {
        "dag": {
            "id": "test_local_dou",
            "description": "Rotina de teste offline",
            "schedule": None,
            "tags": ["temp", "api_dou"],
            "search": [
                {
                    "header": "MONITORAMENTO TESTE",
                    "is_exact_search": False,
                    "force_rematch": force_rematch,
                    "terms": terms,
                    "dou_sections": ["SECAO_1", "SECAO_2", "SECAO_3", "EDICAO_EXTRA"],
                    "field": "TUDO",
                    "date": "DIA",
                    "sources": ["DOU"],
                }
            ],
            "report": {
                "title": "Teste",
                "emails": [],
                "subject": "Teste DOU",
            },
        }
    }


def _make_app(tmp_path: Path):
    db_file = tmp_path / "test_local.db"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_file}",
            "WTF_CSRF_ENABLED": False,
        }
    )
    with app.app_context():
        db.create_all()
    return app


class TestRunnerOffline:
    def test_runner_cnpj_completo_raiz_isolada_trecho_truncado_sem_resultado(self, monkeypatch):
        from app.runtime.runner import _ensure_src_imports
        _ensure_src_imports()
        from hooks.dou_hook import DOUHook
        from searchers import DOUSearcher
        monkeypatch.setattr(DOUSearcher, "SCRAPPING_INTERVAL", 0)

        fixtures_by_root = {
            '"69.069.904"': _load_dou_fixture("cnpj_completo.json"),
            '"24.684.423"': _load_dou_fixture("raiz_isolada.json"),
            '"00.097.446"': _load_dou_fixture("trecho_truncado.json"),
            '"11.111.111"': _load_dou_fixture("sem_resultado.json"),
        }

        def fake_request_page(self, with_retry, payload, max_retries=3):
            q = payload.get("q")
            data = fixtures_by_root.get(q, {"jsonArray": []})
            return SimpleNamespace(
                content=_make_dou_html(data),
                url="https://www.in.gov.br/consulta/-/buscar/dou",
                status_code=200,
            )

        monkeypatch.setattr(DOUHook, "_request_page", fake_request_page)

        yaml_dict = _memory_dou_yaml(
            ["69069904000170", "24684423000136", "00097446000186", "11111111000191"]
        )
        outputs = run_routine(yaml_dict, execution_date="2026-11-23")
        assert len(outputs) == 1
        xcom = outputs[0]

        assert set(xcom.keys()) == {"result", "header", "department", "department_ignore", "pubtype", "source_used"}
        assert xcom["header"] == "MONITORAMENTO TESTE"

        group = xcom["result"]["single_group"]
        # Sem resultado não entra no dicionário
        assert "11111111000191" not in group

        # CNPJ completo
        item_completo = group["69069904000170"]["single_department"][0]
        assert item_completo["matched_cnpj"] == "69.069.904/0001-70"
        assert item_completo["root_only"] is False
        assert item_completo["is_branch"] is False

        # Raiz isolada (SURGITEC)
        item_raiz = group["24684423000136"]["single_department"][0]
        assert item_raiz["matched_cnpj"] == "24.684.423"
        assert item_raiz["root_only"] is True
        assert item_raiz["is_branch"] is False

        # Trecho truncado (Bio Engenharia)
        item_trunc = group["00097446000186"]["single_department"][0]
        assert item_trunc["root_only"] is True

    def test_runner_filial_e_paginacao(self, monkeypatch):
        from app.runtime.runner import _ensure_src_imports
        _ensure_src_imports()
        from hooks.dou_hook import DOUHook
        from searchers import DOUSearcher
        monkeypatch.setattr(DOUSearcher, "SCRAPPING_INTERVAL", 0)

        filial_fixture = _load_dou_fixture("filial.json")
        paginacao_fixture = _load_dou_fixture("paginacao.json")

        calls = []

        def fake_request_page(self, with_retry, payload, max_retries=3):
            calls.append(dict(payload))
            q = payload.get("q")
            if q == '"29.329.985"':
                return SimpleNamespace(
                    content=_make_dou_html(filial_fixture),
                    url="https://www.in.gov.br/consulta/-/buscar/dou",
                    status_code=200,
                )
            if q == "ANVISA":
                if payload.get("newPage") == 2:
                    return SimpleNamespace(
                        content=_make_dou_html(paginacao_fixture["page_2"]),
                        url="https://www.in.gov.br/consulta/-/buscar/dou",
                        status_code=200,
                    )
                return SimpleNamespace(
                    content=_make_dou_html(
                        paginacao_fixture["page_1"],
                        pagination_html='<button id="2btn">2</button>',
                    ),
                    url="https://www.in.gov.br/consulta/-/buscar/dou",
                    status_code=200,
                )
            return SimpleNamespace(
                content=_make_dou_html({"jsonArray": []}),
                url="https://www.in.gov.br/consulta/-/buscar/dou",
                status_code=200,
            )

        monkeypatch.setattr(DOUHook, "_request_page", fake_request_page)

        yaml_dict = _memory_dou_yaml(["29329985000186", "ANVISA"], force_rematch=False)
        outputs = run_routine(yaml_dict, execution_date="2026-11-04")
        group = outputs[0]["result"]["single_group"]
        assert len(group["29329985000186"]["single_department"]) == 1
        assert any(c.get("newPage") == 2 for c in calls)
        assert len(group["ANVISA"]["single_department"]) == (
            len(paginacao_fixture["page_1"]["jsonArray"])
            + len(paginacao_fixture["page_2"]["jsonArray"])
        )

    def test_runner_sem_resultado_bate_contrato_fixture_2026_11_19(self, monkeypatch):
        from app.runtime.runner import _ensure_src_imports
        _ensure_src_imports()
        from hooks.dou_hook import DOUHook
        from searchers import DOUSearcher
        monkeypatch.setattr(DOUSearcher, "SCRAPPING_INTERVAL", 0)

        empty_fixture = _load_dou_fixture("sem_resultado.json")
        with open(FIXTURES_DIR / "run_result_2026-11-19.json", "r", encoding="utf-8") as f:
            expected_19 = json.load(f)

        monkeypatch.setattr(
            DOUHook,
            "_request_page",
            lambda self, with_retry, payload, max_retries=3: SimpleNamespace(
                content=_make_dou_html(empty_fixture),
                url="https://www.in.gov.br/consulta/-/buscar/dou",
                status_code=200,
            ),
        )

        outputs = run_routine(_memory_dou_yaml(["00097446000186"]), execution_date="2026-11-19")
        assert outputs[0]["result"] == expected_19
        assert extract_mentions_from_results([outputs[0]["result"]], cnpj_map={}) == []
        assert extract_mentions_from_results([expected_19], cnpj_map={}) == []

    def test_contrato_chaves_run_result_2026_11_23(self):
        with open(FIXTURES_DIR / "run_result_2026-11-23.json", "r", encoding="utf-8") as f:
            fixture_23 = json.load(f)

        mentions = extract_mentions_from_results([fixture_23], cnpj_map={})
        assert len(mentions) == 4
        assert {m["cnpj_norm"] for m in mentions} == {
            "05785287000126",
            "07021336000180",
            "09217325000103",
            "24684423000136",
        }


class TestLocalExecutor:
    def test_ciclo_completo_job_runs_e_last_search_time(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REGISTRALE_EXECUTOR", "local")
        app = _make_app(tmp_path)

        with open(FIXTURES_DIR / "run_result_2026-11-23.json", "r", encoding="utf-8") as f:
            fixture_23 = json.load(f)

        class FakeDOUSearcher:
            def exec_search(self, **kwargs):
                return fixture_23

        executor = LocalExecutor(app=app, max_workers=2, searchers={"DOU": FakeDOUSearcher()})
        yaml_dict = _memory_dou_yaml(["24684423000136"])

        with app.app_context():
            run_id = executor.trigger(yaml_dict, date="23/11/2026")
            finished, states = executor.wait([run_id], timeout=10)
            assert finished is True
            assert states[run_id] == "success"
            assert executor.status(run_id) == "success"

            res = executor.result(run_id)
            assert len(res) == 1
            assert res[0]["result"] == fixture_23

            runs = executor.last_runs("test_local_dou")
            assert len(runs) == 1
            assert runs[0]["run_id"] == run_id
            assert runs[0]["state"] == "success"

            job = db.session.get(JobRun, run_id)
            assert job is not None
            assert job.data == "2026-11-23"

            assert get_last_search_time() != "N/A"
        executor.shutdown(wait=True)

    def test_concorrencia_max_2_e_deduplicacao_por_dia(self, tmp_path):
        app = _make_app(tmp_path)
        active = 0
        max_seen = 0
        lock = threading.Lock()

        class SlowSearcher:
            def exec_search(self, **kwargs):
                nonlocal active, max_seen
                with lock:
                    active += 1
                    max_seen = max(max_seen, active)
                time.sleep(0.15)
                with lock:
                    active -= 1
                return {"single_group": {}}

        executor = LocalExecutor(app=app, max_workers=2, searchers={"DOU": SlowSearcher()})
        with app.app_context():
            y1 = _memory_dou_yaml(["00097446000186"])
            y1["dag"]["id"] = "rotina_a"
            y2 = _memory_dou_yaml(["00097446000186"])
            y2["dag"]["id"] = "rotina_b"
            y3 = _memory_dou_yaml(["00097446000186"])
            y3["dag"]["id"] = "rotina_c"

            r1 = executor.trigger(y1, date="2026-11-23")
            r1_dup = executor.trigger(y1, date="2026-11-23")
            assert r1_dup == r1  # 1 busca por dia por rotina em voo

            r2 = executor.trigger(y2, date="2026-11-23")
            r3 = executor.trigger(y3, date="2026-11-23")

            finished, states = executor.wait([r1, r2, r3], timeout=10)
            assert finished is True
            assert all(st == "success" for st in states.values())
            assert max_seen <= 2
        executor.shutdown(wait=True)

    def test_timeout_e_erro(self, tmp_path):
        app = _make_app(tmp_path)
        gate = threading.Event()

        class FailingOrSlowSearcher:
            def exec_search(self, **kwargs):
                if kwargs.get("term_list") == ["SLOW"]:
                    gate.wait(timeout=2)
                    return {"single_group": {}}
                raise RuntimeError("falha simulada DOU")

        executor = LocalExecutor(app=app, max_workers=2, searchers={"DOU": FailingOrSlowSearcher()})
        with app.app_context():
            r_slow = executor.trigger(_memory_dou_yaml(["SLOW"]), date="2026-11-23")
            finished, states = executor.wait([r_slow], timeout=0.05)
            assert finished is False
            assert states[r_slow] in ("queued", "running")
            gate.set()
            finished2, states2 = executor.wait([r_slow], timeout=5)
            assert finished2 is True
            assert states2[r_slow] == "success"

            y_err = _memory_dou_yaml(["ERR"])
            y_err["dag"]["id"] = "rotina_erro"
            r_err = executor.trigger(y_err, date="2026-11-23")
            finished_err, states_err = executor.wait([r_err], timeout=5)
            assert finished_err is True
            assert states_err[r_err] == "failed"
            job = db.session.get(JobRun, r_err)
            assert "falha simulada DOU" in (job.erro or "")
        executor.shutdown(wait=True)


class TestDashboardLocalMode:
    def test_normalize_date_str(self):
        assert normalize_date_str("23/11/2026") == "2026-11-23"
        assert normalize_date_str("23/11/26") == "2026-11-23"
        assert normalize_date_str("2026-11-23T12:00:00") == "2026-11-23"

    def test_rotas_painel_modo_local_sem_arquivos_temporarios(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REGISTRALE_EXECUTOR", "local")
        assert get_executor_mode() == "local"

        app = _make_app(tmp_path)
        executor = get_executor(app)
        assert isinstance(executor, LocalExecutor)

        from app.runtime.runner import _ensure_src_imports
        _ensure_src_imports()
        from hooks.dou_hook import DOUHook
        from searchers import DOUSearcher
        from app.services import inlabs_service

        monkeypatch.setattr(DOUSearcher, "SCRAPPING_INTERVAL", 0)
        monkeypatch.setattr(inlabs_service, "get_downloaded_dates", lambda *a, **kw: [])
        monkeypatch.setattr(inlabs_service, "enforce_inlabs_retention_limit", lambda *a, **kw: None)

        raiz_fixture = _load_dou_fixture("raiz_isolada.json")
        monkeypatch.setattr(
            DOUHook,
            "_request_page",
            lambda self, with_retry, payload, max_retries=3: SimpleNamespace(
                content=_make_dou_html(
                    raiz_fixture if payload.get("q") == '"24.684.423"' else {"jsonArray": []}
                ),
                url="https://www.in.gov.br/consulta/-/buscar/dou",
                status_code=200,
            ),
        )

        # Não deixar e-mail real tentar conectar em SMTP
        from app.services import email_service
        sent_emails = []
        monkeypatch.setattr(
            email_service.EmailSender,
            "send_custom_email",
            lambda self, to_emails, subject, html_content: sent_emails.append((to_emails, subject)),
        )

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user"] = {"username": "admin", "role": "master"}
            sess["expires_at"] = 9999999999

        dag_confs = REPO_ROOT / "dag_confs"
        before_temps = {p.name for p in dag_confs.glob("temp_*.yaml")}

        # Dispara busca mensal apenas via API DOU para 2026-11 (mockado)
        resp = client.post(
            "/api/routines/trigger_monthly",
            json={"month": 11, "year": 2026, "routines": ["Pesquisa_cnpj.yaml"], "mode": "api_dou_only"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "success"

        # Aguarda a thread de background concluir completamente (SyncHistory final gravado)
        from app.models import SyncHistory
        deadline = time.monotonic() + 15
        with app.app_context():
            while time.monotonic() < deadline:
                done = SyncHistory.query.filter(
                    SyncHistory.evento == "Busca Mensal Concluída"
                ).count()
                if done > 0:
                    break
                time.sleep(0.1)
            mentions = Mention.query.all()
            assert len(mentions) >= 1
            assert any(m.cnpj_norm == "24684423000136" for m in mentions)

        after_temps = {p.name for p in dag_confs.glob("temp_*.yaml")}
        assert after_temps == before_temps  # Nenhum YAML temporário gravado em dag_confs/

        # Garante encerramento limpo do pool global para não vazar threads entre testes
        from app.runtime import executor as executor_mod
        executor.shutdown(wait=True)
        executor_mod._LOCAL_EXECUTOR_INSTANCE = None

    def test_trigger_individual_modo_local_sem_airflow(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REGISTRALE_EXECUTOR", "local")
        app = _make_app(tmp_path)
        executor = get_executor(app)

        from app.runtime.runner import _ensure_src_imports
        _ensure_src_imports()
        from hooks.dou_hook import DOUHook
        from searchers import DOUSearcher
        from app.services import inlabs_service

        monkeypatch.setattr(DOUSearcher, "SCRAPPING_INTERVAL", 0)
        monkeypatch.setattr(inlabs_service, "is_date_loaded", lambda d: (False, 0))
        raiz_fixture = _load_dou_fixture("raiz_isolada.json")
        monkeypatch.setattr(
            DOUHook,
            "_request_page",
            lambda self, with_retry, payload, max_retries=3: SimpleNamespace(
                content=_make_dou_html(
                    raiz_fixture if payload.get("q") == '"24.684.423"' else {"jsonArray": []}
                ),
                url="https://www.in.gov.br/consulta/-/buscar/dou",
                status_code=200,
            ),
        )

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user"] = {"username": "admin", "role": "master"}
            sess["expires_at"] = 9999999999

        dag_confs = REPO_ROOT / "dag_confs"
        before_temps = {p.name for p in dag_confs.glob("temp_*.yaml")}

        # Dispara data única dentro da janela de 120 dias sem INLABS carregado
        resp = client.post(
            "/api/routines/trigger/Pesquisa_cnpj.yaml",
            json={"logical_date": "23/11/2026"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "success"

        from app.models import SyncHistory
        deadline = time.monotonic() + 15
        with app.app_context():
            while time.monotonic() < deadline:
                if SyncHistory.query.filter(SyncHistory.evento == "Busca Concluída").count() > 0:
                    break
                time.sleep(0.1)
            mentions = Mention.query.all()
            assert any(m.cnpj_norm == "24684423000136" for m in mentions)

        assert {p.name for p in dag_confs.glob("temp_*.yaml")} == before_temps

        from app.runtime import executor as executor_mod
        executor.shutdown(wait=True)
        executor_mod._LOCAL_EXECUTOR_INSTANCE = None
