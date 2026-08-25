from flask import Blueprint, request, jsonify, session, current_app
import os
import yaml
import glob
import re
import threading
import requests
import logging
from datetime import datetime, timezone, timedelta
from .auth import login_required
from ..models import db, Mention, Company, SyncHistory
from ..services.dag_config_service import get_routines, get_dag_confs_path
from ..services.airflow_service import trigger_airflow_dag

# Assumindo a mesma estrutura
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

dags_bp = Blueprint('dags', __name__)

def add_history_event(evento, detalhes):
    from ..models import SyncHistory
    SyncHistory.log_event(evento, detalhes)

def fetch_mentions_from_dag_run(dag_id, dag_run_id, airflow_url, auth, cnpj_map=None):
    """Extrai as menções diretamente do DAG Run recém-concluído via XCom da API REST
    com fallback seguro para os logs daquela execução específica."""
    import requests
    import json
    import ast
    import hashlib
    import glob
    import os
    import re
    from datetime import datetime, timezone, timedelta
    from ..services.mention_service import clean_abstract_for_dashboard, normalize_cnpj
    from ..models import Company

    extracted_mentions = []
    seen_ids = set()

    if cnpj_map is None:
        companies = Company.query.with_entities(Company.cnpj_norm, Company.nome, Company.cnpj).all()
        cnpj_map = {c.cnpj_norm: c.nome for c in companies if c.cnpj_norm}
        cnpj_map.update({c.cnpj: c.nome for c in companies if c.cnpj})

    results_raw_list = []

    # 1. Tentar obter via Airflow REST API XCom
    if dag_run_id:
        try:
            ti_url = f"{airflow_url}/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances"
            res_ti = requests.get(ti_url, auth=auth, timeout=10)
            if res_ti.status_code == 200:
                task_instances = res_ti.json().get('task_instances', [])
                search_tasks = [
                    ti['task_id'] for ti in task_instances 
                    if 'exec_search' in ti.get('task_id', '') and ti.get('state') == 'success'
                ]
                for tid in search_tasks:
                    xcom_url = f"{airflow_url}/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{tid}/xcomEntries/return_value"
                    res_xc = requests.get(xcom_url, auth=auth, timeout=10)
                    if res_xc.status_code == 200:
                        xc_val = res_xc.json().get('value')
                        if isinstance(xc_val, str):
                            try:
                                xc_val = json.loads(xc_val)
                            except Exception:
                                try:
                                    xc_val = ast.literal_eval(xc_val)
                                except Exception:
                                    pass
                        if isinstance(xc_val, dict):
                            res_dict = xc_val.get('result', xc_val)
                            if isinstance(res_dict, dict):
                                results_raw_list.append(res_dict)
        except Exception:
            pass

    # 2. Fallback: Ler apenas os logs daquele dag_run_id específico
    if not results_raw_list and dag_run_id:
        try:
            from ..services.mention_service import LOGS_DIR
            run_log_pattern = os.path.join(LOGS_DIR, f"dag_id={dag_id}", f"run_id={dag_run_id}", "task_id=exec_searchs.exec_search_*", "attempt=*.log")
            specific_logs = glob.glob(run_log_pattern)
            if not specific_logs:
                alt_pattern = os.path.join(LOGS_DIR, f"dag_id={dag_id}", f"run_id={dag_run_id}", "task_id=exec_search_*", "attempt=*.log")
                specific_logs = glob.glob(alt_pattern)

            for log_path in specific_logs:
                try:
                    with open(log_path, 'rb') as f:
                        content = f.read().decode('utf-8', errors='ignore')
                    if 'Done. Returned value was:' in content:
                        part = content.split('Done. Returned value was:', 1)[1].strip()
                        dict_match = re.search(r'^(\{.*?\})\s*(?=\n\[\d{4}-\d{2}-\d{2}|\Z)', part, re.DOTALL)
                        if dict_match:
                            res_dict = ast.literal_eval(dict_match.group(1)).get('result', {})
                            if isinstance(res_dict, dict):
                                results_raw_list.append(res_dict)
                except Exception:
                    continue
        except Exception:
            pass

    # 3. Processar e estruturar as menções
    now_str = datetime.now(timezone(timedelta(hours=-3))).strftime('%Y-%m-%d %H:%M:%S')
    for raw_result in results_raw_list:
        group_list = []
        if 'single_group' in raw_result and isinstance(raw_result['single_group'], dict):
            group_list.append(raw_result['single_group'])
        else:
            for g_key, g_val in raw_result.items():
                if isinstance(g_val, dict):
                    group_list.append(g_val)
        if not group_list and raw_result:
            group_list.append(raw_result)

        for results in group_list:
            for cnpj_raw_key, content_group in results.items():
                if not isinstance(content_group, dict):
                    continue
                cnpjs = [c.strip() for c in cnpj_raw_key.split(',')]
                for cnpj_log in cnpjs:
                    cnpj_norm = normalize_cnpj(cnpj_log)
                    for dept_name, depts in content_group.items():
                        if not isinstance(depts, list):
                            continue
                        for pub in depts:
                            if not isinstance(pub, dict):
                                continue
                            raw_abstract = pub.get('abstract', '')
                            raw_date = pub.get('date', '')
                            hash_str = f"{cnpj_norm}_{raw_date}_{raw_abstract}"
                            fallback_id = hashlib.md5(hash_str.encode('utf-8', errors='ignore')).hexdigest()
                            pub_id = pub.get('id') or fallback_id
                            unique_key = f"{cnpj_norm}_{pub_id}"

                            if unique_key in seen_ids:
                                continue
                            seen_ids.add(unique_key)

                            empresa_nome = cnpj_map.get(cnpj_norm) or cnpj_map.get(cnpj_log) or cnpj_log
                            formatted_trecho = clean_abstract_for_dashboard(raw_abstract, cnpj_norm)

                            extracted_mentions.append({
                                "id": unique_key,
                                "empresa": empresa_nome,
                                "cnpj": cnpj_log,
                                "cnpj_norm": cnpj_norm,
                                "secao": pub.get('section', 'DOU'),
                                "data": pub.get('date', 'N/A'),
                                "detected_at": now_str,
                                "trecho": formatted_trecho,
                                "link": pub.get('href', '#')
                            })

    return extracted_mentions

@dags_bp.route('/routines', methods=['GET', 'POST'])
@login_required
def manage_routines():
    if request.method == 'GET':
        return jsonify(get_routines())
    
    if session['user']['role'] != 'master': return jsonify({"status": "error"}), 403
    data = request.json
    
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"status": "error", "message": "Nome da rotina é obrigatório."}), 400
    
    terms = data.get('terms', [])
    if not terms or len(terms) == 0:
        return jsonify({"status": "error", "message": "Adicione pelo menos um termo de busca."}), 400
    
    sections = data.get('sections', [])
    if not sections or len(sections) == 0:
        return jsonify({"status": "error", "message": "Selecione pelo menos uma seção do DOU."}), 400
    
    emails = data.get('emails', [])
    if not emails or len(emails) == 0:
        return jsonify({"status": "error", "message": "Adicione pelo menos um e-mail de destino."}), 400
    
    filename = data.get('file')
    if not filename:
        new_id = re.sub(r'\W+', '_', data['name'].lower())
        filename = f"{new_id}.yaml"
        
    file_path = os.path.join(BASE_DIR, "dag_confs", filename)
    
    existing_data = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                existing_data = yaml.safe_load(f)
        except: pass

    new_dag = existing_data or {"dag": {}}
    dag = new_dag["dag"]
    
    dag["id"] = dag.get("id") or re.sub(r'\.[^.]*$', '', filename)
    dag["description"] = data.get('description', dag.get('description', ''))
    dag["schedule"] = data.get('schedule', dag.get('schedule', '0 5 * * *'))
    dag["tags"] = dag.get("tags", ["custom"])
    
    source_input = data.get('source', 'INLABS')
    if source_input == 'INLABS':
        if "inlabs" not in dag["tags"]:
            dag["tags"].append("inlabs")
        dag["dataset"] = "inlabs"
    else:
        if "dataset" in dag:
            del dag["dataset"]
        if "inlabs" in dag["tags"]:
            dag["tags"].remove("inlabs")
            
    dag["owner"] = dag.get("owner", ["admin"])
    
    search = dag.get("search", {})
    if isinstance(search, list): 
        search = search[0] if len(search) > 0 else {}
    
    search["header"] = data.get('name', search.get('header', 'Busca'))
    search["department"] = data.get('organs', search.get('department', []))
    search["organs"] = data.get('organs', search.get('organs', []))
    
    class QuotedString(str): pass
    def quoted_scalar_representer(dumper, data):
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style="'")
    yaml.SafeDumper.add_representer(QuotedString, quoted_scalar_representer)
    
    if filename != "Pesquisa_cnpj.yaml":
        raw_terms = data.get('terms', search.get('terms', []))
        search["terms"] = [QuotedString(t) for t in raw_terms]
    
    search["dou_sections"] = data.get('sections', search.get('dou_sections', ["SECAO_1", "SECAO_2", "SECAO_3"]))
    search["field"] = search.get("field", "TUDO")
    search["is_exact_search"] = data.get('is_exact_search', True)
    search["force_rematch"] = data.get('force_rematch', True)
    search["terms_ignore"] = data.get('terms_ignore', [])
    search["full_text"] = search.get("full_text", True)
    search["date"] = search.get("date", "DIA")
    
    if source_input == 'INLABS':
        search["sources"] = ["INLABS"]
    else:
        if "sources" in search:
            del search["sources"]
            
    dag["search"] = [search]
    
    report = dag.get("report", {})
    report["title"] = data.get('name', report.get('title', 'Alerta'))
    report["emails"] = data.get('emails', report.get('emails', []))
    report["subject"] = data.get('subject', report.get('subject', ''))
    
    if 'active' in data:
        dag["active"] = bool(data['active'])
        dag["is_paused"] = not bool(data['active'])
        from ..services.airflow_service import toggle_airflow_dag
        toggle_airflow_dag(dag.get("id"), is_paused=dag["is_paused"])
        
    dag["report"] = report
    
    tmp_path = file_path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(new_dag, f, allow_unicode=True, sort_keys=False)
    os.replace(tmp_path, file_path)
    
    if filename == "Pesquisa_cnpj.yaml":
        from ..models import db, Settings
        from ..services.dag_config_service import rebuild_yaml_from_db
        s_rec = Settings.query.filter_by(key='main_dag_settings').first()
        if not s_rec:
            s_rec = Settings(key='main_dag_settings')
            db.session.add(s_rec)
        s_rec.set_value({
            "emails": emails,
            "subject": report.get("subject", ""),
            "schedule": dag.get("schedule", "0 8 * * MON-FRI"),
            "active": dag.get("active", True)
        })
        db.session.commit()
        rebuild_yaml_from_db()
    
    return jsonify({"status": "success", "message": "Rotina salva com sucesso!"})

