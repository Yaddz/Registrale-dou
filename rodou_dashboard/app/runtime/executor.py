"""Camada de abstração de execução de rotinas (`Executor`).

Define a interface `Executor` e sua implementação local:
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


STATUS_PARTIAL = "partial"  # "Concluída com pendências": alguma seção não foi coberta
TERMINAL_STATES = ("success", "partial", "failed")


def _pending_sections(results: Any) -> List[str]:
    """Seções (de qualquer bloco) que nenhuma fonte cobriu."""
    pending: List[str] = []
    for block in results or []:
        if not isinstance(block, dict):
            continue
        for cov in block.get("coverage") or []:
            if isinstance(cov, dict) and cov.get("status") == "pendente":
                label = str(cov.get("label") or cov.get("section"))
                if label not in pending:
                    pending.append(label)
    return pending


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
        """Retorna o estado da execução: queued, running, success, partial (com pendências), failed ou unknown."""

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
        from .runner import NoMonitoredCompanies, run_routine

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

                    pending = _pending_sections(results)
                    job = db.session.get(JobRun, run_id)
                    if job is not None:
                        job.status = STATUS_PARTIAL if pending else "success"
                        job.fim = datetime.now(_BRASILIA_TZ).isoformat()
                        if pending:
                            job.erro = "Seções sem cobertura: " + ", ".join(pending)
                        job.set_resultado(results)
                        db.session.commit()
                    if pending:
                        logger.warning(
                            "Execução local %s concluída com pendências (%d blocos): %s",
                            run_id, len(results), ", ".join(pending),
                        )
                    else:
                        logger.info("Execução local %s concluída com sucesso (%d blocos)", run_id, len(results))
                except NoMonitoredCompanies as exc:
                    logger.warning("Execução local %s não executada: %s", run_id, exc)
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
                if st not in TERMINAL_STATES + ("unknown",):
                    all_terminal = False
            if all_terminal or time.monotonic() >= deadline:
                break
            time.sleep(0.2)

        finished = all(st in TERMINAL_STATES for st in states.values())
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


ORPHAN_RUN_MESSAGE = "Interrompida: o app foi fechado durante a execução"


def recover_orphan_runs(app: Any) -> int:
    """Marca como ``failed`` as execuções ``queued``/``running`` que sobraram de um app fechado.

    Sem isto o indicador de atividade ficaria em "Executando" para sempre. Execuções que
    este mesmo processo ainda está rodando (futuros do executor singleton) são preservadas.
    """
    from ..models import JobRun, SyncHistory, db

    live: set = set()
    inst = _LOCAL_EXECUTOR_INSTANCE
    if inst is not None:
        with inst._lock:
            live = {rid for rid, fut in inst._futures.items() if not fut.done()}
    count = 0
    with app.app_context():
        try:
            rows = JobRun.query.filter(JobRun.status.in_(["queued", "running"])).all()
            now_iso = datetime.now(_BRASILIA_TZ).isoformat()
            for job in rows:
                if job.id in live:
                    continue
                job.status = "failed"
                job.fim = now_iso
                job.erro = ORPHAN_RUN_MESSAGE
                count += 1
            if count:
                db.session.commit()
                SyncHistory.log_event(
                    "Execução Interrompida",
                    f"{count} execução(ões) ficaram sem terminar porque o app foi fechado e foram marcadas como interrompidas.",
                )
        except Exception as exc:
            db.session.rollback()
            logger.warning("Não foi possível recuperar execuções órfãs: %s", exc)
    if count:
        logger.warning("%d execução(ões) órfã(s) marcada(s) como interrompida(s).", count)
    return count


_EXECUTOR_LOCK = threading.Lock()
_LOCAL_EXECUTOR_INSTANCE: Optional[LocalExecutor] = None


def get_executor(app: Any = None) -> Executor:
    """Retorna a instância singleton de `LocalExecutor`."""
    global _LOCAL_EXECUTOR_INSTANCE
    with _EXECUTOR_LOCK:
        if _LOCAL_EXECUTOR_INSTANCE is None:
            _LOCAL_EXECUTOR_INSTANCE = LocalExecutor(app=app)
        elif app is not None and _LOCAL_EXECUTOR_INSTANCE._app is not app:
            _LOCAL_EXECUTOR_INSTANCE._app = app
        return _LOCAL_EXECUTOR_INSTANCE
