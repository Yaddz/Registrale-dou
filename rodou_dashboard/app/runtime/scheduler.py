"""Agendador local baseado em APScheduler com jobstore SQLite.

Substitui o scheduler do Airflow para as rotinas YAML e unifica a sincronização
recorrente do Google Sheets num único processo, eliminando duplicação por workers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import glob
import logging
import os
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
import yaml

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .paths import get_routines_dir, get_scheduler_db_path

logger = logging.getLogger(__name__)

_TIMEZONE = "America/Sao_Paulo"
_BRASILIA_TZ = timezone(timedelta(hours=-3))
_MISFIRE_GRACE_SECONDS = 86400  # 24h: executa ao ligar o PC se perdeu o horário do dia

_SCHEDULER_LOCK = threading.Lock()
_SCHEDULER_INSTANCE: Optional["RegistraleScheduler"] = None
_APP_REF: Any = None


def _get_app() -> Any:
    if _APP_REF is not None:
        return _APP_REF
    from flask import current_app

    return current_app._get_current_object()


RETRY_DELAY_MINUTES = 60
RETRY_MAX_ATTEMPTS = 4
RETRY_LAST_HOUR = 22  # não reagenda depois das 22h (horário de Brasília)


def _pending_in_runs(run_ids: List[str]) -> bool:
    """True se alguma execução terminou "com pendências" (seção sem cobertura)."""
    from ..models import JobRun

    return any(
        job.status == "partial"
        for job in JobRun.query.filter(JobRun.id.in_(list(run_ids))).all()
    )


RETRY_MISFIRE_GRACE_SECONDS = 600  # nova tentativa perdida (PC desligado) não vale no dia seguinte


def _routine_is_active(routine_file: str) -> bool:
    from ..services.dag_config_service import get_routines

    return any(
        r.get("file") == routine_file and bool(r.get("active", True))
        for r in get_routines()
    )


def _schedule_retry(routine_file: str, attempt: int) -> bool:
    """Agenda nova tentativa do dia para completar as seções pendentes."""
    now = datetime.now(_BRASILIA_TZ)
    if attempt > RETRY_MAX_ATTEMPTS:
        return False
    when = now + timedelta(minutes=RETRY_DELAY_MINUTES)
    if when.date() != now.date() or when.hour >= RETRY_LAST_HOUR:
        return False
    sched = get_scheduler()
    if sched is None or not sched.running:
        return False
    from apscheduler.triggers.date import DateTrigger

    sched.scheduler.add_job(
        "rodou_dashboard.app.runtime.scheduler:_run_scheduled_routine",
        trigger=DateTrigger(run_date=when),
        args=[routine_file, attempt, now.strftime("%Y-%m-%d")],
        id=f"retry::{routine_file}",
        name=f"retry:{routine_file}|{attempt}",
        replace_existing=True,
        misfire_grace_time=RETRY_MISFIRE_GRACE_SECONDS,
    )
    logger.info("Nova tentativa de %s (%d/%d) agendada para %s.", routine_file, attempt, RETRY_MAX_ATTEMPTS, when.strftime("%H:%M"))
    return True


def _run_scheduled_routine(routine_file: str, attempt: int = 0, run_date: Optional[str] = None) -> None:
    """Executa uma rotina agendada, persiste menções e envia e-mail.

    ``attempt`` > 0 marca nova tentativa do dia (seções pendentes): só e-mails de
    menções ainda não gravadas, para não repetir o aviso.
    """
    app = _get_app()
    from ..routes.dags import add_history_event, watch_dag_and_update_mentions
    from .executor import get_executor

    confs_dir = str(get_routines_dir())
    today_iso = datetime.now(_BRASILIA_TZ).strftime("%Y-%m-%d")
    if attempt > 0:
        # Nova tentativa só vale no mesmo dia e com a rotina ainda ativa.
        if run_date != today_iso:
            logger.info("Nova tentativa de %s ignorada: era do dia %s, hoje é %s.", routine_file, run_date, today_iso)
            return
        with app.app_context():
            if not _routine_is_active(routine_file):
                logger.info("Nova tentativa de %s ignorada: rotina pausada ou removida.", routine_file)
                return
    executor = get_executor(app)

    runs_to_watch: List[Dict[str, str]] = []
    routine_emails: List[str] = []
    routine_subject: Optional[str] = None
    target_terms: Optional[set] = None

    with app.app_context():
        try:
            yaml_files: List[str] = []
            if routine_file == "Pesquisa_cnpj.yaml":
                parts = sorted(
                    glob.glob(os.path.join(confs_dir, "Pesquisa_cnpj_sync.yaml"))
                    or glob.glob(os.path.join(confs_dir, "Pesquisa_cnpj_part_*.yaml"))
                )
                if parts:
                    yaml_files = parts
                else:
                    base = os.path.join(confs_dir, "Pesquisa_cnpj.yaml")
                    if os.path.isfile(base):
                        yaml_files = [base]
            else:
                fpath = os.path.join(confs_dir, routine_file)
                if os.path.isfile(fpath):
                    yaml_files = [fpath]

            if not yaml_files:
                logger.warning("Rotina agendada '%s' não encontrada em %s.", routine_file, confs_dir)
                return

            for yf in yaml_files:
                with open(yf, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                dag = data.get("dag", {})
                dag_id = str(dag.get("id") or Path(yf).stem)
                report = dag.get("report", {})
                if not routine_emails and report.get("emails"):
                    emails = report["emails"]
                    routine_emails = [emails] if isinstance(emails, str) else list(emails)
                if routine_subject is None and report.get("subject"):
                    routine_subject = report.get("subject")

                run_id = executor.trigger(yf, date=today_iso)
                runs_to_watch.append({"dag_id": dag_id, "dag_run_id": run_id})

            add_history_event(
                "Busca Agendada",
                f"Rotina {routine_file} disparada automaticamente pelo agendador local.",
            )
        except Exception as exc:
            logger.exception("Erro ao disparar rotina agendada %s: %s", routine_file, exc)
            add_history_event("Erro Agendamento", f"Falha ao disparar {routine_file}: {exc}")
            return

    if runs_to_watch:
        watch_dag_and_update_mentions(
            app.app_context(),
            runs_to_watch,
            routine_file,
            routine_emails=routine_emails,
            routine_subject=routine_subject,
            logical_date=today_iso,
            target_terms=target_terms,
            notify_only_new=attempt > 0,
        )
        try:
            with app.app_context():
                still_pending = _pending_in_runs([r["dag_run_id"] for r in runs_to_watch if r.get("dag_run_id")])
            if still_pending:
                from ..routes.dags import add_history_event as _hist
                scheduled = _schedule_retry(routine_file, attempt + 1)
                with app.app_context():
                    _hist(
                        "Busca Incompleta",
                        f"{routine_file}: seções sem cobertura em {today_iso}. "
                        + ("Nova tentativa automática em 1 hora." if scheduled else "Sem novas tentativas hoje; use 'Buscar' manualmente mais tarde."),
                    )
        except Exception as exc:
            logger.warning("Não foi possível agendar nova tentativa de %s: %s", routine_file, exc)

    if routine_file == "Pesquisa_cnpj.yaml":
        _run_scheduled_pdf_archive(today_iso)


def _run_scheduled_pdf_archive(date_iso: str) -> None:
    """Arquiva os PDFs integrais do DOU após a busca diária se habilitado."""
    app = _get_app()
    from ..routes.dags import add_history_event
    from .pdf_archiver import archive_date_pdfs, get_pdf_archive_config

    with app.app_context():
        try:
            cfg = get_pdf_archive_config()
            if not cfg.get("enabled", True):
                return
            res = archive_date_pdfs(date_iso)
            if res.get("status") in ("success", "error"):
                add_history_event("Arquivo PDF DOU", res.get("message", ""))
        except Exception as exc:
            logger.warning("Erro no arquivamento agendado de PDFs (%s): %s", date_iso, exc)
            add_history_event("Erro Arquivo PDF", str(exc))


def _run_scheduled_sheets_sync() -> None:
    """Executa a sincronização recorrente do Google Sheets."""
    app = _get_app()
    from ..services.sheets_service import _registrar_historico, executar_sincronizacao_sheets

    logger.info("Executando sincronização agendada do Google Sheets...")
    with app.app_context():
        try:
            executar_sincronizacao_sheets(app)
        except Exception as exc:
            logger.error("Erro na sincronização agendada do Google Sheets: %s", exc)
            _registrar_historico("Erro Sync Google Sheets", str(exc))


GESTAOCLICK_SYNC_MINUTES = 60


def _run_scheduled_gestaoclick_sync() -> None:
    """Sincroniza os CNPJs do GestãoClick (mesmo fluxo do botão "Sincronizar")."""
    app = _get_app()
    from ..models import SyncHistory
    from ..services.dag_config_service import COMPANY_SYNC_LOCK
    from ..services.sync_cnpj import executar_sincronizacao, format_sync_summary
    from ..services.sync_state import finish_sync, try_start_sync

    if not try_start_sync():
        logger.info("Sincronização agendada do GestãoClick ignorada: já existe uma sincronização em andamento.")
        return

    logger.info("Executando sincronização agendada do GestãoClick...")
    try:
        with app.app_context():
            try:
                with COMPANY_SYNC_LOCK:
                    stats = executar_sincronizacao()
                from ..routes.admin import clear_admin_caches

                clear_admin_caches()
                detalhes = (
                    format_sync_summary(stats)
                    if isinstance(stats, dict)
                    else "Sincronização automática do GestãoClick concluída."
                )
                SyncHistory.log_event("Sincronização OK", detalhes)
            except Exception as exc:
                logger.error("Erro na sincronização agendada do GestãoClick: %s", exc)
                SyncHistory.log_event("Erro Sync GestãoClick", str(exc))
    finally:
        finish_sync()


def _run_scheduled_inlabs_load() -> None:
    """Executa a carga diária do INLABS nos horários do upstream (06:59 e 23:59)."""
    app = _get_app()
    from ..routes.dags import add_history_event
    from .inlabs_loader import InlabsMaintenanceError, load_inlabs_date
    from .pg_portable import get_portable_postgres, start_portable_postgres

    today_iso = datetime.now(_BRASILIA_TZ).strftime("%Y-%m-%d")
    with app.app_context():
        if not os.getenv("INLABS_DB_URL"):
            pg = get_portable_postgres()
            if pg.get_connection_info() is None or not pg.is_running():
                port = start_portable_postgres()
                if port is None:
                    logger.info(
                        "Carga agendada do INLABS (%s) ignorada: PostgreSQL portátil indisponível.",
                        today_iso,
                    )
                    return

        try:
            res = load_inlabs_date(today_iso)
            add_history_event(
                "Carga INLABS Agendada",
                res.get("message") or f"Carga INLABS concluída para {today_iso}.",
            )
        except InlabsMaintenanceError as exc:
            logger.warning("INLABS em manutenção na carga agendada (%s): %s", today_iso, exc)
            add_history_event("INLABS Indisponível", str(exc))
        except Exception as exc:
            logger.error("Erro na carga agendada do INLABS (%s): %s", today_iso, exc)
            add_history_event("Erro Carga INLABS", f"Falha na carga de {today_iso}: {exc}")


class RegistraleScheduler:
    """Gerencia o `BackgroundScheduler` do modo local com persistência SQLite."""

    def __init__(
        self,
        app: Any,
        db_path: Optional[Path] = None,
        timezone_name: str = _TIMEZONE,
    ) -> None:
        global _APP_REF
        _APP_REF = app
        self._app = app
        self._timezone = timezone_name
        self._db_path = Path(db_path) if db_path is not None else get_scheduler_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # Reentrante: reload() -> get_routines() pode reconstruir o YAML, que chama reload() de novo.
        self._lock = threading.RLock()
        self._started = False

        jobstores = {"default": SQLAlchemyJobStore(url=f"sqlite:///{self._db_path.as_posix()}")}
        job_defaults = {
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": _MISFIRE_GRACE_SECONDS,
        }
        self._scheduler = BackgroundScheduler(
            jobstores=jobstores,
            job_defaults=job_defaults,
            timezone=self._timezone,
        )

    @property
    def scheduler(self) -> BackgroundScheduler:
        return self._scheduler

    @property
    def running(self) -> bool:
        return bool(self._started and self._scheduler.running)

    def start(self) -> None:
        """Inicia o agendador (disparando eventuais misfires pendentes no jobstore)."""
        with self._lock:
            if not self._started:
                self._scheduler.start()
                self._started = True
                logger.info("RegistraleScheduler iniciado (jobstore=%s).", self._db_path)

    def shutdown(self, wait: bool = False) -> None:
        """Encerra o agendador."""
        with self._lock:
            if self._started and self._scheduler.running:
                self._scheduler.shutdown(wait=wait)
            self._started = False
            logger.info("RegistraleScheduler encerrado.")

    def _sync_routine_jobs(self) -> int:
        from ..services.dag_config_service import get_routines

        routines = get_routines()
        active_job_ids = set()

        for routine in routines:
            routine_file = routine.get("file")
            cron_expr = str(routine.get("schedule") or "").strip()
            is_active = bool(routine.get("active", True))
            if not routine_file or not is_active or not cron_expr:
                continue

            job_id = f"routine::{routine_file}"
            expected_name = f"routine:{routine_file}|{cron_expr}"

            try:
                trigger = CronTrigger.from_crontab(cron_expr, timezone=self._timezone)
            except Exception as exc:
                logger.warning("Cron inválido para rotina '%s' (%r): %s", routine_file, cron_expr, exc)
                continue

            active_job_ids.add(job_id)
            existing = self._scheduler.get_job(job_id)
            if existing is not None and existing.name == expected_name:
                # Preserva next_run_time persistido no SQLite para detectar misfires ao ligar
                continue

            self._scheduler.add_job(
                "rodou_dashboard.app.runtime.scheduler:_run_scheduled_routine",
                trigger=trigger,
                args=[routine_file],
                id=job_id,
                name=expected_name,
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=_MISFIRE_GRACE_SECONDS,
            )
            logger.info("Job agendado: %s (%s)", job_id, cron_expr)

        for job in self._scheduler.get_jobs():
            if job.id.startswith("retry::") and f"routine::{job.id[len('retry::'):]}" not in active_job_ids:
                self._scheduler.remove_job(job.id)
                logger.info("Nova tentativa removida (rotina pausada/excluída): %s", job.id)
                continue
            if job.id.startswith("routine::") and job.id not in active_job_ids:
                self._scheduler.remove_job(job.id)
                logger.info("Job removido (rotina pausada/excluída): %s", job.id)

        return len(active_job_ids)

    def _sync_sheets_job(self) -> bool:
        from ..models import Settings

        record = Settings.query.filter_by(key="global_settings").first()
        gs = (record.get_value() or {}).get("google_sheets", {}) if record else {}
        auto_sync = bool(gs.get("auto_sync", False))
        spreadsheet_url = gs.get("spreadsheet_url") or gs.get("spreadsheet_id")
        credentials_json = gs.get("credentials_json")

        job_id = "sheets_auto_sync"
        if not auto_sync or not spreadsheet_url or not credentials_json:
            if self._scheduler.get_job(job_id) is not None:
                self._scheduler.remove_job(job_id)
                logger.info("Job Google Sheets removido (auto_sync desativado).")
            return False

        interval_minutes = max(1, int(gs.get("sync_interval", 60) or 60))
        expected_name = f"sheets_sync|{interval_minutes}"
        existing = self._scheduler.get_job(job_id)
        if existing is not None and existing.name == expected_name:
            return True

        self._scheduler.add_job(
            "rodou_dashboard.app.runtime.scheduler:_run_scheduled_sheets_sync",
            trigger=IntervalTrigger(minutes=interval_minutes, timezone=self._timezone),
            id=job_id,
            name=expected_name,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        logger.info("Job Google Sheets agendado a cada %d minuto(s).", interval_minutes)
        return True

    def _sync_gestaoclick_job(self) -> bool:
        """Job da "Sincronização automática" do GestãoClick: só com o interruptor ligado e as chaves salvas."""
        from ..models import Settings

        record = Settings.query.filter_by(key="global_settings").first()
        ak = (record.get_value() or {}).get("api_keys", {}) if record else {}
        job_id = "gestaoclick_auto_sync"
        configured = bool(str(ak.get("gestaoclick_access_token") or "").strip() and str(ak.get("gestaoclick_secret_token") or "").strip())
        if not (bool(ak.get("gestaoclick_auto_sync", False)) and configured):
            if self._scheduler.get_job(job_id) is not None:
                self._scheduler.remove_job(job_id)
                logger.info("Job GestãoClick removido (sincronização automática desligada ou sem credenciais).")
            return False

        try:
            interval = max(5, int(ak.get("gestaoclick_sync_interval", GESTAOCLICK_SYNC_MINUTES) or GESTAOCLICK_SYNC_MINUTES))
        except (TypeError, ValueError):
            interval = GESTAOCLICK_SYNC_MINUTES
        expected_name = f"gestaoclick_sync|{interval}"
        existing = self._scheduler.get_job(job_id)
        if existing is not None and existing.name == expected_name:
            return True
        self._scheduler.add_job(
            "rodou_dashboard.app.runtime.scheduler:_run_scheduled_gestaoclick_sync",
            trigger=IntervalTrigger(minutes=interval, timezone=self._timezone),
            id=job_id,
            name=expected_name,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        logger.info("Job GestãoClick agendado a cada %d minuto(s).", interval)
        return True

    def _sync_inlabs_job(self) -> bool:
        """Agenda a carga diária do INLABS às 06:59 e 23:59 (cron do upstream)."""
        job_id = "inlabs_daily_load"
        cron_expr = "59 6,23 * * *"
        expected_name = f"inlabs_daily_load|{cron_expr}"
        existing = self._scheduler.get_job(job_id)
        if existing is not None and existing.name == expected_name:
            return True

        trigger = CronTrigger.from_crontab(cron_expr, timezone=self._timezone)
        self._scheduler.add_job(
            "rodou_dashboard.app.runtime.scheduler:_run_scheduled_inlabs_load",
            trigger=trigger,
            id=job_id,
            name=expected_name,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=_MISFIRE_GRACE_SECONDS,
        )
        logger.info("Job INLABS agendado (%s).", cron_expr)
        return True

    def reload(self) -> Dict[str, Any]:
        """Sincroniza os jobs de rotinas YAML, Google Sheets e carga INLABS."""
        with self._lock:
            with self._app.app_context():
                routines_count = self._sync_routine_jobs()
                sheets_active = self._sync_sheets_job()
                gestaoclick_active = self._sync_gestaoclick_job()
                inlabs_active = self._sync_inlabs_job()
        return {
            "routines": routines_count,
            "sheets_active": sheets_active,
            "gestaoclick_active": gestaoclick_active,
            "inlabs_active": inlabs_active,
        }

    def list_jobs(self) -> List[Dict[str, Any]]:
        """Retorna resumo dos jobs cadastrados no APScheduler."""
        jobs = []
        for job in self._scheduler.get_jobs():
            next_run = getattr(job, "next_run_time", None)
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": next_run.isoformat() if next_run else None,
                }
            )
        return jobs


def init_scheduler(app: Any, db_path: Optional[Path] = None, start: bool = True) -> RegistraleScheduler:
    """Inicializa (ou reutiliza) o singleton do `RegistraleScheduler`."""
    global _SCHEDULER_INSTANCE
    with _SCHEDULER_LOCK:
        if _SCHEDULER_INSTANCE is None:
            _SCHEDULER_INSTANCE = RegistraleScheduler(app, db_path=db_path)
            if start:
                _SCHEDULER_INSTANCE.start()
            _SCHEDULER_INSTANCE.reload()
        return _SCHEDULER_INSTANCE


def get_scheduler() -> Optional[RegistraleScheduler]:
    """Retorna a instância ativa do `RegistraleScheduler`, se houver."""
    return _SCHEDULER_INSTANCE


def reload_scheduler_if_running() -> None:
    """Recarrega os jobs do agendador local se estiver ativo."""
    inst = _SCHEDULER_INSTANCE
    if inst is not None:
        try:
            inst.reload()
        except Exception as exc:
            logger.warning("Erro ao recarregar agendador local: %s", exc)


def shutdown_scheduler(wait: bool = False) -> None:
    """Encerra o singleton do agendador local, se ativo."""
    global _SCHEDULER_INSTANCE
    with _SCHEDULER_LOCK:
        if _SCHEDULER_INSTANCE is not None:
            _SCHEDULER_INSTANCE.shutdown(wait=wait)
            _SCHEDULER_INSTANCE = None