@dags_bp.route('/system/main_dag_status', methods=['GET'])
@dags_bp.route('/system/integrations_status', methods=['GET'])
@login_required
def api_integrations_status():
    """Retorna o diagnóstico completo de todas as integrações e pendências do sistema para o assistente/alerta."""
    from ..services.dag_config_service import get_main_dag_info
    from ..models import Settings
    
    # 1. Rotina Principal (Main DAG)
    main_info = get_main_dag_info()
    main_dag_configured = bool(main_info.get("is_configured", False))
    
    # 2. Global Settings (SMTP, Google Sheets, INLABS)
    settings_record = Settings.query.filter_by(key='global_settings').first()
    settings_data = settings_record.get_value() if settings_record else {}
    
    # SMTP
    smtp_data = settings_data.get('smtp', {})
    smtp_configured = bool(str(smtp_data.get('server') or '').strip() and str(smtp_data.get('user') or '').strip())
    
    # Google Sheets
    sheets_data = settings_data.get('google_sheets', {})
    has_creds = bool(str(sheets_data.get('credentials_json') or '').strip())
    has_sheet = bool(str(sheets_data.get('spreadsheet_url') or sheets_data.get('spreadsheet_id') or sheets_data.get('sheet_url') or '').strip())
    sheets_configured = has_creds and has_sheet
    
    # INLABS
    inlabs_data = settings_data.get('inlabs', {})
    inlabs_configured = bool(str(inlabs_data.get('user') or '').strip() and str(inlabs_data.get('password') or '').strip())
    
    integrations = [
        {
            "id": "main_dag",
            "name": "Rotina Principal",
            "title": "E-mails da Rotina Principal",
            "description": "Defina os e-mails de destino e o assunto para receber o relatório diário de publicações.",
            "is_configured": main_dag_configured,
            "action_type": "modal_main_dag",
            "icon": "calendar-clock",
            "missing_fields": main_info.get("missing_fields", [])
        },
        {
            "id": "smtp",
            "name": "Servidor SMTP",
            "title": "Servidor de Envio (SMTP)",
            "description": "Configure o servidor de e-mail (Host, Porta, Usuário e Senha) para disparo automático.",
            "is_configured": smtp_configured,
            "action_type": "modal_smtp",
            "icon": "mail",
            "missing_fields": [f for f in ["server", "user"] if not str(smtp_data.get(f) or '').strip()]
        },
        {
            "id": "google_sheets",
            "name": "Google Sheets",
            "title": "Planilha Google Sheets",
            "description": "Conecte a planilha com credenciais de serviço para sincronização automática de empresas.",
            "is_configured": sheets_configured,
            "action_type": "tab_sheets",
            "icon": "file-spreadsheet",
            "missing_fields": ([ "credentials_json" ] if not has_creds else []) + ([ "spreadsheet_url" ] if not has_sheet else [])
        },
        {
            "id": "inlabs",
            "name": "Acesso INLABS",
            "title": "Credenciais INLABS",
            "description": "Informe usuário e senha do portal INLABS (Imprensa Nacional) para download do DOU.",
            "is_configured": inlabs_configured,
            "action_type": "tab_inlabs",
            "icon": "newspaper",
            "missing_fields": [f for f in ["user", "password"] if not str(inlabs_data.get(f) or '').strip()]
        }
    ]
    
    pending = [i for i in integrations if not i["is_configured"]]
    
    missing_all = []
    for i in pending:
        missing_all.append(i["id"])
        
    main_dag_is_configured = bool(main_dag_configured and smtp_configured)
    
    return jsonify({
        "status": "ok",
        "is_configured": main_dag_is_configured,
        "all_configured": len(pending) == 0,
        "pending_count": len(pending),
        "next_pending": pending[0] if pending else None,
        "integrations": integrations,
        "missing_fields": missing_all,
        "main_dag": main_info,
        "smtp_configured": smtp_configured,
        "smtp": {
            "server": smtp_data.get("server", ""),
            "port": smtp_data.get("port", "587"),
            "user": smtp_data.get("user", ""),
            "from_email": smtp_data.get("from_email", ""),
            "has_password": bool(smtp_data.get("password"))
        }
    })

@dags_bp.route('/system/configure_main_dag', methods=['POST'])
@login_required
def api_configure_main_dag():
    """Configura atomicamente os e-mails, assunto, agendamento da DAG principal e servidor SMTP."""
    if session['user']['role'] != 'master':
        return jsonify({"status": "error", "message": "Apenas administradores podem configurar a rotina principal."}), 403
        
    data = request.json or {}
    
    # Valida e-mails
    raw_emails = data.get('emails', [])
    if isinstance(raw_emails, str):
        emails = [e.strip() for e in raw_emails.replace('\n', ',').split(',') if e.strip()]
    elif isinstance(raw_emails, list):
        emails = [str(e).strip() for e in raw_emails if str(e).strip()]
    else:
        emails = []
        
    if not emails:
        return jsonify({"status": "error", "message": "Pelo menos um e-mail de destino é obrigatório para a rotina principal."}), 400
        
    # Valida formato dos e-mails
    email_regex = re.compile(r'^[\w\.-]+@[\w\.-]+\.\w+$')
    for em in emails:
        if not email_regex.match(em):
            return jsonify({"status": "error", "message": f"E-mail inválido: {em}"}), 400
            
    subject = str(data.get('subject') or '').strip()
    if not subject:
        subject = "[Registrale] Relatório Diário de Publicações do DOU"
        
    schedule = str(data.get('schedule') or '0 8 * * MON-FRI').strip()
    active = bool(data.get('active', True))
    
    # 1. Salva configurações no SQLite (persistente no volume /data)
    from ..models import db, Settings
    s_rec = Settings.query.filter_by(key='main_dag_settings').first()
    if not s_rec:
        s_rec = Settings(key='main_dag_settings')
        db.session.add(s_rec)
    s_rec.set_value({
        "emails": emails,
        "subject": subject,
        "schedule": schedule,
        "active": active
    })
    db.session.commit()
    
    # 2. Atualiza Pesquisa_cnpj.yaml e reconstrói blocos
    from ..services.dag_config_service import get_base_yaml_path, get_dag_confs_path, rebuild_yaml_from_db
    dag_confs_path = get_dag_confs_path()
    file_path = os.path.join(dag_confs_path, "Pesquisa_cnpj.yaml")
    
    existing_data = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                existing_data = yaml.safe_load(f) or {}
        except:
            pass
            
    dag = existing_data.get('dag', {})
    dag["id"] = "pesquisa_cnpj_anvisa"
    dag["description"] = "Busca padrão diária vinculada às empresas com monitoramento ativo na base."
    dag["tags"] = ["pesquisa_cnpj", "inlabs"]
    dag["owner"] = ["CNPJ_SYNC"]
    dag["schedule"] = schedule
    dag["dataset"] = "inlabs"
    dag["active"] = active
    dag["is_paused"] = not active
    
    report = dag.get('report', {})
    report["title"] = "MONITORAMENTO PADRÃO"
    report["subject"] = subject
    report["skip_null"] = True
    report["emails"] = emails
    dag["report"] = report
    
    existing_data["dag"] = dag
    
    tmp_path = file_path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(existing_data, f, allow_unicode=True, sort_keys=False)
    os.replace(tmp_path, file_path)
    
    # Reconstrói para preservar os CNPJs ativos e blocos particionados
    rebuild_yaml_from_db()
    
    # 2. Configurar SMTP se fornecido
    if 'smtp' in data and isinstance(data['smtp'], dict):
        smtp = data['smtp']
        server = str(smtp.get('server') or '').strip()
        user = str(smtp.get('user') or '').strip()
        
        if server and user:
            from ..models import db, Settings
            from dotenv import set_key
            
            settings_record = Settings.query.filter_by(key='global_settings').first()
            if not settings_record:
                settings_record = Settings(key='global_settings')
                db.session.add(settings_record)
            current_val = settings_record.get_value() or {}
            if not isinstance(current_val, dict):
                current_val = {}
            
            port = str(smtp.get('port') or '587').strip()
            raw_password = str(smtp.get('password') or '').strip()
            # Se não enviou senha nova, preserva a senha anterior
            if not raw_password and current_val.get('smtp', {}).get('password'):
                raw_password = current_val.get('smtp', {}).get('password')
            if 'gmail.com' in server.lower():
                raw_password = raw_password.replace(' ', '')
            from_email = str(smtp.get('from_email') or user).strip()
            
            current_val['smtp'] = {
                "server": server,
                "port": port,
                "user": user,
                "password": raw_password,
                "from_email": from_email
            }
            settings_record.set_value(current_val)
            db.session.commit()
            
            DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data'))
            env_path = os.path.join(DATA_DIR, '.env')
            if not os.path.exists(env_path): open(env_path, 'a').close()
            
            smtp_mappings = {
                "AIRFLOW__SMTP__SMTP_HOST": server,
                "AIRFLOW__SMTP__SMTP_PORT": port,
                "AIRFLOW__SMTP__SMTP_USER": user,
                "AIRFLOW__SMTP__SMTP_PASSWORD": raw_password,
                "AIRFLOW__SMTP__SMTP_MAIL_FROM": from_email
            }
            for env_var, val in smtp_mappings.items():
                if val:
                    set_key(env_path, env_var, str(val))
                    os.environ[env_var] = str(val)
            if port in ('587', '25'):
                set_key(env_path, "AIRFLOW__SMTP__SMTP_STARTTLS", "true")
                os.environ["AIRFLOW__SMTP__SMTP_STARTTLS"] = "true"
            elif port == '465':
                set_key(env_path, "AIRFLOW__SMTP__SMTP_SSL", "true")
                os.environ["AIRFLOW__SMTP__SMTP_SSL"] = "true"
                
            # Sincronizar conexão smtp_default no Airflow
            try:
                import requests
                import json
                airflow_url = os.getenv('AIRFLOW_URL', 'http://airflow-webserver:8080')
                auth = ("airflow", "airflow")
                
                conn_payload = {
                    "connection_id": "smtp_default",
                    "conn_type": "smtp",
                    "host": server,
                    "login": user,
                    "password": raw_password,
                    "port": int(port) if port.isdigit() else 587,
                    "extra": json.dumps({"from_email": from_email, "disable_tls": False})
                }
                
                res = requests.get(f"{airflow_url}/api/v1/connections/smtp_default", auth=auth, timeout=5)
                if res.status_code == 200:
                    requests.patch(
                        f"{airflow_url}/api/v1/connections/smtp_default?update_mask=host,login,password,port,extra",
                        json=conn_payload,
                        auth=auth,
                        timeout=5
                    )
                else:
                    requests.post(f"{airflow_url}/api/v1/connections", json=conn_payload, auth=auth, timeout=5)
            except Exception as e:
                import logging
                logging.error(f"Falha ao atualizar conexão smtp_default no Airflow via assistente: {e}")
                
    return jsonify({
        "status": "success",
        "message": "Configurações da rotina principal atualizadas com sucesso!",
        "main_dag": {
            "emails": emails,
            "subject": subject,
            "schedule": schedule,
            "active": active
        }
    })

