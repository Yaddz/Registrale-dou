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

def normalize_cnpj(cnpj):
    if not cnpj: return ""
    return re.sub(r'[^A-Za-z0-9]', '', str(cnpj)).upper()

def get_monitored_cnpjs():
    dag_confs_path = os.path.join(BASE_DIR, "dag_confs")
    yaml_files = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_sync.yaml"))
    if not yaml_files:
        yaml_files = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_part_*.yaml"))
    if not yaml_files:
        base = os.path.join(dag_confs_path, "Pesquisa_cnpj.yaml")
        if os.path.exists(base):
            yaml_files = [base]
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
    return active_cnpjs

def get_last_search_time():
    if not os.path.exists(LOGS_DIR): return "N/A"
    log_files = glob.glob(os.path.join(LOGS_DIR, "dag_id=pesquisa_cnpj*", "run_id=*", "task_id=exec_searchs.exec_search_*", "attempt=*.log"), recursive=True)
    if not log_files: return "N/A"
    try:
        latest_log = max(log_files, key=os.path.getmtime)
        return datetime.fromtimestamp(os.path.getmtime(latest_log), timezone(timedelta(hours=-3))).strftime('%d/%m %H:%M')
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

def get_routines():
    dag_confs_path = os.path.join(BASE_DIR, "dag_confs")
    yaml_files = glob.glob(os.path.join(dag_confs_path, "*.yaml"))
    
    routines = []
    sync_parts = []
    sync_base_data = None
    
    for f_path in yaml_files:
        name = os.path.basename(f_path)
        
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
    
    if total_cnpjs == 0 and sync_base_data:
        base_yaml = os.path.join(dag_confs_path, "Pesquisa_cnpj.yaml")
        if os.path.exists(base_yaml):
            try:
                with open(base_yaml, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    search = data.get('dag', {}).get('search', [])
                    if isinstance(search, list):
                        for block in search:
                            total_cnpjs += len(block.get('terms', []))
                    else:
                        total_cnpjs += len(search.get('terms', []))
            except: pass

    sync_routine = {
        "id": "Sincronização Automática (GestãoClick)",
        "file": "Pesquisa_cnpj.yaml",
        "description": f"Sincronização automática via API. Monitorando {total_cnpjs} CNPJs.",
        "schedule": sync_base_data.get('schedule', '0 5 * * *') if sync_base_data else "0 5 * * *",
        "terms": [f"{total_cnpjs} CNPJs monitorados"],
        "organs": sync_base_data.get('organs', ["Diversos"]) if sync_base_data else ["Diversos"],
        "department": sync_base_data.get('department', ["Diversos"]) if sync_base_data else ["Diversos"],
        "sections": sync_base_data.get('sections', ["SECAO_1", "SECAO_2", "SECAO_3"]) if sync_base_data else ["SECAO_1", "SECAO_2", "SECAO_3"],
        "emails": sync_base_data.get('emails', []) if sync_base_data else [],
        "subject": sync_base_data.get('subject', '') if sync_base_data else '',
        "type": "sync",
        "is_exact_search": sync_base_data.get('is_exact_search', True) if sync_base_data else True,
        "force_rematch": sync_base_data.get('force_rematch', True) if sync_base_data else True,
        "terms_ignore": sync_base_data.get('terms_ignore', []) if sync_base_data else [],
        "source": sync_base_data.get('source', 'DOU') if sync_base_data else 'DOU'
    }
    
    routines.insert(0, sync_routine)
    return routines

def rebuild_yaml_from_db():
    import copy, math
    from ..models import Company

    # 1. Buscar CNPJs ativos
    active_companies = Company.query.filter_by(situacao='Ativa', status=True).all()
    all_cnpjs = sorted(set(normalize_cnpj(c.cnpj) for c in active_companies if c.cnpj))

    # 2. Carregar YAML base como template
    base_yaml = os.path.join(BASE_DIR, "dag_confs", "Pesquisa_cnpj.yaml")
    if not os.path.exists(base_yaml):
        logger.warning("Pesquisa_cnpj.yaml não encontrado, impossível rebuild.")
        return

    with open(base_yaml, 'r', encoding='utf-8') as f:
        template_data = yaml.safe_load(f)

    dag = template_data.get('dag', {})
    search_template = dag.get('search', [{}])
    if isinstance(search_template, list):
        search_template = search_template[0] if len(search_template) > 0 else {}

    # 3. Limpar arquivos de partes isoladas que foram gerados indevidamente
    dag_confs_path = os.path.join(BASE_DIR, "dag_confs")
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

    # 5. Escrita atômica no arquivo único
    tmp_path = base_yaml + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(template_data, f, allow_unicode=True, sort_keys=False)
    os.replace(tmp_path, base_yaml)

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
                uf=emp.get('uf', ''), cidade=emp.get('cidade', ''),
                email=emp.get('email', ''), telefone=emp.get('telefone', ''),
                situacao=emp.get('situacao', 'Ativa'), origem='GestaoClick'
            )
            db.session.add(existing)
            count_new += 1
        else:
            if existing.origem == 'Manual': continue
            existing.nome = emp.get('razao_social', emp.get('nome', existing.nome))
            existing.uf = emp.get('uf', existing.uf)
            existing.cidade = emp.get('cidade', existing.cidade)
            existing.email = emp.get('email', existing.email)
            existing.telefone = emp.get('telefone', existing.telefone)
            existing.situacao = emp.get('situacao', existing.situacao)
            count_updated += 1
    db.session.commit()
    logger.info(f"Sync JSON->DB: {count_new} novas, {count_updated} atualizadas")
