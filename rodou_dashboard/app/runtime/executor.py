"""Camada de abstração de execução de rotinas (`Executor`).

Define a interface `Executor` e suas duas implementações:
- `AirflowExecutor`: encapsula as chamadas HTTP/CLI ao Airflow 3 (modo Docker).
- `LocalExecutor`: executa `runtime.runner.run_routine` em `ThreadPoolExecutor`
  e persiste estado e resultados na tabela SQLite `job_runs`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import ast
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait as futures_wait
from datetime import datetime, timedelta, timezone
import glob
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import urllib.parse
import uuid
import yaml

logger = logging.getLogger(__name__)

_BRASILIA_TZ = timezone(timedelta(hours=-3))


def normalize_date_str(value: Any) -> Optional[str]:
    """Converte datas para ISO (AAAA-MM-DD).

    Aceita DD/MM/AAAA, D/M/AAAA, DD/MM/AA, DD-MM-AAAA, AAAA-MM-DD, AAAA/MM/DD
    e ISO com horário. Retorna None se vazio e lança ValueError se inválida.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    raw = raw.split("T")[0].split(" ")[0]
    parts = [p for p in re.split(r"[/\-.]", raw) if p]
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"Data inválida: {value}")
    if len(parts[0]) == 4:
        y, m, d = parts
    else:
        d, m, y = parts
        if len(y) == 2:
            y = "20" + y
    if len(y) != 4:
        raise ValueError(f"Data inválida: {value}")
    return datetime(int(y), int(m), int(d)).strftime("%Y-%m-%d")