@dags_bp.route('/routines/toggle/<path:file>', methods=['POST'])
@login_required
def toggle_routine_route(file):
    """Ativa ou desativa uma rotina de busca no YAML e no Airflow."""
    if session['user']['role'] != 'master':
        return jsonify({"status": "error", "message": "Acesso negado."}), 403
        
    data = request.get_json(silent=True) or {}
    dag_confs_path = get_dag_confs_path()
    file_path = os.path.join(dag_confs_path, file)
    
    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "Arquivo de rotina não encontrado."}), 404
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            yaml_data = yaml.safe_load(f) or {}
            
        dag = yaml_data.get('dag', {})
        dag_id = dag.get('id') or re.sub(r'\.[^.]*$', '', file)
        
        # Inverte ou define conforme passado
        current_active = dag.get('active', not dag.get('is_paused', False))
        new_active = data.get('active', not current_active)
        
        dag['active'] = bool(new_active)
        dag['is_paused'] = not bool(new_active)
        yaml_data['dag'] = dag
        
        tmp_path = file_path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(yaml_data, f, allow_unicode=True, sort_keys=False)
        os.replace(tmp_path, file_path)
        
        from ..services.airflow_service import toggle_airflow_dag
        toggle_airflow_dag(dag_id, is_paused=not new_active)
        
        # Se for Pesquisa_cnpj.yaml, propaga também para partes particionadas
        if file == "Pesquisa_cnpj.yaml":
            parts = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_sync.yaml")) + \
                    glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_part_*.yaml"))
            for p in parts:
                try:
                    with open(p, 'r', encoding='utf-8') as pf:
                        pdata = yaml.safe_load(pf) or {}
                    pdag = pdata.get('dag', {})
                    pdag_id = pdag.get('id')
                    pdag['active'] = bool(new_active)
                    pdag['is_paused'] = not bool(new_active)
                    pdata['dag'] = pdag
                    ptmp = p + '.tmp'
                    with open(ptmp, 'w', encoding='utf-8') as pf:
                        yaml.safe_dump(pdata, pf, allow_unicode=True, sort_keys=False)
                    os.replace(ptmp, p)
                    if pdag_id:
                        toggle_airflow_dag(pdag_id, is_paused=not new_active)
                except Exception as part_err:
                    pass
        
        action_str = "ativada" if new_active else "desativada"
        add_history_event(
            f"Rotina {'Ativada' if new_active else 'Desativada'}",
            f"A rotina {dag.get('id', file)} foi {action_str} com sucesso."
        )
        
        return jsonify({
            "status": "success",
            "active": new_active,
            "message": f"Rotina {action_str} com sucesso!"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao alternar status: {str(e)}"}), 500


@dags_bp.route('/routines/<path:file>', methods=['DELETE'])
@login_required
def delete_routine(file):
    if session['user']['role'] != 'master': return jsonify({"status": "error", "message": "Acesso negado."}), 403
    
    if file == "Pesquisa_cnpj.yaml" or "_part_" in file or "_sync" in file or "gestaoclick" in file.lower():
        return jsonify({"status": "error", "message": "Não é possível excluir rotinas de sistema (Sync / GestãoClick)."}), 400
        
    dag_confs_path = get_dag_confs_path()
    file_path = os.path.join(dag_confs_path, file)
    if os.path.exists(file_path):
        try:
            # Tentar extrair dag_id
            dag_id = os.path.splitext(file)[0]
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    ydata = yaml.safe_load(f)
                    if isinstance(ydata, dict) and 'dag' in ydata:
                        dag_id = ydata['dag'].get('id', dag_id)
            except Exception:
                pass

            os.remove(file_path)

            # Desregistrar do Airflow se aplicável
            try:
                from ..services.airflow_service import get_airflow_auth, get_airflow_url
                auth = get_airflow_auth()
                airflow_url = get_airflow_url()
                requests.delete(f"{airflow_url}/api/v1/dags/{dag_id}", auth=auth, timeout=5)
            except Exception:
                pass

            try:
                generator_path = os.path.join(BASE_DIR, "src", "dou_dag_generator.py")
                if os.path.exists(generator_path):
                    os.utime(generator_path, None)
            except Exception:
                pass

            add_history_event("Rotina Excluída", f"Rotina {file} removida do sistema.")
            return jsonify({"status": "success", "message": "Rotina excluída com sucesso!"})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Erro ao excluir o arquivo: {str(e)}"}), 500
    
    return jsonify({"status": "error", "message": "Arquivo não encontrado."}), 404


@dags_bp.route('/routines/cleanup_temp', methods=['POST'])
@login_required
def cleanup_temp_dags_route():
    """Endpoint para forçar a limpeza imediata de arquivos e DAGs temporárias do disco e do Airflow."""
    try:
        from ..services.dag_config_service import cleanup_orphaned_temp_dags
        cleaned = cleanup_orphaned_temp_dags(max_age_seconds=0, force_all=True)
        return jsonify({
            "status": "success",
            "message": f"{cleaned} DAG(s) e arquivo(s) temporário(s) removido(s) com sucesso.",
            "cleaned_count": cleaned
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@dags_bp.route('/routines/trigger/<path:file>', methods=['POST'])
@login_required
def trigger_routine(file):
    req_data = request.get_json(silent=True) or {}
    logical_date = req_data.get('logical_date')
    
    if logical_date:
        try:
            datetime.strptime(logical_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"status": "error", "message": "Data inválida. Use o formato AAAA-MM-DD."}), 400

    dag_confs_path = get_dag_confs_path()
    
    # ----------------------------------------------------
    # Lógica de verificação e leitura da rotina
    # ----------------------------------------------------
    is_inlabs = False
    dag_id_to_trigger = None
    routine_emails = []
    routine_subject = None
    routine_title = file
    routine_cnpjs = set()

    file_path = os.path.join(dag_confs_path, file)
    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "Arquivo de rotina não encontrado."}), 404

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            yaml_check = yaml.safe_load(f) or {}
            
            # Bloqueio de rotina pausada
            is_active = yaml_check.get('dag', {}).get('active')
            if is_active is None:
                is_active = yaml_check.get('active', True)
            if is_active is False:
                return jsonify({"status": "error", "message": "Esta rotina está pausada. Ative-a antes de disparar pesquisas."}), 400
                
            dag_data = yaml_check.get('dag', {})
            dag_id_to_trigger = dag_data.get('id')
            if not dag_id_to_trigger and file != "Pesquisa_cnpj.yaml":
                dag_id_to_trigger = re.sub(r'\.[^.]*$', '', file)
                
            report_data = dag_data.get('report', {})
            routine_emails = report_data.get('emails', [])
            if isinstance(routine_emails, str): routine_emails = [routine_emails]
            routine_subject = report_data.get('subject')
            routine_title = report_data.get('title') or file
            
            search_entries = dag_data.get('search', [])
            if isinstance(search_entries, dict): search_entries = [search_entries]
            for s_item in search_entries:
                sources = s_item.get('sources', ['DOU'])
                if 'INLABS' in sources:
                    is_inlabs = True
                for t in s_item.get('terms', []):
                    clean_t = re.sub(r'[^A-Za-z0-9]', '', str(t)).upper()
                    if clean_t:
                        routine_cnpjs.add(clean_t)
    except Exception: pass

    def watch_dag_and_update_mentions(app_context, runs_to_watch, routine_name, routine_emails=None, routine_subject=None, logical_date=None, target_terms=None, trigger_time_str=None):
        import time
        import requests
        import logging
        from datetime import datetime, timezone, timedelta
        from ..services.mention_service import clear_mentions_cache, get_mentions_kpis, get_real_mentions
        from ..services.email_service import EmailSender, build_mentions_email_html
        from ..models import db, Settings, Mention, Company
        
        airflow_url = os.getenv('AIRFLOW_URL', 'http://airflow-webserver:8080')
        auth = ("airflow", "airflow")
        
        time.sleep(3)
        max_wait = 1800  # 30 min
        start = time.time()
        
        # Garante lista estruturada de itens a monitorar
        normalized_runs = []
        for r in runs_to_watch:
            if isinstance(r, dict):
                normalized_runs.append(r)
            else:
                normalized_runs.append({"dag_id": str(r), "dag_run_id": None})
        
        # 1. Aguarda conclusão de todos os DAG runs disparados
        while (time.time() - start) < max_wait:
            all_done = True
            for item in normalized_runs:
                did = item.get('dag_id')
                run_id = item.get('dag_run_id')
                
                try:
                    if run_id:
                        url = f"{airflow_url}/api/v1/dags/{did}/dagRuns/{run_id}"
                        res = requests.get(url, auth=auth, timeout=5)
                        if res.status_code == 200:
                            st = res.json().get('state')
                            if st in ('running', 'queued') or not st:
                                all_done = False
                                break
                        else:
                            all_done = False
                            break
                    else:
                        url = f"{airflow_url}/api/v1/dags/{did}/dagRuns?order_by=-execution_date&limit=10"
                        res = requests.get(url, auth=auth, timeout=5)
                        if res.status_code == 200:
                            runs = res.json().get('dag_runs', [])
                            active = [run for run in runs if run.get('state') in ('running', 'queued')]
                            if active:
                                all_done = False
                                break
                except Exception:
                    all_done = False
                    break
            
            if all_done:
                break
            time.sleep(3)
            
        time.sleep(2)
        with app_context:
            try:
                # 2. Formatar data de referência
                if logical_date:
                    try:
                        target_date_str = datetime.strptime(str(logical_date).strip(), '%Y-%m-%d').strftime('%d/%m/%Y')
                    except Exception:
                        try:
                            target_date_str = datetime.strptime(str(logical_date).strip(), '%d/%m/%Y').strftime('%d/%m/%Y')
                        except Exception:
                            target_date_str = str(logical_date)
                else:
                    target_date_str = datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y')

                # 3. Extrair menções diretamente dos DAG Runs concluídos (Ultrarrápido: ~0.05s)
                direct_mentions = []
                companies = Company.query.with_entities(Company.cnpj_norm, Company.nome, Company.cnpj).all()
                cnpj_map = {c.cnpj_norm: c.nome for c in companies if c.cnpj_norm}
                cnpj_map.update({c.cnpj: c.nome for c in companies if c.cnpj})

                for item in normalized_runs:
                    did = item.get('dag_id')
                    run_id = item.get('dag_run_id')
                    if did:
                        run_res = fetch_mentions_from_dag_run(did, run_id, airflow_url, auth, cnpj_map=cnpj_map)
                        direct_mentions.extend(run_res)

                # Se obteve menções diretas, insere/atualiza no banco SQLite para o Dashboard
                if direct_mentions:
                    for m in direct_mentions:
                        existing = db.session.get(Mention, m['id'])
                        if not existing:
                            db.session.add(Mention(**m))
                        else:
                            existing.empresa = m.get('empresa', existing.empresa)
                            existing.secao = m.get('secao', existing.secao)
                            existing.data = m.get('data', existing.data)
                            existing.detected_at = m.get('detected_at', existing.detected_at)
                            existing.trecho = m.get('trecho', existing.trecho)
                            existing.link = m.get('link', existing.link)
                    db.session.commit()
                    clear_mentions_cache()
                    relevant_mentions = direct_mentions
                else:
                    clear_mentions_cache()
                    relevant_mentions = []

                # Filtragem opcional de termos para rotinas com termos específicos
                if target_terms and routine_name != "Pesquisa_cnpj.yaml":
                    relevant_mentions = [
                        m for m in relevant_mentions 
                        if (m.get('cnpj_norm') in target_terms) or (m.get('cnpj') in target_terms)
                    ]

                total, hoje, mes = get_mentions_kpis()

                # 4. Destinatários de E-mail
                emails = list(routine_emails or [])
                if not emails:
                    settings_record = Settings.query.filter_by(key='global_settings').first()
                    if settings_record:
                        smtp_data = settings_record.get_value().get('smtp', {})
                        smtp_from = smtp_data.get('from_email') or smtp_data.get('user', '')
                        if smtp_from:
                            emails = [smtp_from]
                emails = [e.strip() for e in emails if e and str(e).strip()]

                logging.info(f"[Watcher {routine_name}] relevant_mentions={len(relevant_mentions)}, emails={emails}")

                # 5. Envio do E-mail Formatado
                email_sent = False
                if emails and relevant_mentions:
                    subject = routine_subject or f"Registrale - Alerta DOU ({routine_name}) - {target_date_str}"
                    html = build_mentions_email_html(
                        relevant_mentions,
                        template_name='Padrão Registrale',
                        title=routine_subject or f"Notificação DOU: {routine_name}",
                        subtitle=f"Foram identificadas {len(relevant_mentions)} publicações no Diário Oficial da União para a data {target_date_str}:"
                    )
                    try:
                        sender = EmailSender(None)
                        sender.send_custom_email(
                            to_emails=emails,
                            subject=subject,
                            html_content=html
                        )
                        email_sent = True
                        add_history_event("E-mail Enviado", f"Alerta {routine_name} enviado para {', '.join(emails)} ({len(relevant_mentions)} menções).")
                    except Exception as e_mail:
                        logging.error(f"Erro ao enviar e-mail da rotina {routine_name}: {e_mail}")
                        add_history_event("Erro Envio E-mail", f"Falha ao enviar e-mail da rotina {routine_name}: {str(e_mail)}")

                if not email_sent:
                    motivo = []
                    if not emails:
                        motivo.append("nenhum destinatário configurado")
                    if not relevant_mentions:
                        motivo.append(f"0 menções encontradas para {target_date_str}")
                    motivo_str = f" ({'; '.join(motivo)})" if motivo else ""
                    add_history_event("Busca Concluída", f"Rotina {routine_name} concluída{motivo_str}. Total no painel: {total} ({hoje} hoje).")

            except Exception as e:
                import logging
                logging.error(f"Erro ao atualizar menções pós-busca: {e}")

    # ----------------------------------------------------
    # SE FOR ROTINA INLABS COM DATA ESPECÍFICA (EX: 2026-08-15)
    # ----------------------------------------------------
    if is_inlabs and logical_date:
        from ..services.inlabs_service import is_date_loaded, record_inlabs_download_success, enforce_inlabs_retention_limit
        from ..services.holiday_service import is_within_inlabs_retention_window
        from ..services.airflow_service import wait_for_specific_dag_runs, wait_for_dag_discovery

        already_loaded, articles_found = is_date_loaded(logical_date)
        app_ctx = current_app._get_current_object().app_context()

        if already_loaded:
            add_history_event("Busca Iniciada", f"Dados de {logical_date} já disponíveis ({articles_found} artigos). Disparando pesquisa na rotina {file}...")
            ok, msg, run_info = trigger_airflow_dag(dag_id_to_trigger, logical_date)
            threading.Thread(
                target=watch_dag_and_update_mentions,
                args=(
                    app_ctx, 
                    [run_info], 
                    file, 
                    routine_emails, 
                    routine_subject, 
                    logical_date, 
                    routine_cnpjs,
                    run_info.get("trigger_time") if isinstance(run_info, dict) else None
                ),
                daemon=True
            ).start()
            return jsonify({"status": "success", "message": f"Dados já disponíveis no banco. Pesquisa iniciada com sucesso para {logical_date}!"})

        # Se for anterior à janela de 120 dias do portal INLABS, executa diretamente via API DOU
        if not is_within_inlabs_retention_window(logical_date, 120):
            def run_adhoc_dou_search(app_context_obj, source_file, target_date, r_emails, r_subject, r_terms):
                temp_yaml_path = None
                temp_dag_id = None
                with app_context_obj:
                    try:
                        routine_path = os.path.join(dag_confs_path, source_file)
                        with open(routine_path, 'r', encoding='utf-8') as f:
                            base_yaml = yaml.safe_load(f) or {}

                        original_searches = base_yaml.get('dag', {}).get('search', [])
                        if not isinstance(original_searches, list):
                            original_searches = [original_searches] if original_searches else []

                        temp_search_blocks = []
                        for block in original_searches:
                            temp_block = {
                                "header": block.get("header", f"Busca API-DOU {source_file}"),
                                "is_exact_search": block.get("is_exact_search", True),
                                "force_rematch": True,
                                "terms": block.get("terms", []),
                                "dou_sections": block.get("dou_sections", ["SECAO_1", "SECAO_2", "SECAO_3"]),
                                "field": block.get("field", "TUDO"),
                                "full_text": block.get("full_text", True),
                                "date": "DIA",
                                "sources": ["DOU"],
                            }
                            if block.get("department"): temp_block["department"] = block["department"]
                            if block.get("organs"): temp_block["organs"] = block["organs"]
                            if block.get("terms_ignore"): temp_block["terms_ignore"] = block["terms_ignore"]
                            temp_search_blocks.append(temp_block)

                        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                        temp_dag_id = f"temp_adhoc_dou_{timestamp}"

                        temp_yaml = {
                            "dag": {
                                "id": temp_dag_id,
                                "description": f"Busca ad-hoc API-DOU para {target_date}",
                                "schedule": None,
                                "tags": ["temp", "api_dou", "adhoc"],
                                "search": temp_search_blocks,
                                "report": {
                                    "page_title": f"Busca API-DOU {target_date}",
                                    "emails": [],
                                    "subject": f"Registrale - API-DOU {target_date}"
                                }
                            }
                        }

                        temp_yaml_path = os.path.join(dag_confs_path, f"{temp_dag_id}.yaml")
                        with open(temp_yaml_path, 'w', encoding='utf-8') as f:
                            yaml.safe_dump(temp_yaml, f, allow_unicode=True, sort_keys=False)

                        import time
                        time.sleep(2)

                        wait_for_dag_discovery(temp_dag_id, max_wait=120)

                        ok, msg, run_info = trigger_airflow_dag(temp_dag_id, target_date)
                        if ok:
                            watch_dag_and_update_mentions(
                                app_context_obj,
                                [run_info],
                                source_file,
                                r_emails,
                                r_subject,
                                target_date,
                                r_terms,
                                run_info.get("trigger_time") if isinstance(run_info, dict) else None
                            )
                    except Exception as e:
                        logging.error(f"Erro na busca ad-hoc API DOU para {target_date}: {e}")
                    finally:
                        from ..services.dag_config_service import cleanup_orphaned_temp_dags
                        if temp_yaml_path and os.path.exists(temp_yaml_path):
                            try:
                                os.remove(temp_yaml_path)
                            except Exception:
                                pass
                        if temp_dag_id:
                            try:
                                from ..services.airflow_service import get_airflow_auth, get_airflow_url
                                auth = get_airflow_auth()
                                airflow_url = get_airflow_url()
                                requests.delete(f"{airflow_url}/api/v1/dags/{temp_dag_id}", auth=auth, timeout=5)
                            except Exception:
                                pass
                            try:
                                import shutil
                                log_dir = os.path.join(BASE_DIR, "mnt", "airflow-logs", f"dag_id={temp_dag_id}")
                                if os.path.exists(log_dir):
                                    shutil.rmtree(log_dir, ignore_errors=True)
                            except Exception:
                                pass
                        try:
                            generator_path = os.path.join(BASE_DIR, "src", "dou_dag_generator.py")
                            if os.path.exists(generator_path):
                                os.utime(generator_path, None)
                        except Exception:
                            pass
                        try:
                            cleanup_orphaned_temp_dags(max_age_seconds=0, force_all=False)
                        except Exception:
                            pass

            add_history_event("Busca Individual (API DOU)", f"Data {logical_date} anterior a 120 dias (fora da retenção do INLABS). Disparando busca via API Oficial do DOU...")
            threading.Thread(
                target=run_adhoc_dou_search,
                args=(app_ctx, file, logical_date, routine_emails, routine_subject, routine_cnpjs),
                daemon=True
            ).start()
            return jsonify({"status": "success", "message": f"Data anterior a 120 dias. Busca iniciada diretamente via API Oficial do DOU!"})

        def run_inlabs_then_search(app_context_obj, target_dag_id, target_date, filename, r_emails, r_subject, r_terms):
            from ..services.airflow_service import trigger_airflow_dag, wait_for_specific_dag_runs
            from ..services.inlabs_service import record_inlabs_download_success, enforce_inlabs_retention_limit

            with app_context_obj:
                enforce_inlabs_retention_limit(max_days=120, protected_dates=[target_date])

            ok_inlabs, msg_inlabs, inlabs_run_info = trigger_airflow_dag("ro-dou_inlabs_load_pg", target_date)
            inlabs_run_id = inlabs_run_info.get("dag_run_id") if isinstance(inlabs_run_info, dict) else None
            
            if inlabs_run_id:
                wait_for_specific_dag_runs("ro-dou_inlabs_load_pg", [inlabs_run_id], max_wait=600)
                
            with app_context_obj:
                record_inlabs_download_success(target_date)
                add_history_event("Carga INLABS Concluída", f"Download concluído para {target_date}. Disparando agora a busca {filename}...")
                
            with app_context_obj:
                ok, msg, run_info = trigger_airflow_dag(target_dag_id, target_date)
                watch_dag_and_update_mentions(
                    app_context_obj, 
                    [run_info], 
                    filename, 
                    r_emails, 
                    r_subject, 
                    target_date, 
                    r_terms,
                    run_info.get("trigger_time") if isinstance(run_info, dict) else None
                )
        
        add_history_event("Carga INLABS", f"Iniciando download dos dados INLABS para {logical_date}...")
        threading.Thread(target=run_inlabs_then_search, args=(app_ctx, dag_id_to_trigger, logical_date, file, routine_emails, routine_subject, routine_cnpjs), daemon=True).start()
        return jsonify({"status": "success", "message": f"Download INLABS iniciado em background. A busca iniciará automaticamente logo após."})
    # ----------------------------------------------------

    if file == "Pesquisa_cnpj.yaml":
        parts = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_sync.yaml"))
        if not parts:
            parts = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_part_*.yaml"))
        if not parts:
            file_path = os.path.join(dag_confs_path, file)
            if not os.path.exists(file_path):
                return jsonify({"status": "error", "message": "Arquivo base não encontrado."}), 404
            parts = [file_path]
            
        success_count = 0
        triggered_runs = []
        errors = []
        for p in parts:
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    dag_id = data.get('dag', {}).get('id')
                    if dag_id:
                        ok, msg, run_info = trigger_airflow_dag(dag_id, logical_date)
                        if ok:
                            success_count += 1
                            triggered_runs.append(run_info)
                        else: errors.append(msg)
            except: continue
        
        if success_count > 0:
            add_history_event("Busca Iniciada", f"Rotina {file} ({success_count} parte(s)) disparada via Airflow. Data Lógica: {logical_date or 'Atual'}")
            app_ctx = current_app._get_current_object().app_context()
            first_trigger_time = triggered_runs[0].get("trigger_time") if triggered_runs else None
            threading.Thread(
                target=watch_dag_and_update_mentions, 
                args=(app_ctx, triggered_runs, file, routine_emails, routine_subject, logical_date, routine_cnpjs, first_trigger_time), 
                daemon=True
            ).start()
            return jsonify({"status": "success", "message": f"{success_count} parte(s) disparada(s)!"})
        else:
            return jsonify({"status": "error", "message": "Nenhuma parte pôde ser disparada.", "details": errors}), 500

    file_path = os.path.join(dag_confs_path, file)
    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "Arquivo de rotina não encontrado."}), 404
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            dag_id = data.get('dag', {}).get('id')
            if not dag_id: dag_id = re.sub(r'\.[^.]*$', '', file)
            
            ok, msg, run_info = trigger_airflow_dag(dag_id, logical_date)
            if ok:
                add_history_event("Busca Iniciada", f"Rotina {file} disparada via Airflow. Data Lógica: {logical_date or 'Atual'}")
                app_ctx = current_app._get_current_object().app_context()
                threading.Thread(
                    target=watch_dag_and_update_mentions, 
                    args=(app_ctx, [run_info], file, routine_emails, routine_subject, logical_date, routine_cnpjs, run_info.get("trigger_time")), 
                    daemon=True
                ).start()
                return jsonify({"status": "success", "message": f"Busca {dag_id} iniciada!"})
            else:
                add_history_event("Busca (Tentativa)", f"Tentativa de disparar {dag_id}: {msg}")
                return jsonify({"status": "warning", "message": "Busca solicitada, mas houve erro no Airflow.", "details": msg})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@dags_bp.route('/routines/check_date', methods=['GET'])
