import os
import logging
from datetime import datetime
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

def get_inlabs_postgres_engine():
    """Retorna uma engine de conexão com o PostgreSQL do INLABS com timeout seguro."""
    inlabs_db_url = os.getenv('INLABS_DB_URL', 'postgresql+pg8000://airflow:airflow@postgres:5432/inlabs')
    if 'localhost' in inlabs_db_url and os.path.exists('/.dockerenv'):
        inlabs_db_url = inlabs_db_url.replace('localhost', 'postgres')
    return create_engine(inlabs_db_url, connect_args={'timeout': 5})

def get_downloaded_dates(start_date=None, end_date=None):
    """
    Retorna o conjunto (set) de datas (formato 'YYYY-MM-DD') com matérias salvas
    no PostgreSQL do INLABS (tabela dou_inlabs.article_raw).
    """
    downloaded = set()
    try:
        engine = get_inlabs_postgres_engine()
        with engine.connect() as conn:
            conn.execute(text("SET statement_timeout = 5000"))
            if start_date and end_date:
                query = text(
                    "SELECT DISTINCT CAST(pubdate AS DATE)::text FROM dou_inlabs.article_raw "
                    "WHERE pubdate >= :s_dt AND pubdate < CAST(:e_dt AS DATE) + interval '1 day'"
                )
                result = conn.execute(query, {"s_dt": start_date, "e_dt": end_date})
            else:
                result = conn.execute(text("SELECT DISTINCT CAST(pubdate AS DATE)::text FROM dou_inlabs.article_raw"))
            downloaded = set(row[0] for row in result)
    except Exception as e:
        logger.warning(f"Erro ao consultar datas no PostgreSQL do INLABS: {e}")
        try:
            from ..models import InlabsDownloadLog
            query = InlabsDownloadLog.query.filter_by(status='success')
            if start_date and end_date:
                query = query.filter(InlabsDownloadLog.date_str >= start_date, InlabsDownloadLog.date_str <= end_date)
            downloaded = set(log.date_str for log in query.all())
        except Exception:
            pass
    return downloaded

def is_date_loaded(date_str):
    """Verifica se uma data específica já possui matérias carregadas no PostgreSQL."""
    if not date_str:
        return False, 0
    try:
        engine = get_inlabs_postgres_engine()
        with engine.connect() as conn:
            conn.execute(text("SET statement_timeout = 3000"))
            res = conn.execute(
                text("SELECT COUNT(*) FROM dou_inlabs.article_raw WHERE CAST(pubdate AS DATE) = :dt"),
                {"dt": date_str}
            ).scalar()
            count = int(res or 0)
            return (count > 0), count
    except Exception as e:
        logger.warning(f"Erro ao checar data {date_str} no PostgreSQL: {e}")
        try:
            from ..models import InlabsDownloadLog
            log = InlabsDownloadLog.query.filter_by(date_str=date_str, status='success').first()
            if log:
                return True, 1
        except Exception:
            pass
        return False, 0

def record_inlabs_download_success(date_str):
    """Registra ou atualiza o log de download no SQLite com timestamp atual."""
    if not date_str:
        return
    try:
        from ..models import InlabsDownloadLog, db
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        existing = InlabsDownloadLog.query.filter_by(date_str=date_str).first()
        if existing:
            existing.downloaded_at = now_str
            existing.status = 'success'
        else:
            new_log = InlabsDownloadLog(date_str=date_str, downloaded_at=now_str, status='success')
            db.session.add(new_log)
        db.session.commit()
    except Exception as e:
        logger.error(f"Erro ao salvar InlabsDownloadLog para {date_str}: {e}")

def enforce_inlabs_retention_limit(max_days=120, protected_dates=None):
    """
    Garante que o PostgreSQL mantenha no máximo `max_days` (padrão 120) dias distintos baixados.
    Exclui os dias mais antigos baseado na data em que foram baixados (`downloaded_at` no SQLite / LRU).
    Protege explicitamente as datas em `protected_dates` (ex: dias do mês que está sendo baixado/pesquisado).
    """
    if protected_dates is None:
        protected_dates = set()
    else:
        protected_dates = set(str(d) for d in protected_dates)

    from ..models import InlabsDownloadLog, db

    # 1. Identifica todos os dias distintos presentes no PostgreSQL
    postgres_dates = get_downloaded_dates()
    total_dates = len(postgres_dates)
    if total_dates <= max_days:
        return 0

    excess_count = total_dates - max_days

    # 2. Ordena os logs de download do SQLite por downloaded_at ASC (mais antigos primeiro)
    try:
        logs = InlabsDownloadLog.query.order_by(InlabsDownloadLog.downloaded_at.asc()).all()
        logged_order = [log.date_str for log in logs]
    except Exception:
        logged_order = []

    # Datas presentes no PostgreSQL mas sem registro em log são consideradas candidatas prioritárias
    unlogged_dates = [d for d in postgres_dates if d not in logged_order]
    candidate_dates = unlogged_dates + [d for d in logged_order if d in postgres_dates]

    # 3. Filtra para NUNCA apagar datas protegidas
    deletable_dates = [d for d in candidate_dates if d not in protected_dates]
    dates_to_delete = deletable_dates[:excess_count]

    if not dates_to_delete:
        return 0

    deleted_count = 0
    try:
        engine = get_inlabs_postgres_engine()
        if engine:
            with engine.connect() as conn:
                for dt in dates_to_delete:
                    conn.execute(
                        text("DELETE FROM dou_inlabs.article_raw WHERE CAST(pubdate AS DATE) = :dt"),
                        {"dt": dt}
                    )
                    deleted_count += 1
                conn.commit()
    except Exception as e:
        logger.warning(f"Aviso ao deletar datas no PostgreSQL: {e}")

    try:
        InlabsDownloadLog.query.filter(InlabsDownloadLog.date_str.in_(dates_to_delete)).delete(synchronize_session=False)
        db.session.commit()
        if deleted_count == 0:
            deleted_count = len(dates_to_delete)
        logger.info(f"Retenção INLABS: {deleted_count} dia(s) excluído(s) para respeitar limite de {max_days} dias: {dates_to_delete}")
    except Exception as e:
        logger.error(f"Erro ao remover logs no SQLite na retenção INLABS: {e}")
        try:
            db.session.rollback()
        except Exception:
            pass

    return deleted_count