class Executor(ABC):
    """Interface comum para execução de rotinas de busca."""

    @abstractmethod
    def trigger(
        self,
        routine: Union[str, Path, Dict[str, Any]],
        date: Optional[str] = None,
        **conf: Any,
    ) -> str:
        """Dispara uma execução da rotina e retorna seu `run_id`."""

    @abstractmethod
    def status(self, run_id: str, routine: Optional[str] = None) -> str:
        """Retorna o estado da execução: queued, running, success, failed ou unknown."""

    @abstractmethod
    def wait(
        self,
        run_ids: List[str],
        timeout: int = 1800,
        routine: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, str]]:
        """Aguarda `run_ids` atingirem estado terminal. Retorna (all_finished, states)."""

    @abstractmethod
    def result(self, run_id: str, routine: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retorna a lista de resultados no formato XCom de `exec_search_N`."""

    @abstractmethod
    def pause(self, routine: str) -> Tuple[bool, str]:
        """Pausa o agendamento da rotina."""

    @abstractmethod
    def unpause(self, routine: str) -> Tuple[bool, str]:
        """Ativa o agendamento da rotina."""

    @abstractmethod
    def last_runs(self, routine: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Retorna as execuções mais recentes da rotina."""

    def delete_routine(self, routine: str) -> None:
        """Remove a rotina do orquestrador externo, se aplicável."""

    def sync_connection(self, conn_id: str, payload: Dict[str, Any]) -> None:
        """Sincroniza uma conexão no orquestrador externo, se aplicável."""


class AirflowExecutor(Executor):
    """Implementação que delega para a API REST / CLI do Airflow."""

    def trigger(
        self,
        routine: Union[str, Path, Dict[str, Any]],
        date: Optional[str] = None,
        **conf: Any,
    ) -> str:
        from ..services.airflow_service import trigger_airflow_dag

        dag_id = routine if isinstance(routine, str) else str(routine)
        ok, msg, run_info = trigger_airflow_dag(dag_id, logical_date=date, **conf)
        if not ok:
            raise RuntimeError(msg)
        if isinstance(run_info, dict) and run_info.get("dag_run_id"):
            return str(run_info["dag_run_id"])
        return f"manual__{dag_id}"

    def status(self, run_id: str, routine: Optional[str] = None) -> str:
        import requests
        from ..services.airflow_service import get_airflow_auth, get_airflow_url

        if not routine or not run_id:
            return "unknown"
        try:
            did_q = urllib.parse.quote(str(routine), safe="")
            rid_q = urllib.parse.quote(str(run_id), safe="")
            url = f"{get_airflow_url()}/api/v2/dags/{did_q}/dagRuns/{rid_q}"
            res = requests.get(url, auth=get_airflow_auth(), timeout=8)
            if res.status_code == 200:
                return str(res.json().get("state") or "unknown")
        except Exception as exc:
            logger.warning("Erro ao consultar status Airflow (%s/%s): %s", routine, run_id, exc)
        return "unknown"

    def wait(
        self,
        run_ids: List[str],
        timeout: int = 1800,
        routine: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, str]]:
        from ..services.airflow_service import wait_for_specific_dag_runs

        return wait_for_specific_dag_runs(routine or "", run_ids, max_wait=timeout)

    def result(self, run_id: str, routine: Optional[str] = None) -> List[Dict[str, Any]]:
        import requests
        from ..services.airflow_service import get_airflow_auth, get_airflow_url
        from ..services.dag_config_service import LOGS_DIR

        results_raw_list: List[Dict[str, Any]] = []
        airflow_url = get_airflow_url()
        auth = get_airflow_auth()

        if routine and run_id:
            try:
                ti_url = f"{airflow_url}/api/v2/dags/{routine}/dagRuns/{run_id}/taskInstances"
                res_ti = requests.get(ti_url, auth=auth, timeout=10)
                if res_ti.status_code == 200:
                    task_instances = res_ti.json().get("task_instances", [])
                    search_tasks = [
                        ti["task_id"]
                        for ti in task_instances
                        if "exec_search" in ti.get("task_id", "") and ti.get("state") == "success"
                    ]
                    for tid in search_tasks:
                        xcom_url = (
                            f"{airflow_url}/api/v2/dags/{routine}/dagRuns/{run_id}"
                            f"/taskInstances/{tid}/xcomEntries/return_value"
                        )
                        res_xc = requests.get(xcom_url, auth=auth, timeout=10)
                        if res_xc.status_code == 200:
                            xc_val = res_xc.json().get("value")
                            if isinstance(xc_val, str):
                                try:
                                    xc_val = json.loads(xc_val)
                                except Exception:
                                    try:
                                        xc_val = ast.literal_eval(xc_val)
                                    except Exception:
                                        pass
                            if isinstance(xc_val, dict):
                                results_raw_list.append(xc_val)
            except Exception as exc:
                logger.warning("Erro ao ler XCom Airflow (%s/%s): %s", routine, run_id, exc)

        if not results_raw_list and routine and run_id:
            try:
                patterns = [
                    os.path.join(
                        LOGS_DIR,
                        f"dag_id={routine}",
                        f"run_id={run_id}",
                        "task_id=exec_searchs.exec_search_*",
                        "attempt=*.log",
                    ),
                    os.path.join(
                        LOGS_DIR,
                        f"dag_id={routine}",
                        f"run_id={run_id}",
                        "task_id=exec_search_*",
                        "attempt=*.log",
                    ),
                ]
                specific_logs = []
                for pat in patterns:
                    specific_logs = glob.glob(pat)
                    if specific_logs:
                        break
                for log_path in specific_logs:
                    try:
                        with open(log_path, "rb") as f:
                            content = f.read().decode("utf-8", errors="ignore")
                        if "Done. Returned value was:" in content:
                            part = content.split("Done. Returned value was:", 1)[1].strip()
                            dict_match = re.search(
                                r"^(\{.*?\})\s*(?=\n\[\d{4}-\d{2}-\d{2}|\Z)",
                                part,
                                re.DOTALL,
                            )
                            if dict_match:
                                parsed = ast.literal_eval(dict_match.group(1))
                                if isinstance(parsed, dict):
                                    results_raw_list.append(parsed)
                    except Exception:
                        continue
            except Exception:
                pass

        return results_raw_list

    def pause(self, routine: str) -> Tuple[bool, str]:
        from ..services.airflow_service import toggle_airflow_dag

        return toggle_airflow_dag(routine, is_paused=True)

    def unpause(self, routine: str) -> Tuple[bool, str]:
        from ..services.airflow_service import toggle_airflow_dag

        return toggle_airflow_dag(routine, is_paused=False)

    def last_runs(self, routine: str, limit: int = 30) -> List[Dict[str, Any]]:
        import requests
        from ..services.airflow_service import get_airflow_auth, get_airflow_url

        try:
            did_q = urllib.parse.quote(str(routine), safe="")
            url = f"{get_airflow_url()}/api/v2/dags/{did_q}/dagRuns?order_by=-run_after&limit={limit}"
            res = requests.get(url, auth=get_airflow_auth(), timeout=8)
            if res.status_code == 200:
                runs = res.json().get("dag_runs", [])
                return [
                    {
                        "run_id": r.get("dag_run_id"),
                        "state": r.get("state"),
                        "start_date": r.get("start_date"),
                        "end_date": r.get("end_date"),
                    }
                    for r in runs
                ]
        except Exception as exc:
            logger.warning("Erro ao listar dagRuns Airflow para %s: %s", routine, exc)
        return []

    def delete_routine(self, routine: str) -> None:
        import requests
        from ..services.airflow_service import get_airflow_auth, get_airflow_url

        try:
            did_q = urllib.parse.quote(str(routine), safe="")
            requests.delete(
                f"{get_airflow_url()}/api/v2/dags/{did_q}",
                auth=get_airflow_auth(),
                timeout=5,
            )
        except Exception as exc:
            logger.warning("Erro ao remover DAG %s do Airflow: %s", routine, exc)

    def sync_connection(self, conn_id: str, payload: Dict[str, Any]) -> None:
        import requests
        from ..services.airflow_service import get_airflow_auth, get_airflow_url

        airflow_url = get_airflow_url()
        auth = get_airflow_auth()
        try:
            res = requests.get(
                f"{airflow_url}/api/v2/connections/{conn_id}",
                auth=auth,
                timeout=5,
            )
            if res.status_code == 200:
                update_mask = ",".join(k for k in payload.keys() if k != "connection_id")
                requests.patch(
                    f"{airflow_url}/api/v2/connections/{conn_id}?update_mask={update_mask}",
                    json=payload,
                    auth=auth,
                    timeout=5,
                )
            else:
                requests.post(
                    f"{airflow_url}/api/v2/connections",
                    json=payload,
                    auth=auth,
                    timeout=5,
                )
        except Exception as exc:
            logger.error("Falha ao sincronizar conexão %s no Airflow: %s", conn_id, exc)