@login_required
def api_check_date():
    """Verifica se uma data específica já possui dados baixados no INLABS/PostgreSQL."""
    from sqlalchemy import create_engine, text
    from ..models import InlabsDownloadLog
    from ..services.holiday_service import is_business_day, is_within_inlabs_retention_window
    
    target_date = request.args.get('date', '').strip()
    if not target_date:
        return jsonify({"status": "error", "message": "Parâmetro date é obrigatório."}), 400
        
    if '/' in target_date:
        parts = target_date.split('/')
        if len(parts) == 3:
            target_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
    
    already_loaded = False
    articles_count = 0
    
    try:
        engine = create_engine('postgresql+pg8000://airflow:airflow@postgres:5432/inlabs')
        with engine.connect() as conn:
            conn.execute(text("SET statement_timeout = 5000"))
            res = conn.execute(
                text("SELECT COUNT(*) FROM dou_inlabs.article_raw WHERE CAST(pubdate AS DATE) = :dt"),
                {"dt": target_date}
            ).scalar()
            if res and int(res) > 0:
                already_loaded = True
                articles_count = int(res)
    except Exception:
        log = InlabsDownloadLog.query.filter_by(date_str=target_date, status='success').first()
        if log:
            already_loaded = True
            articles_count = 1
            
    is_bus = True
    holiday_reason = ""
    try:
        d_obj = datetime.strptime(target_date, '%Y-%m-%d').date()
        is_bus, holiday_reason = is_business_day(d_obj)
    except Exception:
        pass

    is_within_120 = is_within_inlabs_retention_window(target_date, 120)
            
    return jsonify({
        "status": "success",
        "date": target_date,
        "already_loaded": already_loaded,
        "articles_count": articles_count,
        "is_business_day": is_bus,
        "holiday_reason": holiday_reason,
        "is_within_120": is_within_120
    })

