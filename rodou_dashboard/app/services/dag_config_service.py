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
        res = datetime.fromtimestamp(os.path.getmtime(latest_log), timezone(timedelta(hours=-3))).strftime('%d/%m %H:%M')
        _last_search_cache = {'time': now, 'data': res}
        return res
    except:
        return "N/A"

def get_next_search_time():
    now = datetime.now(timezone(timedelta(hours=-3)))
    schedule_hour, schedule_minute = 8, 0
    try:
        yaml_files = glob.glob(os.path.join(BASE_DIR, "dag_confs", "Pesquisa_cnpj_sync.yaml"))
        if yaml_files:
            with open(yaml_files[0], 'r', encoding='utf-8') as f:
                d = yaml.safe_load(f)
                sched = d.get('dag', {}).get('schedule', '0 8 * * *')
                parts = sched.split()
                if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                    schedule_minute = int(parts[0])
                    schedule_hour = int(parts[1])
    except: pass
    
    next_run = now.replace(hour=schedule_hour, minute=schedule_minute, second=0, microsecond=0)
    if now >= next_run:
        next_run += timedelta(days=1)
    
    while next_run.weekday() > 4:
        next_run += timedelta(days=1)
        
    return next_run.strftime('%d/%m %H:%M')

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
                    
                    # 2. Excluir o arquivo YAML do disco
                    try:
                        if os.path.exists(f_path):
                            os.remove(f_path)
                            cleaned_count += 1
                            logger.info(f"Arquivo YAML temporário removido do disco: {f_path}")
                    except Exception as rm_err:
                        logger.warning(f"Erro ao remover arquivo temporário {f_path}: {rm_err}")
                        
                    # 3. Desregistrar DAG do Airflow se disponível
                    try:
                        auth = get_airflow_auth()
                        airflow_url = get_airflow_url()
                        requests.delete(f"{airflow_url}/api/v1/dags/{dag_id}", auth=auth, timeout=5)
                    except Exception:
                        pass
                        
                    # 4. Remover pastas de logs temporárias em mnt/airflow-logs/dag_id=...
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
            if os.path.exists(generator_path):
                os.utime(generator_path, None)
        except Exception:
            pass
            
    return cleaned_count

