import os
import glob
import yaml
import re
from datetime import datetime, timezone, timedelta

# Replicando a lógica do BASE_DIR usada no app antigo
# Dependendo da estrutura, ajuste o BASE_DIR para o local correto
# No app antigo, estava na raiz. Aqui estamos em rodou_dashboard/app/services
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
LOGS_DIR = os.path.join(BASE_DIR, "mnt", "airflow-logs")

import logging
logger = logging.getLogger(__name__)

import time

_cnpjs_cache = {'time': 0, 'data': set(), 'mtime': 0}
_last_search_cache = {'time': 0, 'data': 'N/A'}
_next_search_cache = {'time': 0, 'data': 'N/A'}

def normalize_cnpj(cnpj):
    if not cnpj: return ""
    return re.sub(r'[^A-Za-z0-9]', '', str(cnpj)).upper()

def get_dag_confs_path():
    candidates = [
        os.path.join(BASE_DIR, "dag_confs"),
        os.path.abspath("dag_confs"),
        "/app/dag_confs",
        "/dag_confs"
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.isdir(c):
            return c
    default_p = os.path.join(BASE_DIR, "dag_confs")
    try:
        os.makedirs(default_p, exist_ok=True)
    except: pass
    return default_p

def get_base_yaml_path():
    dag_confs_path = get_dag_confs_path()
    return os.path.join(dag_confs_path, "Pesquisa_cnpj.yaml")

def touch_dag_generator():
    """Atualiza o timestamp de modificação do gerador de DAGs do Airflow para forçar recarregamento imediato."""
    candidates = [
        os.path.join(BASE_DIR, "src", "dou_dag_generator.py"),
        "/opt/airflow/dags/ro_dou_src/dou_dag_generator.py",
        "/app/src/dou_dag_generator.py",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src", "dou_dag_generator.py"))
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                os.utime(p, None)
                logger.info(f"Gerador de DAGs atualizado com sucesso: {p}")
            except Exception as e:
                logger.warning(f"Aviso ao atualizar mtime do gerador DAG {p}: {e}")

def get_monitored_cnpjs():
    global _cnpjs_cache
    now = time.time()
    if (now - _cnpjs_cache['time']) < 60 and _cnpjs_cache['data']:
        return _cnpjs_cache['data']
        
    dag_confs_path = get_dag_confs_path()
    yaml_files = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_sync.yaml"))
    if not yaml_files:
        yaml_files = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_part_*.yaml"))
    if not yaml_files:
        base = get_base_yaml_path()
        if os.path.exists(base):
            yaml_files = [base]
    
    # Se o arquivo não mudou no disco
    if yaml_files:
        current_mtime = max(os.path.getmtime(f) for f in yaml_files)
        if current_mtime == _cnpjs_cache['mtime'] and _cnpjs_cache['data']:
            _cnpjs_cache['time'] = now
            return _cnpjs_cache['data']
    else:
        current_mtime = 0

    active_cnpjs = set()
    for f_path in yaml_files:
        try:
            with open(f_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                search = config.get('dag', {}).get('search', [])
                if isinstance(search, list):
                    for s in search:
                        terms = s.get('terms', [])
                        if isinstance(terms, list):
                            for t in terms: active_cnpjs.add(normalize_cnpj(t))
                else:
                    terms = search.get('terms', [])
                    if isinstance(terms, list):
                        for t in terms: active_cnpjs.add(normalize_cnpj(t))
        except: continue
    
    _cnpjs_cache = {'time': now, 'data': active_cnpjs, 'mtime': current_mtime}
    return active_cnpjs

def get_last_search_time():
    global _last_search_cache
    now = time.time()
    if (now - _last_search_cache['time']) < 15 and _last_search_cache['data'] != 'N/A':
        return _last_search_cache['data']

    if not os.path.exists(LOGS_DIR): return "N/A"
    
    # Varre apenas os 20 runs mais recentes de pesquisa_cnpj para alta performance
    dag_dirs = glob.glob(os.path.join(LOGS_DIR, "dag_id=pesquisa_cnpj*"))
    run_dirs = []
    for d in dag_dirs:
        try:
            for r in os.listdir(d):
                p = os.path.join(d, r)
                if os.path.isdir(p):
                    run_dirs.append(p)
        except Exception:
            pass
    
    if not run_dirs:
        return "N/A"
        
    run_dirs.sort(key=os.path.getmtime, reverse=True)
    recent_runs = run_dirs[:10]
    
    log_files = []
    for r in recent_runs:
        log_files.extend(glob.glob(os.path.join(r, "task_id=exec_searchs.exec_search_*", "attempt=*.log")))
        if not log_files:
            log_files.extend(glob.glob(os.path.join(r, "task_id=exec_search_*", "attempt=*.log")))
            
    if not log_files: 
        return "N/A"
    try:
        latest_log = max(log_files, key=os.path.getmtime)
        res = datetime.fromtimestamp(os.path.getmtime(latest_log), timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M')
        _last_search_cache = {'time': now, 'data': res}
        return res
    except:
        return "N/A"

def get_next_search_time():
    now = datetime.now(timezone(timedelta(hours=-3)))
    schedule_hour, schedule_minute = 8, 0
    try:
        # 1. Tentar ler do banco de dados (prioridade)
        from flask import current_app
        if current_app:
            from ..models import Settings
            s_rec = Settings.query.filter_by(key='main_dag_settings').first()
            if s_rec:
                s_val = s_rec.get_value()
                if isinstance(s_val, dict) and 'schedule' in s_val:
                    sched = s_val.get('schedule', '0 8 * * *')
                    parts = sched.split()
                    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                        schedule_minute = int(parts[0])
                        schedule_hour = int(parts[1])
                        next_run = now.replace(hour=schedule_hour, minute=schedule_minute, second=0, microsecond=0)
                        if now >= next_run: next_run += timedelta(days=1)
                        while next_run.weekday() > 4: next_run += timedelta(days=1)
                        return next_run.strftime('%d/%m/%Y %H:%M')
        
        # 2. Tentar ler de Pesquisa_cnpj.yaml
        confs_path = get_dag_confs_path()
        yaml_candidates = [
            os.path.join(confs_path, "Pesquisa_cnpj.yaml"),
            os.path.join(BASE_DIR, "dag_confs", "Pesquisa_cnpj.yaml")
        ]
        for y_path in yaml_candidates:
            if os.path.exists(y_path):
                with open(y_path, 'r', encoding='utf-8') as f:
                    d = yaml.safe_load(f) or {}
                    sched = d.get('dag', {}).get('schedule', '0 8 * * *')
                    parts = sched.split()
                    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                        schedule_minute = int(parts[0])
                        schedule_hour = int(parts[1])
                        break
    except: pass
    
    next_run = now.replace(hour=schedule_hour, minute=schedule_minute, second=0, microsecond=0)
    if now >= next_run:
        next_run += timedelta(days=1)
    
    while next_run.weekday() > 4:
        next_run += timedelta(days=1)
        
    return next_run.strftime('%d/%m/%Y %H:%M')

def cleanup_orphaned_temp_dags(max_age_seconds=60, force_all=False):
    """
    Remove arquivos temporários de DAGs (temp_*.yaml e temp_*.yml) do disco,
    desregistra as DAGs correspondentes na API do Airflow e limpa pastas de logs órfãs.
    """
    import shutil
    import requests
    from .airflow_service import get_airflow_auth, get_airflow_url
    
    dag_confs_path = get_dag_confs_path()
    pattern_yaml = os.path.join(dag_confs_path, "*.yaml")
    pattern_yml = os.path.join(dag_confs_path, "*.yml")
    all_files = glob.glob(pattern_yaml) + glob.glob(pattern_yml)
    
    cleaned_count = 0
    now = time.time()
    
    for f_path in all_files:
        name = os.path.basename(f_path)
        name_lower = name.lower()
        if name_lower.startswith("temp_") or "temp_adhoc" in name_lower or "temp_monthly" in name_lower:
            try:
                mtime = os.path.getmtime(f_path)
                if force_all or (now - mtime) >= max_age_seconds:
                    # 1. Tentar ler o dag_id de dentro do yaml ou deduzir do nome
                    dag_id = os.path.splitext(name)[0]
                    try:
                        with open(f_path, 'r', encoding='utf-8') as yf:
                            ydata = yaml.safe_load(yf)
                            if isinstance(ydata, dict) and 'dag' in ydata:
                                dag_id = ydata['dag'].get('id', dag_id)
                    except Exception:
                        pass
                    
                    # 2. Verificar se a DAG possui execuções ativas ('running' ou 'queued') no Airflow.
                    # Nunca apagar se ainda estiver em execução (a menos que force_all seja explicitamente True).
                    if not force_all:
                        try:
                            auth = get_airflow_auth()
                            airflow_url = get_airflow_url()
                            import urllib.parse
                            dag_id_quoted = urllib.parse.quote(str(dag_id), safe='')
                            r_check = requests.get(
                                f"{airflow_url}/api/v1/dags/{dag_id_quoted}/dagRuns?order_by=-execution_date&limit=15",
                                auth=auth,
                                timeout=5
                            )
                            if r_check.status_code == 200:
                                runs = r_check.json().get('dag_runs', [])
                                has_active = any(run.get('state') in ('running', 'queued') for run in runs)
                                if has_active:
                                    logger.info(f"DAG temporária {dag_id} ainda possui execuções ativas no Airflow. Limpeza ignorada.")
                                    continue
                        except Exception:
                            pass

                    # 3. Excluir o arquivo YAML do disco
                    try:
                        if os.path.exists(f_path):
                            os.remove(f_path)
                            cleaned_count += 1
                            logger.info(f"Arquivo YAML temporário removido do disco: {f_path}")
                    except Exception as rm_err:
                        logger.warning(f"Erro ao remover arquivo temporário {f_path}: {rm_err}")
                        
                    # 4. Desregistrar DAG do Airflow se disponível
                    try:
                        auth = get_airflow_auth()
                        airflow_url = get_airflow_url()
                        requests.delete(f"{airflow_url}/api/v1/dags/{dag_id}", auth=auth, timeout=5)
                    except Exception:
                        pass
                        
                    # 5. Remover pastas de logs temporárias em mnt/airflow-logs/dag_id=...
                    try:
                        temp_log_dir = os.path.join(LOGS_DIR, f"dag_id={dag_id}")
                        if os.path.exists(temp_log_dir) and os.path.isdir(temp_log_dir):
                            shutil.rmtree(temp_log_dir, ignore_errors=True)
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Erro ao processar limpeza da DAG temporária {f_path}: {e}")
                
    if cleaned_count > 0:
        try:
            generator_path = os.path.join(BASE_DIR, "src", "dou_dag_generator.py")
        except Exception:
            pass
            
    return cleaned_count

_routines_cache = None
_routines_cache_sig = None
_routines_cache_time = 0

def clear_routines_cache():
    global _routines_cache, _routines_cache_sig, _routines_cache_time
    _routines_cache = None
    _routines_cache_sig = None
    _routines_cache_time = 0

def get_routines():
    global _routines_cache, _routines_cache_sig, _routines_cache_time
    # Executa limpeza automática de DAGs temporárias órfãs (arquivos com mais de 1h e sem execuções ativas)
    try:
        cleanup_orphaned_temp_dags(max_age_seconds=3600)
    except Exception as e:
        logger.warning(f"Erro na limpeza automática de DAGs temporárias: {e}")

    dag_confs_path = get_dag_confs_path()
    yaml_files = glob.glob(os.path.join(dag_confs_path, "*.yaml"))
    
    try:
        current_sig = tuple(sorted((f, os.path.getmtime(f)) for f in yaml_files if os.path.exists(f)))
    except Exception:
        current_sig = None

    now = time.time()
    if _routines_cache is not None and current_sig is not None and _routines_cache_sig == current_sig and (now - _routines_cache_time < 15):
        return [dict(r) for r in _routines_cache]
    
    routines = []
    sync_parts = []
    sync_base_data = None
    
    for f_path in yaml_files:
        name = os.path.basename(f_path)
        
        # Ignora arquivos temporários gerados para pesquisas ad-hoc/mensais
        if name.lower().startswith("temp_") or "temp_monthly" in name.lower():
            continue
            
        if "pesquisa_cnpj" in name.lower():
            if "_part_" in name.lower() or "_sync" in name.lower():
                sync_parts.append(f_path)
                continue
            elif name.lower() == "pesquisa_cnpj.yaml":
                try:
                    with open(f_path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                        if data and 'dag' in data:
                            dag = data.get('dag', {})
                            search = dag.get('search', {})
                            if isinstance(search, list): search = search[0] if search else {}
                            report = dag.get('report', {})
                            active_val = dag.get('active', not dag.get('is_paused', False))
                            sync_base_data = {
                                "id": dag.get('id', name),
                                "file": name,
                                "description": dag.get('description', ''),
                                "schedule": dag.get('schedule', '0 5 * * *'),
                                "terms": search.get('terms', []),
                                "organs": search.get('department', []),
                                "sections": search.get('dou_sections', ["SECAO_1", "SECAO_2", "SECAO_3"]),
                                "emails": report.get('emails', []),
                                "subject": report.get('subject', ''),
                                "type": "sync",
                                "active": bool(active_val),
                                "is_exact_search": search.get('is_exact_search', True),
                                "force_rematch": search.get('force_rematch', True),
                                "terms_ignore": search.get('terms_ignore', []),
                                "source": search.get('sources', ['INLABS'])[0] if isinstance(search.get('sources'), list) and len(search.get('sources')) > 0 else ('INLABS' if 'inlabs' in dag.get('tags', []) else 'DOU')
                            }
                except: pass
                continue

        try:
            with open(f_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if not data or 'dag' not in data: continue
                dag = data.get('dag', {})
                search = dag.get('search', {})
                if isinstance(search, list): search = search[0] if search else {}
                report = dag.get('report', {})
                active_val = dag.get('active', not dag.get('is_paused', False))
                
                routines.append({
                    "id": dag.get('id', name),
                    "file": name,
                    "description": dag.get('description', ''),
                    "schedule": dag.get('schedule', '0 5 * * *'),
                    "terms": search.get('terms', []),
                    "organs": search.get('department', []),
                    "department": search.get('department', []),
                    "sections": search.get('dou_sections', ["SECAO_1", "SECAO_2", "SECAO_3"]),
                    "emails": report.get('emails', []),
                    "subject": report.get('subject', ''),
                    "type": "custom",
                    "active": bool(active_val),
                    "is_exact_search": search.get('is_exact_search', True),
                    "force_rematch": search.get('force_rematch', True),
                    "terms_ignore": search.get('terms_ignore', []),
                    "source": search.get('sources', ['INLABS'])[0] if isinstance(search.get('sources'), list) and len(search.get('sources')) > 0 else ('INLABS' if 'inlabs' in dag.get('tags', []) else 'DOU')
                })
        except Exception as e: 
            logger.error(f"Erro ao ler rotina {name}: {e}")
            continue
    
    total_cnpjs = len(sync_base_data.get('terms', [])) if sync_base_data else 0
    for sp in sync_parts:
        try:
            with open(sp, 'r', encoding='utf-8') as f:
                d = yaml.safe_load(f)
                s = d.get('dag', {}).get('search', [])
                if isinstance(s, list):
                    for block in s:
                        total_cnpjs += len(block.get('terms', []))
                else:
                    total_cnpjs += len(s.get('terms', []))
        except: continue
    
    # Sincronização inteligente com a base de dados
    try:
        from ..models import Company, Settings
        db_active_count = Company.query.filter_by(status=True).count()
        if db_active_count > 0 and (total_cnpjs != db_active_count or not os.path.exists(get_base_yaml_path())):
            rebuild_yaml_from_db()
            total_cnpjs = db_active_count
    except Exception:
        pass

    db_main_dag = {}
    try:
        from ..models import Settings
        s_rec = Settings.query.filter_by(key='main_dag_settings').first()
        if s_rec:
            s_val = s_rec.get_value()
            if isinstance(s_val, dict):
                db_main_dag = s_val
    except Exception:
        pass

    sync_routine = {
        "id": "Monitoramento Padrão (Empresas Ativas)",
        "file": "Pesquisa_cnpj.yaml",
        "description": f"Busca padrão diária vinculada às empresas com monitoramento ativo na base ({total_cnpjs} CNPJs).",
        "schedule": db_main_dag.get('schedule') or (sync_base_data.get('schedule', '0 8 * * MON-FRI') if sync_base_data else "0 8 * * MON-FRI"),
        "terms": [f"{total_cnpjs} CNPJs monitorados"],
        "organs": db_main_dag.get('organs') or (sync_base_data.get('organs', ["Diversos"]) if sync_base_data else ["Diversos"]),
        "department": db_main_dag.get('department') or (sync_base_data.get('department', ["Diversos"]) if sync_base_data else ["Diversos"]),
        "sections": db_main_dag.get('sections') or (sync_base_data.get('sections', ["SECAO_1", "SECAO_2", "SECAO_3"]) if sync_base_data else ["SECAO_1", "SECAO_2", "SECAO_3"]),
        "emails": db_main_dag.get('emails') or (sync_base_data.get('emails', []) if sync_base_data else []),
        "subject": db_main_dag.get('subject') if 'subject' in db_main_dag else (sync_base_data.get('subject', '') if sync_base_data else ''),
        "type": "sync",
        "active": bool(db_main_dag['active'] if 'active' in db_main_dag else (sync_base_data.get('active', True) if sync_base_data else True)),
        "is_exact_search": bool(db_main_dag['is_exact_search'] if 'is_exact_search' in db_main_dag else (sync_base_data.get('is_exact_search', False) if sync_base_data else False)),
        "force_rematch": bool(db_main_dag['force_rematch'] if 'force_rematch' in db_main_dag else (sync_base_data.get('force_rematch', True) if sync_base_data else True)),
        "terms_ignore": db_main_dag.get('terms_ignore', sync_base_data.get('terms_ignore', []) if sync_base_data else []),
        "source": db_main_dag.get('source', 'INLABS')
    }
    
    routines.insert(0, sync_routine)
    
    _routines_cache = routines
    _routines_cache_sig = current_sig
    _routines_cache_time = now
    return routines

def get_main_dag_info():
    """Retorna as configurações atuais da DAG principal (Pesquisa_cnpj.yaml) e indica se configurações obrigatórias estão pendentes."""
    base_yaml = get_base_yaml_path()
    dag_confs_path = get_dag_confs_path()
    
    # Procura se existe Pesquisa_cnpj.yaml ou partes
    target_path = base_yaml
    if not os.path.exists(target_path):
        parts = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_sync.yaml"))
        if not parts:
            parts = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_part_*.yaml"))
        if parts:
            target_path = parts[0]
            
    emails = []
    subject = ""
    active = True
    schedule = "0 8 * * MON-FRI"
    source = "INLABS"
    file_exists = os.path.exists(target_path)
    
    # 1. Tenta carregar do SQLite (fonte de verdade persistente)
    try:
        from ..models import Settings
        s_rec = Settings.query.filter_by(key='main_dag_settings').first()
        if s_rec:
            s_val = s_rec.get_value()
            if isinstance(s_val, dict):
                emails = s_val.get('emails', [])
                subject = s_val.get('subject', '')
                schedule = s_val.get('schedule', '0 8 * * MON-FRI')
                active = bool(s_val.get('active', True))
    except Exception as e:
        logger.debug(f"Info Settings SQLite: {e}")

    # 2. Se não houver no SQLite, lê do YAML se existir
    if file_exists and not emails and not subject:
        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            dag = data.get('dag', {})
            report = dag.get('report', {})
            yaml_emails = report.get('emails', [])
            if not isinstance(yaml_emails, list):
                yaml_emails = [yaml_emails] if yaml_emails else []
            if yaml_emails:
                emails = yaml_emails
            if report.get('subject'):
                subject = str(report.get('subject', '')).strip()
            active = bool(dag.get('active', not dag.get('is_paused', False)))
            schedule = dag.get('schedule', '0 8 * * MON-FRI')
            tags = dag.get('tags', [])
            source = "INLABS" if "inlabs" in tags else "DOU"
        except Exception as e:
            logger.error(f"Erro ao ler informações da DAG principal: {e}")
            
    if not isinstance(emails, list):
        emails = [emails] if emails else []
            
    # Filtra e-mails válidos
    valid_emails = [str(e).strip() for e in emails if e and str(e).strip()]
    
    missing_fields = []
    if len(valid_emails) == 0:
        missing_fields.append("emails")
    if not subject:
        missing_fields.append("subject")
        
    return {
        "file": "Pesquisa_cnpj.yaml",
        "file_exists": file_exists,
        "emails": valid_emails,
        "subject": subject,
        "active": active,
        "schedule": schedule,
        "source": source,
        "is_configured": len(missing_fields) == 0,
        "missing_fields": missing_fields
    }

def rebuild_yaml_from_db():
    import copy, math, shutil
    from ..models import Company, Settings

    # 1. Buscar CNPJs ativos
    active_companies = Company.query.filter_by(status=True).all()
    all_cnpjs = sorted(set(normalize_cnpj(c.cnpj) for c in active_companies if c.cnpj))

    # 2. Carregar configurações persistentes da DAG principal no SQLite
    db_main_dag = {}
    try:
        s_rec = Settings.query.filter_by(key='main_dag_settings').first()
        if s_rec:
            db_main_dag = s_rec.get_value() or {}
    except Exception:
        pass

    # 3. Carregar YAML base como template
    base_yaml = get_base_yaml_path()
    dag_confs_path = get_dag_confs_path()
    try:
        os.makedirs(dag_confs_path, exist_ok=True)
    except: pass

    if not os.path.exists(base_yaml):
        logger.warning(f"Pesquisa_cnpj.yaml não encontrado em {base_yaml}, criando template inicial.")
        template_data = {
            'dag': {
                'id': 'pesquisa_cnpj_anvisa',
                'description': 'Busca padrão diária vinculada às empresas com monitoramento ativo.',
                'tags': ['pesquisa_cnpj', 'inlabs'],
                'owner': ['CNPJ_SYNC'],
                'schedule': db_main_dag.get('schedule', '0 8 * * MON-FRI'),
                'active': db_main_dag.get('active', True),
                'is_paused': not db_main_dag.get('active', True),
                'dataset': 'inlabs',
                'search': [{
                    'header': 'MONITORAMENTO PADRÃO',
                    'is_exact_search': db_main_dag.get('is_exact_search', True),
                    'force_rematch': db_main_dag.get('force_rematch', True),
                    'department': db_main_dag.get('organs') or db_main_dag.get('department') or ['ANVISA', 'Agência Nacional de Vigilância Sanitária'],
                    'dou_sections': db_main_dag.get('sections') or db_main_dag.get('dou_sections') or ["SECAO_1", "SECAO_2", "SECAO_3"],
                    'terms_ignore': db_main_dag.get('terms_ignore', []),
                    'terms': []
                }],
                'report': {
                    'title': 'MONITORAMENTO PADRÃO',
                    'subject': db_main_dag.get('subject', ''),
                    'skip_null': True,
                    'emails': db_main_dag.get('emails', [])
                }
            }
        }
    else:
        with open(base_yaml, 'r', encoding='utf-8') as f:
            template_data = yaml.safe_load(f) or {}

    dag = template_data.get('dag', {})
    if 'report' not in dag:
        dag['report'] = {
            'title': 'MONITORAMENTO PADRÃO',
            'subject': '',
            'skip_null': True,
            'emails': []
        }
        
    # Se houver configuração persistida no SQLite, aplica com prioridade máxima
    if db_main_dag:
        if 'emails' in db_main_dag:
            dag['report']['emails'] = db_main_dag.get('emails', [])
        if 'subject' in db_main_dag:
            dag['report']['subject'] = db_main_dag.get('subject', '')
        if 'schedule' in db_main_dag:
            dag['schedule'] = db_main_dag.get('schedule', '0 8 * * MON-FRI')
        if 'active' in db_main_dag:
            dag['active'] = db_main_dag.get('active', True)
            dag['is_paused'] = not db_main_dag.get('active', True)

    search_template = dag.get('search', [{}])
    if isinstance(search_template, list):
        search_template = search_template[0] if len(search_template) > 0 else {}

    # 3. Limpar arquivos de partes isoladas que foram gerados indevidamente
    for f in glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_sync.yaml")):
        try: os.remove(f)
        except: pass
    for f in glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_part_*.yaml")):
        try: os.remove(f)
        except: pass

    # 4. Dividir em chunks de 1500
    CHUNK_SIZE = 1500
    import re
    raw_header = search_template.get('header', 'MONITORAMENTO PADRÃO')
    header_base = re.sub(r'\s*-\s*PARTE\s*\d+', '', str(raw_header), flags=re.IGNORECASE).strip()
    if not header_base:
        header_base = "MONITORAMENTO PADRÃO"
    
    class QuotedString(str): pass
    def quoted_scalar_representer(dumper, data):
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style="'")
    yaml.SafeDumper.add_representer(QuotedString, quoted_scalar_representer)

    chunks = [[QuotedString(c) for c in all_cnpjs[i:i+CHUNK_SIZE]] for i in range(0, max(len(all_cnpjs), 1), CHUNK_SIZE)]

    if 'is_exact_search' in db_main_dag:
        exact_search_val = bool(db_main_dag['is_exact_search'])
    elif 'is_exact_search' in search_template:
        exact_search_val = bool(search_template['is_exact_search'])
    else:
        exact_search_val = False

    force_rematch_val = bool(db_main_dag.get('force_rematch', search_template.get('force_rematch', True)))
    organs_val = db_main_dag.get('organs') or db_main_dag.get('department') or search_template.get('department', ['ANVISA', 'Agência Nacional de Vigilância Sanitária'])
    sections_val = db_main_dag.get('sections') or db_main_dag.get('dou_sections') or search_template.get('dou_sections', ["SECAO_1", "SECAO_2", "SECAO_3"])
    terms_ignore_val = db_main_dag.get('terms_ignore', search_template.get('terms_ignore', []))

    search_blocks = []
    for idx, chunk in enumerate(chunks, 1):
        block = copy.deepcopy(search_template)
        block['terms'] = chunk
        block['header'] = f"{header_base} - PARTE {idx}" if len(chunks) > 1 else header_base
        block['is_exact_search'] = exact_search_val
        block['force_rematch'] = force_rematch_val
        block['department'] = organs_val
        block['dou_sections'] = sections_val
        block['terms_ignore'] = terms_ignore_val
        block['full_text'] = False
        search_blocks.append(block)

    dag['search'] = search_blocks
    template_data['dag'] = dag

    # 5. Escrita segura com criação prévia de diretório
    target_dir = os.path.dirname(os.path.abspath(base_yaml))
    try:
        os.makedirs(target_dir, exist_ok=True)
    except: pass

    try:
        tmp_path = base_yaml + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(template_data, f, allow_unicode=True, sort_keys=False)
        try:
            os.replace(tmp_path, base_yaml)
        except (OSError, IOError):
            try:
                shutil.move(tmp_path, base_yaml)
            except Exception:
                with open(base_yaml, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(template_data, f, allow_unicode=True, sort_keys=False)
                try:
                    if os.path.exists(tmp_path): os.remove(tmp_path)
                except: pass
    except Exception as err:
        try:
            with open(base_yaml, 'w', encoding='utf-8') as f:
                yaml.safe_dump(template_data, f, allow_unicode=True, sort_keys=False)
        except Exception as final_err:
            logger.error(f"Erro ao salvar YAML base em {base_yaml}: {final_err}")

    # Notifica o Airflow para recarregar o gerador de DAGs imediatamente
    touch_dag_generator()
    logger.info(f"YAML reconstruído com {len(all_cnpjs)} CNPJs em 1 arquivo com {len(chunks)} parte(s) (is_exact_search={exact_search_val}).")

def sync_json_to_db():
    import json
    from ..models import db, Company

    metadata_file = os.path.join(BASE_DIR, "data", "monitored_companies.json")
    if not os.path.exists(metadata_file):
        return

    with open(metadata_file, 'r', encoding='utf-8') as f:
        empresas = json.load(f)

    count_new, count_updated = 0, 0
    for emp in empresas:
        cnpj = emp.get('cnpj', '')
        if not cnpj: continue
        cnpj_norm = normalize_cnpj(cnpj)
        existing = Company.query.filter_by(cnpj_norm=cnpj_norm).first()
        if not existing:
            existing = Company(
                cnpj=cnpj, cnpj_norm=cnpj_norm,
                nome=emp.get('razao_social', emp.get('nome', 'N/A')),
                origem='GestaoClick',
                status=emp.get('status', True)
            )
            db.session.add(existing)
            count_new += 1
        else:
            if existing.origem == 'Manual': continue
            existing.nome = emp.get('razao_social', emp.get('nome', existing.nome))
            existing.status = emp.get('status', existing.status)
            count_updated += 1
    db.session.commit()
    logger.info(f"Sync JSON->DB: {count_new} novas, {count_updated} atualizadas")