@dags_bp.route('/routines/monthly_inlabs_check', methods=['GET'])
@login_required
def api_monthly_inlabs_check():
    from ..services.holiday_service import get_business_days_for_month, is_within_inlabs_retention_window
    from ..services.inlabs_service import get_downloaded_dates
    
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    routine_file = request.args.get('routine', '')
    
    if not month or not year:
        return jsonify({"status": "error", "message": "Mês e ano são obrigatórios."}), 400
    
    # Checar se a rotina usa INLABS
    dag_confs_path = get_dag_confs_path()
    file_path = os.path.join(dag_confs_path, routine_file)
    uses_inlabs = False
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                yaml_data = yaml.safe_load(f)
                search = yaml_data.get('dag', {}).get('search', {})
                if isinstance(search, list): search = search[0] if search else {}
                sources = search.get('sources', ['DOU'])
                uses_inlabs = 'INLABS' in sources
        except: pass
    
    # Gerar dias úteis do mês descontando fins de semana e feriados nacionais (fixos e móveis)
    weekdays = get_business_days_for_month(year, month, cap_today=True)
    if not weekdays:
        return jsonify({
            "status": "ok",
            "scenario": "complete",
            "uses_inlabs": uses_inlabs,
            "total_weekdays": 0,
            "inlabs_days": [],
            "inlabs_count": 0,
            "missing_days": [],
            "missing_count": 0,
            "downloadable_inlabs_days": [],
            "downloadable_count": 0,
            "api_dou_days": [],
            "api_dou_count": 0
        })
    
    first_day = weekdays[0]
    last_day_str = weekdays[-1]
    downloaded = get_downloaded_dates(first_day, last_day_str)
    
    inlabs_days = sorted([d for d in weekdays if d in downloaded])
    missing_days = sorted([d for d in weekdays if d not in downloaded])
    
    # Segregar dias faltantes: dentro da janela de 120 dias do INLABS vs anteriores (API DOU)
    downloadable_inlabs_days = [d for d in missing_days if is_within_inlabs_retention_window(d, 120)]
    api_dou_days = [d for d in missing_days if not is_within_inlabs_retention_window(d, 120)]
    
    if not missing_days:
        scenario = "complete"
    elif len(inlabs_days) == 0 and len(downloadable_inlabs_days) == 0:
        scenario = "all_api_dou"
    elif len(api_dou_days) > 0 and (len(inlabs_days) > 0 or len(downloadable_inlabs_days) > 0):
        scenario = "mixed"
    else:
        scenario = "download_only"

    return jsonify({
        "status": "ok",
        "scenario": scenario,
        "uses_inlabs": uses_inlabs,
        "total_weekdays": len(weekdays),
        "inlabs_days": inlabs_days,
        "inlabs_count": len(inlabs_days),
        "missing_days": missing_days,
        "missing_count": len(missing_days),
        "downloadable_inlabs_days": downloadable_inlabs_days,
        "downloadable_count": len(downloadable_inlabs_days),
        "api_dou_days": api_dou_days,
        "api_dou_count": len(api_dou_days)
    })