def get_routines():
    # Executa limpeza automática de DAGs temporárias órfãs (arquivos com mais de 30s ou concluídos)
    try:
        cleanup_orphaned_temp_dags(max_age_seconds=30)
    except Exception as e:
        logger.warning(f"Erro na limpeza automática de DAGs temporárias: {e}")

    dag_confs_path = get_dag_confs_path()
    yaml_files = glob.glob(os.path.join(dag_confs_path, "*.yaml"))
    
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
                            if isinstance(search, list): search = search[0]
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
                                "source": search.get('sources', ['DOU'])[0] if isinstance(search.get('sources'), list) and len(search.get('sources')) > 0 else 'DOU'
                            }
                except: pass
                continue

        try:
            with open(f_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if not data or 'dag' not in data: continue
                dag = data.get('dag', {})
                search = dag.get('search', {})
                if isinstance(search, list): search = search[0]
                report = dag.get('report', {})
                active_val = dag.get('active', not dag.get('is_paused', False))
                
                routines.append({
                    "id": dag.get('id', name),
                    "file": name,
                    "description": dag.get('description', ''),
                    "schedule": dag.get('schedule', '0 5 * * *'),
                    "terms": search.get('terms', []),
                    "organs": search.get('department', []),
                    "sections": search.get('dou_sections', ["SECAO_1", "SECAO_2", "SECAO_3"]),
                    "emails": report.get('emails', []),
                    "subject": report.get('subject', ''),
                    "type": "custom",
                    "active": bool(active_val),
                    "is_exact_search": search.get('is_exact_search', True),
                    "force_rematch": search.get('force_rematch', True),
                    "terms_ignore": search.get('terms_ignore', []),
                    "source": search.get('sources', ['DOU'])[0] if isinstance(search.get('sources'), list) and len(search.get('sources')) > 0 else 'DOU'
                })
        except Exception as e: 
            logger.error(f"Erro ao ler rotina {name}: {e}")
            continue
    
    total_cnpjs = 0
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
        from ..models import Company
        db_active_count = Company.query.filter_by(status=True).count()
        if db_active_count > 0 and (total_cnpjs != db_active_count or not os.path.exists(get_base_yaml_path())):
            rebuild_yaml_from_db()
            total_cnpjs = db_active_count
    except Exception:
        pass

    sync_routine = {
        "id": "Monitoramento Padrão (Empresas Ativas)",
        "file": "Pesquisa_cnpj.yaml",
        "description": f"Busca padrão diária vinculada às empresas com monitoramento ativo na base ({total_cnpjs} CNPJs).",
        "schedule": sync_base_data.get('schedule', '0 5 * * *') if sync_base_data else "0 5 * * *",
        "terms": [f"{total_cnpjs} CNPJs monitorados"],
        "organs": sync_base_data.get('organs', ["Diversos"]) if sync_base_data else ["Diversos"],
        "department": sync_base_data.get('department', ["Diversos"]) if sync_base_data else ["Diversos"],
        "sections": sync_base_data.get('sections', ["SECAO_1", "SECAO_2", "SECAO_3"]) if sync_base_data else ["SECAO_1", "SECAO_2", "SECAO_3"],
        "emails": sync_base_data.get('emails', []) if sync_base_data else [],
        "subject": sync_base_data.get('subject', '') if sync_base_data else '',
        "type": "sync",
        "active": sync_base_data.get('active', True) if sync_base_data else True,
        "is_exact_search": sync_base_data.get('is_exact_search', True) if sync_base_data else True,
        "force_rematch": sync_base_data.get('force_rematch', True) if sync_base_data else True,
        "terms_ignore": sync_base_data.get('terms_ignore', []) if sync_base_data else [],
        "source": sync_base_data.get('source', 'DOU') if sync_base_data else 'DOU'
    }
    
    routines.insert(0, sync_routine)
    return routines

def rebuild_yaml_from_db():
    import copy, math, shutil
    from ..models import Company

    # 1. Buscar CNPJs ativos
    active_companies = Company.query.filter_by(status=True).all()
    all_cnpjs = sorted(set(normalize_cnpj(c.cnpj) for c in active_companies if c.cnpj))

    # 2. Carregar YAML base como template
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
                'schedule': '0 8 * * MON-FRI',
                'search': [{
                    'header': 'MONITORAMENTO PADRÃO',
                    'is_exact_search': True,
                    'force_rematch': True,
                    'department': ['ANVISA', 'Agência Nacional de Vigilância Sanitária'],
                    'terms': []
                }],
                'report': {
                    'title': 'MONITORAMENTO PADRÃO',
                    'subject': '[ro-dou] Relatório de Menções',
                    'skip_null': True,
                    'emails': []
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
            'subject': '[ro-dou] Relatório de Menções',
            'skip_null': True,
            'emails': []
        }
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
    header_base = search_template.get('header', 'Pesquisa CNPJ')
    
    class QuotedString(str): pass
    def quoted_scalar_representer(dumper, data):
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style="'")
    yaml.SafeDumper.add_representer(QuotedString, quoted_scalar_representer)

    chunks = [[QuotedString(c) for c in all_cnpjs[i:i+CHUNK_SIZE]] for i in range(0, max(len(all_cnpjs), 1), CHUNK_SIZE)]

    search_blocks = []
    for idx, chunk in enumerate(chunks, 1):
        block = copy.deepcopy(search_template)
        block['terms'] = chunk
        block['header'] = f"{header_base} - PARTE {idx}" if len(chunks) > 1 else header_base
        block['is_exact_search'] = True
        block['force_rematch'] = True
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

    logger.info(f"YAML reconstruído com {len(all_cnpjs)} CNPJs em 1 arquivo com {len(chunks)} parte(s).")

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