class LocalExecutor(Executor):
    """Executor local baseado em `ThreadPoolExecutor` e tabela `job_runs`."""

    def __init__(
        self,
        app: Any = None,
        max_workers: int = 2,
        searchers: Optional[Dict[str, Any]] = None,
    ):
        self._app = app
        self._max_workers = max_workers
        self._searchers = searchers
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="registrale-runner",
        )
        self._lock = threading.Lock()
        self._futures: Dict[str, Future] = {}
        self._inflight_by_key: Dict[Tuple[str, str], str] = {}

    def _resolve_app(self) -> Any:
        if self._app is not None:
            return self._app
        from flask import current_app

        return current_app._get_current_object()

    @staticmethod
    def _resolve_yaml_source(
        routine: Union[str, Path, Dict[str, Any]],
        conf: Dict[str, Any],
    ) -> Tuple[str, Union[str, Path, Dict[str, Any]]]:
        if isinstance(routine, dict):
            dag_id = str(routine.get("dag", {}).get("id") or conf.get("dag_id") or "temp_memory")
            return dag_id, routine

        if isinstance(conf.get("yaml_dict"), dict):
            yaml_dict = conf["yaml_dict"]
            dag_id = str(yaml_dict.get("dag", {}).get("id") or routine)
            return dag_id, yaml_dict

        routine_str = os.fspath(routine)
        if routine_str == "ro-dou_inlabs_load_pg":
            return "ro-dou_inlabs_load_pg", "__inlabs_load__"
        if os.path.isfile(routine_str):
            dag_id = Path(routine_str).stem
            try:
                with open(routine_str, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                dag_id = str(data.get("dag", {}).get("id") or dag_id)
            except Exception:
                pass
            return dag_id, routine_str

        from ..services.dag_config_service import get_dag_confs_path

        confs_dir = get_dag_confs_path()
        confs_resolved = Path(confs_dir).resolve()
        candidate = os.path.join(confs_dir, routine_str)
        if Path(candidate).resolve().is_relative_to(confs_resolved) and os.path.isfile(candidate):
            return LocalExecutor._resolve_yaml_source(candidate, conf)

        for fname in sorted(os.listdir(confs_dir)):
            if not fname.endswith((".yaml", ".yml")):
                continue
            fpath = os.path.join(confs_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                if data.get("dag", {}).get("id") == routine_str or Path(fname).stem == routine_str:
                    return routine_str, fpath
            except Exception:
                continue

        raise FileNotFoundError(f"Rotina '{routine_str}' não encontrada em {confs_dir}.")

    def trigger(
        self,
        routine: Union[str, Path, Dict[str, Any]],
        date: Optional[str] = None,
        **conf: Any,
    ) -> str:
        from ..models import JobRun, db

        app = self._resolve_app()
        norm_date = normalize_date_str(date) if date else None
        routine_id, yaml_source = self._resolve_yaml_source(routine, conf)
        dedup_key = (routine_id, norm_date or "current")

        with self._lock:
            existing_run_id = self._inflight_by_key.get(dedup_key)
            if existing_run_id:
                existing_future = self._futures.get(existing_run_id)
                if existing_future is not None and not existing_future.done():
                    return existing_run_id

            run_id = f"local__{routine_id}__{norm_date or 'current'}__{uuid.uuid4().hex[:8]}"
            now_iso = datetime.now(_BRASILIA_TZ).isoformat()

            with app.app_context():
                job = JobRun(
                    id=run_id,
                    rotina=routine_id,
                    data=norm_date,
                    status="queued",
                    inicio=now_iso,
                )
                db.session.add(job)
                db.session.commit()

            future = self._pool.submit(
                self._execute_job,
                app,
                run_id,
                yaml_source,
                norm_date,
                dedup_key,
            )
            self._futures[run_id] = future
            self._inflight_by_key[dedup_key] = run_id
            return run_id

    def _execute_job(
        self,
        app: Any,
        run_id: str,
        yaml_source: Union[str, Path, Dict[str, Any]],
        norm_date: Optional[str],
        dedup_key: Tuple[str, str],
    ) -> None:
        from ..models import JobRun, db
        from .logging_setup import run_log_context
        from .runner import run_routine

        with run_log_context(run_id):
            logger.info("Iniciando execução local %s (data=%s)", run_id, norm_date or "atual")
            with app.app_context():
                try:
                    job = db.session.get(JobRun, run_id)
                    if job is not None:
                        job.status = "running"
                        job.inicio = datetime.now(_BRASILIA_TZ).isoformat()
                        db.session.commit()

                    if yaml_source == "__inlabs_load__":
                        from .inlabs_loader import load_inlabs_date

                        target_dt = norm_date or datetime.now(_BRASILIA_TZ).strftime("%Y-%m-%d")
                        load_res = load_inlabs_date(target_dt)
                        results = [load_res]
                    else:
                        results = run_routine(
                            yaml_source,
                            execution_date=norm_date,
                            searchers=self._searchers,
                        )

                    job = db.session.get(JobRun, run_id)
                    if job is not None:
                        job.status = "success"
                        job.fim = datetime.now(_BRASILIA_TZ).isoformat()
                        job.set_resultado(results)
                        db.session.commit()
                    logger.info("Execução local %s concluída com sucesso (%d blocos)", run_id, len(results))
                except Exception as exc:
                    logger.exception("Erro ao executar job local %s: %s", run_id, exc)
                    try:
                        db.session.rollback()
                        job = db.session.get(JobRun, run_id)
                        if job is not None:
                            job.status = "failed"
                            job.fim = datetime.now(_BRASILIA_TZ).isoformat()
                            job.erro = str(exc)
                            db.session.commit()
                    except Exception:
                        db.session.rollback()
                finally:
                    with self._lock:
                        if self._inflight_by_key.get(dedup_key) == run_id:
                            self._inflight_by_key.pop(dedup_key, None)
                        self._futures.pop(run_id, None)
                    db.session.remove()

    def _query_with_context(self, fn):
        from flask import has_app_context

        if has_app_context():
            return fn()
        with self._resolve_app().app_context():
            return fn()

    def status(self, run_id: str, routine: Optional[str] = None) -> str:
        from ..models import JobRun, db

        def _read():
            job = db.session.get(JobRun, run_id)
            return job.status if job is not None else "unknown"

        return self._query_with_context(_read)

    def wait(
        self,
        run_ids: List[str],
        timeout: int = 1800,
        routine: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, str]]:
        if not run_ids:
            return True, {}

        deadline = time.monotonic() + max(0.0, float(timeout))
        pending_ids = list(dict.fromkeys(run_ids))

        with self._lock:
            known_futures = {
                rid: self._futures[rid]
                for rid in pending_ids
                if rid in self._futures
            }

        if known_futures:
            remaining = max(0.0, deadline - time.monotonic())
            futures_wait(list(known_futures.values()), timeout=remaining)

        states: Dict[str, str] = {}
        while True:
            all_terminal = True
            for rid in pending_ids:
                st = self.status(rid, routine=routine)
                states[rid] = st
                if st not in ("success", "failed", "unknown"):
                    all_terminal = False
            if all_terminal or time.monotonic() >= deadline:
                break
            time.sleep(0.2)

        finished = all(st in ("success", "failed") for st in states.values())
        return finished, states

    def result(self, run_id: str, routine: Optional[str] = None) -> List[Dict[str, Any]]:
        from ..models import JobRun, db

        def _read():
            job = db.session.get(JobRun, run_id)
            return job.get_resultado() if job is not None else []

        return self._query_with_context(_read)

    def pause(self, routine: str) -> Tuple[bool, str]:
        return True, "Status da rotina atualizado localmente."

    def unpause(self, routine: str) -> Tuple[bool, str]:
        return True, "Status da rotina atualizado localmente."

    def last_runs(self, routine: str, limit: int = 30) -> List[Dict[str, Any]]:
        from ..models import JobRun

        def _read():
            rows = (
                JobRun.query.filter_by(rotina=routine)
                .order_by(JobRun.inicio.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "run_id": r.id,
                    "state": r.status,
                    "start_date": r.inicio,
                    "end_date": r.fim,
                    "data": r.data,
                    "erro": r.erro,
                }
                for r in rows
            ]

        return self._query_with_context(_read)

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait)


_EXECUTOR_LOCK = threading.Lock()
_LOCAL_EXECUTOR_INSTANCE: Optional[LocalExecutor] = None


def get_executor_mode() -> str:
    """Retorna 'local' ou 'airflow' conforme REGISTRALE_EXECUTOR."""
    mode = os.getenv("REGISTRALE_EXECUTOR", "airflow").strip().lower()
    return "local" if mode == "local" else "airflow"


def get_executor(app: Any = None) -> Executor:
    """Retorna o Executor configurado por `REGISTRALE_EXECUTOR`."""
    global _LOCAL_EXECUTOR_INSTANCE
    if get_executor_mode() == "local":
        with _EXECUTOR_LOCK:
            if _LOCAL_EXECUTOR_INSTANCE is None:
                _LOCAL_EXECUTOR_INSTANCE = LocalExecutor(app=app)
            elif app is not None and _LOCAL_EXECUTOR_INSTANCE._app is not app:
                _LOCAL_EXECUTOR_INSTANCE._app = app
            return _LOCAL_EXECUTOR_INSTANCE
    return AirflowExecutor()