@dags_bp.route('/routines/download_missing_inlabs', methods=['POST'])
@login_required
def api_download_missing_inlabs():
    """Dispara o download no INLABS (DAG ro-dou_inlabs_load_pg) para os dias faltantes dentro da janela de 120 dias."""
    from ..services.holiday_service import get_business_days_for_month, is_within_inlabs_retention_window
    from ..services.inlabs_service import get_downloaded_dates, enforce_inlabs_retention_limit, record_inlabs_download_success
    from ..services.airflow_service import trigger_airflow_dag, wait_for_specific_dag_runs

    data = request.get_json() or {}
    days = data.get('days', [])
    if not days:
        try:
            year = int(data.get('year'))
            month = int(data.get('month'))
            weekdays = get_business_days_for_month(year, month, cap_today=True)
            if weekdays:
                downloaded = get_downloaded_dates(weekdays[0], weekdays[-1])
                days = [d for d in weekdays if d not in downloaded]
        except Exception as e:
            return jsonify({"status": "error", "message": f"Erro ao identificar dias: {e}"}), 400

    # Filtra apenas dias dentro da janela de 120 dias do INLABS
    downloadable_days = [d for d in days if is_within_inlabs_retention_window(d, 120)]

    if not downloadable_days:
        return jsonify({"status": "ok", "message": "Nenhum dia disponível para download no portal INLABS (fora da janela de 120 dias). A busca será realizada via API DOU."})

    import threading
    def run_downloads(app_context, target_days):
        import time
        from datetime import datetime, timezone, timedelta
        with app_context:
            from ..models import db, SyncHistory
            # Aplica limite de 120 dias protegendo os dias solicitados
            enforce_inlabs_retention_limit(max_days=120, protected_dates=target_days)
            
            sucessos = 0
            run_ids = []
            date_by_run = {}
            for d_str in target_days:
                ok, msg, run_info = trigger_airflow_dag("ro-dou_inlabs_load_pg", d_str)
                if ok and isinstance(run_info, dict) and run_info.get("dag_run_id"):
                    r_id = run_info.get("dag_run_id")
                    run_ids.append(r_id)
                    date_by_run[r_id] = d_str
                    sucessos += 1
                time.sleep(0.05)
                
            try:
                hist = SyncHistory(
                    data=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M:%S'),
                    evento="Download INLABS Solicitado",
                    detalhes=f"Disparado download INLABS para {len(target_days)} dia(s) faltantes ({sucessos} DAGs acionadas)."
                )
                db.session.add(hist)
                db.session.commit()
            except: pass

            if run_ids:
                finished_all, run_states = wait_for_specific_dag_runs("ro-dou_inlabs_load_pg", run_ids, max_wait=1800)
                for r_id, st in run_states.items():
                    if st == 'success' and r_id in date_by_run:
                        record_inlabs_download_success(date_by_run[r_id])

    threading.Thread(target=run_downloads, args=(current_app._get_current_object().app_context(), downloadable_days), daemon=True).start()

    return jsonify({
        "status": "success",
        "message": f"Download de {len(downloadable_days)} dia(s) faltantes disparado em segundo plano no INLABS.",
        "days": downloadable_days
    })

@dags_bp.route('/routines/trigger_monthly', methods=['POST'])
@login_required
def api_trigger_monthly():
    data = request.get_json() or {}
    try:
        year = int(data.get('year'))
        month = int(data.get('month'))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Ano ou mês inválidos."}), 400
    routines = data.get('routines', [])
    mode = data.get('mode', 'full')  # 'full' ou 'inlabs_only'
    
    dag_confs_path = get_dag_confs_path()
    if not routines:
        # Pega todas as rotinas disponíveis
        yaml_files = [f for f in os.listdir(dag_confs_path) if f.endswith('.yaml') and not f.startswith('temp_') and '_part_' not in f]
        routines = yaml_files

    # Validar se as rotinas selecionadas estão ativas
    for rf in routines:
        fpath = os.path.join(dag_confs_path, rf)
        if os.path.exists(fpath):
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    yd = yaml.safe_load(f) or {}
                    is_act = yd.get('dag', {}).get('active')
                    if is_act is None:
                        is_act = yd.get('active', True)
                    if is_act is False:
                        return jsonify({"status": "error", "message": f"A rotina '{rf}' está pausada. Ative-a antes de disparar a busca mensal."}), 400
            except Exception:
                pass
    
    import threading
    
    def run_monthly_search_in_background(app_context, routines, month, year, mode='full'):
        import time
        from datetime import datetime, date
        import requests
        import yaml
        import re
        import os
        import glob
        import logging
        from ..services.holiday_service import get_business_days_for_month, is_within_inlabs_retention_window
        from ..services.airflow_service import trigger_airflow_dag, wait_for_specific_dag_runs
        from ..services.inlabs_service import get_downloaded_dates, enforce_inlabs_retention_limit, record_inlabs_download_success
        from ..services.mention_service import get_real_mentions
        from ..models import db, Settings, EmailTemplate, InlabsDownloadLog
        
        confs_path = get_dag_confs_path()
        airflow_url = os.getenv('AIRFLOW_URL', 'http://airflow-webserver:8080')
        auth = ("airflow", "airflow")
        
        def wait_for_dags(dags_list, max_wait=1200):
            import time as _time
            start = _time.time()
            _time.sleep(5)
            consecutive_errors = 0
            while (_time.time() - start) < max_wait:
                all_done = True
                for did in set(dags_list):
                    try:
                        url = f"{airflow_url}/api/v1/dags/{did}/dagRuns?order_by=-execution_date&limit=30"
                        r = requests.get(url, auth=auth, timeout=5)
                        if r.status_code == 200:
                            consecutive_errors = 0
                            runs = r.json().get('dag_runs', [])
                            active = [run for run in runs if run.get('state') in ('running', 'queued')]
                            if active:
                                all_done = False
                                break
                        else:
                            consecutive_errors += 1
                            if consecutive_errors > 8:
                                all_done = True
                                break
                    except Exception:
                        consecutive_errors += 1
                        if consecutive_errors > 8:
                            all_done = True
                            break
                if all_done:
                    break
                _time.sleep(4)
                
        def wait_for_dag_discovery(dag_id, max_wait=120):
            import time as _time
            elapsed = 0
            interval = 5
            while elapsed < max_wait:
                try:
                    url = f"{airflow_url}/api/v1/dags/{dag_id}"
                    r = requests.get(url, auth=auth, timeout=5)
                    if r.status_code == 200:
                        return True
                except:
                    pass
                _time.sleep(interval)
                elapsed += interval
            return False
                
        # Calcular dias úteis do mês (excluindo feriados e finais de semana) em ordem cronológica
        weekdays = get_business_days_for_month(year, month, cap_today=True)
        if not weekdays:
            with app_context:
                add_history_event("Busca Mensal Concluída", f"Nenhum dia útil com circulação do DOU encontrado para o mês {month}/{year}.")
            return

        with app_context:
            # 1. Aplica limite de retenção de 120 dias protegendo TODOS os dias úteis do mês pesquisado
            enforce_inlabs_retention_limit(max_days=120, protected_dates=weekdays)

            # 2. Verificar dias INLABS disponíveis
            first_day = weekdays[0]
            last_day_str = weekdays[-1]
            downloaded = get_downloaded_dates(first_day, last_day_str)
            
            inlabs_days = sorted([d for d in weekdays if d in downloaded])
            missing_days = sorted([d for d in weekdays if d not in downloaded])
            
            add_history_event("Busca Mensal Iniciada",
                f"Mês {str(month).zfill(2)}/{year} • {len(inlabs_days)} dias INLABS disponíveis, "
                f"{len(missing_days)} dias faltantes (período: {weekdays[0]} a {weekdays[-1]}), modo: {mode}")

        # ─── FASE 0: Se houver dias faltantes e modo for 'download_and_search' (ou 'full'), baixa no INLABS os dias na janela de 120 dias ───
        if mode in ('download_and_search', 'full') and missing_days:
            downloadable_missing = [d for d in missing_days if is_within_inlabs_retention_window(d, 120)]
            
            if downloadable_missing:
                with app_context:
                    add_history_event("Download INLABS Solicitado",
                        f"Iniciando download dos {len(downloadable_missing)} dia(s) faltantes no INLABS antes da pesquisa mensal ({str(month).zfill(2)}/{year}).")
                
                triggered_load_run_ids = []
                date_by_run = {}
                for d_str in downloadable_missing:
                    ok, msg, run_info = trigger_airflow_dag("ro-dou_inlabs_load_pg", d_str)
                    if ok and isinstance(run_info, dict) and run_info.get("dag_run_id"):
                        r_id = run_info.get("dag_run_id")
                        triggered_load_run_ids.append(r_id)
                        date_by_run[r_id] = d_str
                    time.sleep(0.05)
                    
                if triggered_load_run_ids:
                    finished_all, run_states = wait_for_specific_dag_runs("ro-dou_inlabs_load_pg", triggered_load_run_ids, max_wait=1800)
                    
                    for r_id, st in run_states.items():
                        if st == 'success' and r_id in date_by_run:
                            record_inlabs_download_success(date_by_run[r_id])

                    # Revalidação direta no PostgreSQL
                    first_day = weekdays[0]
                    last_day_str = weekdays[-1]
                    actual_downloaded = get_downloaded_dates(first_day, last_day_str)
                    inlabs_days = sorted([d for d in weekdays if d in actual_downloaded])
                    missing_days = sorted([d for d in weekdays if d not in actual_downloaded])

                    with app_context:
                        add_history_event("Download INLABS Concluído",
                            f"Download finalizado. {len(inlabs_days)} de {len(weekdays)} dias úteis disponíveis no PostgreSQL. Iniciando agora as pesquisas nas rotinas...")

        # ─── FASE 1: Disparar DAGs INLABS para dias com dados ───
        all_emails = set()
        triggered_inlabs_dags = []
        all_triggered_runs = []
        
        # Coleta os e-mails de todas as rotinas selecionadas
        for routine_file in routines:
            file_path = os.path.join(confs_path, routine_file)
            if not os.path.exists(file_path): continue
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    yaml_data = yaml.safe_load(f) or {}
                r_emails = yaml_data.get('dag', {}).get('report', {}).get('emails', [])
                if isinstance(r_emails, list):
                    all_emails.update(r_emails)
            except Exception:
                pass

        if mode != 'api_dou_only' and inlabs_days:
            for routine_file in routines:
                file_path = os.path.join(confs_path, routine_file)
                if not os.path.exists(file_path): continue
                
                # Tratamento especial para rotina principal de CNPJ
                if routine_file == "Pesquisa_cnpj.yaml":
                    parts = glob.glob(os.path.join(confs_path, "Pesquisa_cnpj_sync.yaml"))
                    if not parts:
                        parts = glob.glob(os.path.join(confs_path, "Pesquisa_cnpj_part_*.yaml"))
                    if not parts:
                        parts = [file_path]
                    for p in parts:
                        try:
                            with open(p, 'r', encoding='utf-8') as pf:
                                pdata = yaml.safe_load(pf) or {}
                                pid = pdata.get('dag', {}).get('id')
                                if pid:
                                    r_emails = pdata.get('dag', {}).get('report', {}).get('emails', [])
                                    if isinstance(r_emails, list): all_emails.update(r_emails)
                                    for date_str in inlabs_days:
                                        ok, msg, run_info = trigger_airflow_dag(pid, date_str)
                                        if ok:
                                            if pid not in triggered_inlabs_dags:
                                                triggered_inlabs_dags.append(pid)
                                            if isinstance(run_info, dict) and run_info.get("dag_run_id"):
                                                all_triggered_runs.append(run_info)
                                        time.sleep(0.05)
                        except Exception as e:
                            logging.error(f"Erro ao disparar parte de Pesquisa_cnpj {p}: {e}")
                    continue

                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        yaml_data = yaml.safe_load(f)
                    
                    report = yaml_data.get('dag', {}).get('report', {})
                    routine_emails = report.get('emails', [])
                    if isinstance(routine_emails, list):
                        all_emails.update(routine_emails)
                        
                    dag_id = yaml_data.get('dag', {}).get('id')
                    if not dag_id: dag_id = re.sub(r'\.[^.]*$', '', routine_file)
                    
                    for date_str in inlabs_days:
                        ok, msg, run_info = trigger_airflow_dag(dag_id, date_str)
                        if ok:
                            if dag_id not in triggered_inlabs_dags:
                                triggered_inlabs_dags.append(dag_id)
                            if isinstance(run_info, dict) and run_info.get("dag_run_id"):
                                all_triggered_runs.append(run_info)
                        time.sleep(0.05)
                except Exception as e:
                    logging.error(f"Erro ao disparar rotina INLABS {routine_file}: {e}")

            if triggered_inlabs_dags:
                wait_for_dags(triggered_inlabs_dags)

        # ─── FASE 2: DAG Temporária para dias sem INLABS (modo 'full', 'download_and_search' ou 'api_dou_only') ───
        temp_dag_id = None
        temp_yaml_path = None
        
        dou_target_days = weekdays if mode == 'api_dou_only' else missing_days
        
        if mode in ('full', 'download_and_search', 'api_dou_only') and dou_target_days and routines:
            try:
                temp_search_blocks = []
                for routine_file in routines:
                    routine_path = os.path.join(confs_path, routine_file)
                    
                    files_to_read = [routine_path]
                    if routine_file == "Pesquisa_cnpj.yaml":
                        parts = glob.glob(os.path.join(confs_path, "Pesquisa_cnpj_sync.yaml"))
                        if not parts:
                            parts = glob.glob(os.path.join(confs_path, "Pesquisa_cnpj_part_*.yaml"))
                        if parts:
                            files_to_read = parts

                    for r_subfile in files_to_read:
                        if not os.path.exists(r_subfile):
                            continue
                        try:
                            with open(r_subfile, 'r', encoding='utf-8') as f:
                                base_yaml = yaml.safe_load(f) or {}
                        except Exception:
                            continue
                        
                        original_searches = base_yaml.get('dag', {}).get('search', [])
                        if not isinstance(original_searches, list):
                            original_searches = [original_searches] if original_searches else []
                        
                        for idx, block in enumerate(original_searches):
                            temp_block = {
                                "header": block.get("header", f"Busca API-DOU {os.path.basename(r_subfile)} - PARTE {idx+1}"),
                                "is_exact_search": block.get("is_exact_search", True),
                                "force_rematch": True,
                                "terms": block.get("terms", []),
                                "dou_sections": block.get("dou_sections", ["SECAO_1", "SECAO_2", "SECAO_3"]),
                                "field": block.get("field", "TUDO"),
                                "full_text": block.get("full_text", True),
                                "date": "DIA",
                                "sources": ["DOU"],
                            }
                            if block.get("department"): temp_block["department"] = block["department"]
                            if block.get("organs"): temp_block["organs"] = block["organs"]
                            if block.get("terms_ignore"): temp_block["terms_ignore"] = block["terms_ignore"]
                            temp_search_blocks.append(temp_block)
                
                if temp_search_blocks:
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    temp_dag_id = f"temp_monthly_dou_{timestamp}"
                    
                    temp_yaml = {
                        "dag": {
                            "id": temp_dag_id,
                            "description": f"Busca temporária API-DOU para mês {str(month).zfill(2)}/{year}",
                            "schedule": None,
                            "tags": ["temp", "api_dou", "monthly"],
                            "search": temp_search_blocks,
                            "report": {
                                "page_title": f"Busca Mensal API-DOU {str(month).zfill(2)}/{year}",
                                "emails": [],
                                "subject": f"Registrale - Mensal API-DOU {str(month).zfill(2)}/{year}"
                            }
                        }
                    }
                    
                    temp_yaml_path = os.path.join(confs_path, f"{temp_dag_id}.yaml")
                    with open(temp_yaml_path, 'w', encoding='utf-8') as f:
                        yaml.safe_dump(temp_yaml, f, allow_unicode=True, sort_keys=False)
                    
                    # Força o Airflow a reler os YAMLs alterando a data do gerador python
                    try:
                        generator_path = os.path.join(BASE_DIR, "src", "dou_dag_generator.py")
                        if os.path.exists(generator_path):
                            os.utime(generator_path, None)
                    except Exception:
                        pass
                    
                    dag_found = wait_for_dag_discovery(temp_dag_id)
                    if not dag_found:
                        logging.warning(f"Airflow não descobriu a DAG temporária {temp_dag_id} em 120s.")
                    
                    triggered_dou_dags = []
                    with app_context:
                        add_history_event("Busca Mensal (API DOU)",
                            f"Disparando busca via API Oficial do DOU para {len(dou_target_days)} dia(s) históricos/fora do INLABS.")
                    
                    for date_str in dou_target_days:
                        ok, msg, run_info = trigger_airflow_dag(temp_dag_id, date_str)
                        if ok:
                            if temp_dag_id not in triggered_dou_dags:
                                triggered_dou_dags.append(temp_dag_id)
                            if isinstance(run_info, dict) and run_info.get("dag_run_id"):
                                all_triggered_runs.append(run_info)
                        time.sleep(0.05)
                    
                    if triggered_dou_dags:
                        wait_for_dags(triggered_dou_dags, max_wait=1800)
                        
            except Exception as e:
                logging.error(f"Erro ao criar/executar DAG temporária API-DOU: {e}")

        # ─── FASE 3: Consolidar menções recém-executadas e enviar e-mails ───
        with app_context:
            from ..services.mention_service import clear_mentions_cache, get_real_mentions
            from ..models import db, Settings, Mention, Company
            try:
                time.sleep(3)
                
                companies = Company.query.with_entities(Company.cnpj_norm, Company.nome, Company.cnpj).all()
                cnpj_map = {c.cnpj_norm: c.nome for c in companies if c.cnpj_norm}
                cnpj_map.update({c.cnpj: c.nome for c in companies if c.cnpj})
                
                # 1. Extrai as menções geradas especificamente pelos DAG Runs disparados
                monthly_new_mentions = []
                seen_ids = set()
                
                for r_info in all_triggered_runs:
                    did = r_info.get("dag_id")
                    run_id = r_info.get("dag_run_id")
                    if did and run_id:
                        extracted = fetch_mentions_from_dag_run(did, run_id, airflow_url, auth, cnpj_map=cnpj_map)
                        for m in extracted:
                            if m['id'] not in seen_ids:
                                seen_ids.add(m['id'])
                                monthly_new_mentions.append(m)
                
                # 2. Persistir novas menções no banco SQLite
                if monthly_new_mentions:
                    for m in monthly_new_mentions:
                        existing = db.session.get(Mention, m['id'])
                        if not existing:
                            db.session.add(Mention(**m))
                        else:
                            existing.empresa = m.get('empresa', existing.empresa)
                            existing.secao = m.get('secao', existing.secao)
                            existing.data = m.get('data', existing.data)
                            existing.detected_at = m.get('detected_at', existing.detected_at)
                            existing.trecho = m.get('trecho', existing.trecho)
                            existing.link = m.get('link', existing.link)
                    db.session.commit()
                
                clear_mentions_cache()
                
                month_str_slash = f"/{str(month).zfill(2)}/{year}"
                month_str_iso = f"{year}-{str(month).zfill(2)}-"
                month_str_alt = f"-{str(month).zfill(2)}-{year}"
                relevant_monthly_mentions = [
                    m for m in monthly_new_mentions
                    if month_str_slash in m.get('data', '') or month_str_iso in m.get('data', '') or month_str_alt in m.get('data', '')
                ]
                if not relevant_monthly_mentions and monthly_new_mentions:
                    relevant_monthly_mentions = monthly_new_mentions
                
                logging.info(f"Busca Mensal FASE 3: {len(monthly_new_mentions)} menções novas extraídas, {len(relevant_monthly_mentions)} para o relatório do mês {month}/{year}")
                
                emails = list(all_emails)
                if not emails:
                    settings_record = Settings.query.filter_by(key='global_settings').first()
                    if settings_record:
                        smtp_data = settings_record.get_value().get('smtp', {})
                        smtp_from = smtp_data.get('from_email') or smtp_data.get('user', '')
                        if smtp_from: emails = [smtp_from]
                emails = [e.strip() for e in emails if e and str(e).strip()]
                
                if not emails:
                    add_history_event("Busca Mensal Concluída", f"Busca finalizada ({len(relevant_monthly_mentions)} menções em {month}/{year}), mas nenhum destinatário de e-mail configurado.")
                elif not relevant_monthly_mentions:
                    add_history_event("Busca Mensal Concluída", f"Nenhuma menção encontrada para o mês {month}/{year}.")
                else:
                    from ..services.email_service import EmailSender, build_mentions_email_html
                    sender = EmailSender(None)
                    
                    html = build_mentions_email_html(
                        relevant_monthly_mentions,
                        template_name='Relatório Mensal Registrale',
                        title=f"Relatório Consolidado de Menções ({month}/{year})",
                        subtitle=f"Abaixo constam as {len(relevant_monthly_mentions)} publicações identificadas pelo sistema Registrale no período consolidado:"
                    )
                    sender.send_custom_email(
                        to_emails=emails,
                        subject=f"Registrale - Relatório Mensal {month}/{year}",
                        html_content=html
                    )
                    
                    add_history_event("Busca Mensal Concluída",
                        f"Relatório mensal {month}/{year} enviado com {len(relevant_monthly_mentions)} menções para {len(emails)} destinatário(s).")
            except Exception as e:
                logging.error(f"Erro ao consolidar busca mensal: {e}")
                add_history_event("Erro (Busca Mensal)", str(e))
            finally:
                # ─── LIMPEZA DA DAG TEMPORÁRIA (Executada APÓS extração das menções na FASE 3) ───
                from ..services.dag_config_service import cleanup_orphaned_temp_dags
                if temp_yaml_path and os.path.exists(temp_yaml_path):
                    try:
                        os.remove(temp_yaml_path)
                    except Exception:
                        pass
                if temp_dag_id:
                    try:
                        from ..services.airflow_service import get_airflow_auth, get_airflow_url
                        auth = get_airflow_auth()
                        airflow_url = get_airflow_url()
                        requests.delete(f"{airflow_url}/api/v1/dags/{temp_dag_id}", auth=auth, timeout=5)
                    except Exception:
                        pass
                    try:
                        import shutil
                        log_dir = os.path.join(BASE_DIR, "mnt", "airflow-logs", f"dag_id={temp_dag_id}")
                        if os.path.exists(log_dir):
                            shutil.rmtree(log_dir, ignore_errors=True)
                    except Exception:
                        pass
                try:
                    generator_path = os.path.join(BASE_DIR, "src", "dou_dag_generator.py")
                    if os.path.exists(generator_path):
                        os.utime(generator_path, None)
                except Exception:
                    pass
                try:
                    cleanup_orphaned_temp_dags(max_age_seconds=0, force_all=False)
                except Exception:
                    pass

    app_context = current_app._get_current_object().app_context()
    threading.Thread(target=run_monthly_search_in_background, args=(app_context, routines, month, year, mode), daemon=True).start()
    return jsonify({"status": "success", "message": "Busca mensal iniciada em segundo plano."})
