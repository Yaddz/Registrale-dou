from flask import Blueprint, request, jsonify, session
import os
import yaml
import glob
import re
from datetime import datetime
from .auth import login_required
from ..services.dag_config_service import get_routines
from ..services.airflow_service import trigger_airflow_dag

# Assumindo a mesma estrutura
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

dags_bp = Blueprint('dags', __name__)

def add_history_event(evento, detalhes):
    from ..models import db, SyncHistory
    try:
        from datetime import timezone, timedelta
        from flask import current_app
        new_event = SyncHistory(
            data=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m %H:%M'),
            evento=evento,
            detalhes=detalhes
        )
        db.session.add(new_event)
        if SyncHistory.query.count() >= 50:
            oldest = SyncHistory.query.order_by(SyncHistory.id.asc()).first()
            if oldest:
                db.session.delete(oldest)
        db.session.commit()
    except Exception as e:
        import logging
        logging.error(f"Erro ao adicionar histórico: {e}")

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
    
    if data.get('source') == 'INLABS':
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
    
    source_input = data.get('source', 'DOU')
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
    
    dag["report"] = report
    
    tmp_path = file_path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(new_dag, f, allow_unicode=True, sort_keys=False)
    os.replace(tmp_path, file_path)
    
    if filename == "Pesquisa_cnpj.yaml":
        from ..services.dag_config_service import rebuild_yaml_from_db
        rebuild_yaml_from_db()
    
    return jsonify({"status": "success", "message": "Rotina salva com sucesso!"})

@dags_bp.route('/routines/<path:file>', methods=['DELETE'])
@login_required
def delete_routine(file):
    if session['user']['role'] != 'master': return jsonify({"status": "error", "message": "Acesso negado."}), 403
    
    if file == "Pesquisa_cnpj.yaml" or "_part_" in file or "_sync" in file or "gestaoclick" in file.lower():
        return jsonify({"status": "error", "message": "Não é possível excluir rotinas de sistema (Sync / GestãoClick)."}), 400
        
    file_path = os.path.join(BASE_DIR, "dag_confs", file)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            add_history_event("Rotina Excluída", f"Rotina {file} removida do sistema.")
            return jsonify({"status": "success", "message": "Rotina excluída com sucesso!"})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Erro ao excluir o arquivo: {str(e)}"}), 500
    
    return jsonify({"status": "error", "message": "Arquivo não encontrado."}), 404

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

    dag_confs_path = os.path.join(BASE_DIR, "dag_confs")
    
    # ----------------------------------------------------
    # Lógica de verificação para disparo prévio do INLABS
    # ----------------------------------------------------
    is_inlabs = False
    dag_id_to_trigger = None

    if file == "Pesquisa_cnpj.yaml":
        file_path = os.path.join(dag_confs_path, file)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    yaml_check = yaml.safe_load(f)
                    dag_id_to_trigger = yaml_check.get('dag', {}).get('id')
                    search = yaml_check.get('dag', {}).get('search', {})
                    if isinstance(search, list) and len(search) > 0:
                        search = search[0]
                    sources = search.get('sources', ['DOU'])
                    if 'INLABS' in sources:
                        is_inlabs = True
            except: pass
    else:
        file_path = os.path.join(dag_confs_path, file)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    yaml_check = yaml.safe_load(f)
                    dag_id_to_trigger = yaml_check.get('dag', {}).get('id')
                    if not dag_id_to_trigger:
                        dag_id_to_trigger = re.sub(r'\.[^.]*$', '', file)
                    search = yaml_check.get('dag', {}).get('search', {})
                    if isinstance(search, list) and len(search) > 0:
                        search = search[0]
                    sources = search.get('sources', ['DOU'])
                    if 'INLABS' in sources:
                        is_inlabs = True
            except: pass

    if logical_date and is_inlabs and dag_id_to_trigger:
        import threading
        
        def run_inlabs_then_search(app_context, target_dag_id, target_date, filename):
            import time
            import requests
            from flask import current_app
            from ..services.airflow_service import trigger_airflow_dag
            from ..routes.dags import add_history_event

            airflow_url = os.getenv('AIRFLOW_URL', 'http://airflow-webserver:8080')
            auth = ("airflow", "airflow")
            
            with app_context:
                add_history_event("Carga INLABS", f"Iniciando download dos dados INLABS para {target_date}...")
            
            # 1. Dispara a carga
            trigger_airflow_dag("ro-dou_inlabs_load_pg", target_date, skip_notifications=True)
            
            # 2. Aguarda a carga
            # Polling com limite de 10 minutos (60 vezes x 10 segs)
            time.sleep(2)
            max_retries = 60
            while max_retries > 0:
                try:
                    url = f"{airflow_url}/api/v1/dags/ro-dou_inlabs_load_pg/dagRuns?state=running"
                    r = requests.get(url, auth=auth, timeout=5)
                    if r.status_code == 200 and len(r.json().get('dag_runs', [])) == 0:
                        url_q = f"{airflow_url}/api/v1/dags/ro-dou_inlabs_load_pg/dagRuns?state=queued"
                        r_q = requests.get(url_q, auth=auth, timeout=5)
                        if r_q.status_code == 200 and len(r_q.json().get('dag_runs', [])) == 0:
                            # Concluiu! Vamos registrar no banco
                            with app_context:
                                from ..models import InlabsDownloadLog, db
                                from datetime import datetime
                                new_log = InlabsDownloadLog(date_str=target_date, downloaded_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                                db.session.merge(new_log)
                                db.session.commit()
                            break 
                except:
                    pass
                time.sleep(10)
                max_retries -= 1
                
            # 3. Dispara a busca
            with app_context:
                add_history_event("Carga INLABS Concluída", f"Disparando agora a busca {filename}...")
                trigger_airflow_dag(target_dag_id, target_date)
        
        from flask import current_app
        app_context = current_app.app_context()
        threading.Thread(target=run_inlabs_then_search, args=(app_context, dag_id_to_trigger, logical_date, file)).start()
        
        add_history_event("Busca Agendada", f"Download do INLABS iniciado para {logical_date}. A busca rodará em seguida.")
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
        errors = []
        for p in parts:
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    dag_id = data.get('dag', {}).get('id')
                    if dag_id:
                        ok, msg = trigger_airflow_dag(dag_id, logical_date)
                        if ok: success_count += 1
                        else: errors.append(msg)
            except: continue
        
        if success_count > 0:
            add_history_event("Busca Iniciada", f"Rotina {file} (ou suas partes) disparada via Airflow. Data Lógica: {logical_date or 'Atual'}")
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
            
            ok, msg = trigger_airflow_dag(dag_id, logical_date)
            if ok:
                add_history_event("Busca Iniciada", f"Rotina {file} disparada via Airflow. Data Lógica: {logical_date or 'Atual'}")
                return jsonify({"status": "success", "message": f"Busca {dag_id} iniciada!"})
            else:
                add_history_event("Busca (Tentativa)", f"Tentativa de disparar {dag_id}: {msg}")
                return jsonify({"status": "warning", "message": "Busca solicitada, mas houve erro no Airflow.", "details": msg})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@dags_bp.route('/routines/monthly_inlabs_check', methods=['GET'])
@login_required
def api_monthly_inlabs_check():
    """Consulta quais dias do mês têm dados INLABS disponíveis."""
    from ..models import InlabsDownloadLog
    import calendar
    from datetime import date
    
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    routine_file = request.args.get('routine', '')
    
    if not month or not year:
        return jsonify({"status": "error", "message": "Mês e ano são obrigatórios."}), 400
    
    # Checar se a rotina usa INLABS
    dag_confs_path = os.path.join(BASE_DIR, "dag_confs")
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
    
    last_day = calendar.monthrange(year, month)[1]
    today = date.today()
    if year == today.year and month == today.month:
        last_day = today.day
    
    # Gerar dias úteis do mês
    weekdays = []
    for day in range(1, last_day + 1):
        d = date(year, month, day)
        if d.weekday() < 5:  # segunda a sexta
            weekdays.append(f"{year}-{str(month).zfill(2)}-{str(day).zfill(2)}")
    
    # Consultar banco
    downloaded = set(
        log.date_str for log in InlabsDownloadLog.query.filter(
            InlabsDownloadLog.date_str.in_(weekdays),
            InlabsDownloadLog.status == 'success'
        ).all()
    )
    
    inlabs_days = sorted([d for d in weekdays if d in downloaded])
    missing_days = sorted([d for d in weekdays if d not in downloaded])
    
    return jsonify({
        "status": "ok",
        "uses_inlabs": uses_inlabs,
        "total_weekdays": len(weekdays),
        "inlabs_days": inlabs_days,
        "inlabs_count": len(inlabs_days),
        "missing_days": missing_days,
        "missing_count": len(missing_days)
    })

@dags_bp.route('/routines/trigger_monthly', methods=['POST'])
@login_required
def api_trigger_monthly():
    data = request.get_json() or {}
    year = int(data.get('year'))
    month = int(data.get('month'))
    routines = data.get('routines', [])
    mode = data.get('mode', 'full')  # 'full' ou 'inlabs_only'
    
    import threading
    
    def run_monthly_search_in_background(app_context, routines, month, year, mode='full'):
        import calendar
        import time
        from datetime import datetime, date
        import requests
        import yaml
        import re
        import os
        import logging
        from ..services.airflow_service import trigger_airflow_dag
        from ..services.mention_service import get_real_mentions
        from ..models import db, Settings, EmailTemplate, InlabsDownloadLog
        
        last_day = calendar.monthrange(year, month)[1]
        today = datetime.now()
        if year == today.year and month == today.month:
            last_day = min(last_day, today.day)
            
        dag_confs_path = os.path.join(BASE_DIR, "dag_confs")
        airflow_url = os.getenv('AIRFLOW_URL', 'http://airflow-webserver:8080')
        auth = ("airflow", "airflow")
        
        def wait_for_dags(dags_list):
            while True:
                all_done = True
                for did in set(dags_list):
                    try:
                        url = f"{airflow_url}/api/v1/dags/{did}/dagRuns?state=running"
                        r = requests.get(url, auth=auth, timeout=5)
                        if r.status_code == 200 and len(r.json().get('dag_runs', [])) > 0:
                            all_done = False
                            break
                        url_q = f"{airflow_url}/api/v1/dags/{did}/dagRuns?state=queued"
                        r_q = requests.get(url_q, auth=auth, timeout=5)
                        if r_q.status_code == 200 and len(r_q.json().get('dag_runs', [])) > 0:
                            all_done = False
                            break
                    except: pass
                if all_done:
                    break
                time.sleep(2)
                
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
                
        # Calcular dias úteis do mês
        weekdays = []
        for day in range(1, last_day + 1):
            if date(year, month, day).weekday() < 5:
                weekdays.append(f"{year}-{str(month).zfill(2)}-{str(day).zfill(2)}")

        with app_context:
            from ..routes.dags import add_history_event
            # Verificar dias INLABS disponíveis
            downloaded = set(
                log.date_str for log in InlabsDownloadLog.query.filter(
                    InlabsDownloadLog.date_str.in_(weekdays),
                    InlabsDownloadLog.status == 'success'
                ).all()
            )
            inlabs_days = [d for d in weekdays if d in downloaded]
            missing_days = [d for d in weekdays if d not in downloaded]
            
            add_history_event("Busca Mensal Iniciada",
                f"Mês {month}/{year} • {len(inlabs_days)} dias INLABS, "
                f"{len(missing_days)} dias faltantes, modo: {mode}")

        # ─── FASE 1: Disparar DAGs INLABS para dias com dados ───
        all_emails = set()
        triggered_inlabs_dags = []
        
        for routine_file in routines:
            file_path = os.path.join(dag_confs_path, routine_file)
            if not os.path.exists(file_path): continue
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
                    ok, msg = trigger_airflow_dag(dag_id, date_str, skip_notifications=True)
                    if ok and dag_id not in triggered_inlabs_dags:
                        triggered_inlabs_dags.append(dag_id)
                    time.sleep(0.1)
            except Exception as e:
                logging.error(f"Erro ao disparar rotina INLABS {routine_file}: {e}")

        if triggered_inlabs_dags:
            wait_for_dags(triggered_inlabs_dags)

        # ─── FASE 2: DAG Temporária para dias sem INLABS (modo 'full') ───
        temp_dag_id = None
        temp_yaml_path = None
        
        if mode == 'full' and missing_days and routines:
            try:
                first_routine_path = os.path.join(dag_confs_path, routines[0])
                with open(first_routine_path, 'r', encoding='utf-8') as f:
                    base_yaml = yaml.safe_load(f)
                
                original_searches = base_yaml.get('dag', {}).get('search', [])
                if not isinstance(original_searches, list):
                    original_searches = [original_searches] if original_searches else []
                
                temp_search_blocks = []
                for idx, block in enumerate(original_searches):
                    temp_block = {
                        "header": block.get("header", f"Busca API-DOU - PARTE {idx+1}"),
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
                temp_dag_id = f"temp_monthly_dou_{timestamp}"
                
                temp_yaml = {
                    "dag": {
                        "id": temp_dag_id,
                        "description": f"Busca temporária API-DOU para mês {month}/{year}",
                        "schedule": None,
                        "tags": ["temp", "api_dou", "monthly"],
                        "search": temp_search_blocks,
                        "report": {
                            "title": f"Busca Mensal API-DOU {month}/{year}",
                            "emails": list(all_emails),
                            "subject": f"Registrale - Mensal API-DOU {month}/{year}"
                        }
                    }
                }
                
                temp_yaml_path = os.path.join(dag_confs_path, f"{temp_dag_id}.yaml")
                with open(temp_yaml_path, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(temp_yaml, f, allow_unicode=True, sort_keys=False)
                
                dag_found = wait_for_dag_discovery(temp_dag_id)
                if not dag_found:
                    logging.warning(f"Airflow não descobriu a DAG temporária {temp_dag_id} em 120s.")
                
                triggered_dou_dags = []
                with app_context:
                    from ..routes.dags import add_history_event
                    add_history_event("Busca Mensal (API DOU)",
                        f"Disparando {len(missing_days)} dias sem INLABS via API-DOU")
                
                for date_str in missing_days:
                    ok, msg = trigger_airflow_dag(temp_dag_id, date_str, skip_notifications=True)
                    if ok and temp_dag_id not in triggered_dou_dags:
                        triggered_dou_dags.append(temp_dag_id)
                    time.sleep(0.1)
                
                if triggered_dou_dags:
                    wait_for_dags(triggered_dou_dags)
                
                if temp_yaml_path and os.path.exists(temp_yaml_path):
                    try:
                        os.remove(temp_yaml_path)
                    except: pass
                    
            except Exception as e:
                logging.error(f"Erro ao criar DAG temporária API-DOU: {e}")
            finally:
                # Segurança caso dê erro antes
                if temp_yaml_path and os.path.exists(temp_yaml_path):
                    try:
                        os.remove(temp_yaml_path)
                    except: pass

        # ─── FASE 3: Consolidar e enviar e-mails ───
        with app_context:
            from ..routes.dags import add_history_event
            try:
                all_mentions = get_real_mentions()
                month_str = f"/{str(month).zfill(2)}/{year}"
                monthly_mentions = [m for m in all_mentions if month_str in m.get('data', '')]
                
                emails = list(all_emails)
                if not emails:
                    settings_record = Settings.query.filter_by(key='global_settings').first()
                    if settings_record:
                        smtp_from = settings_record.get_value().get('smtp', {}).get('from_email', '')
                        if smtp_from: emails = [smtp_from]
                
                if monthly_mentions and emails:
                    from ..services.email_service import EmailSender
                    sender = EmailSender(None)
                    
                    inlabs_date_set = set(
                        f"{d[8:10]}/{d[5:7]}/{d[0:4]}" for d in inlabs_days
                    )
                    dou_date_set = set(
                        f"{d[8:10]}/{d[5:7]}/{d[0:4]}" for d in missing_days
                    )
                    
                    inlabs_m = [m for m in monthly_mentions if m.get('data','') in inlabs_date_set]
                    dou_m    = [m for m in monthly_mentions if m.get('data','') in dou_date_set]
                    
                    template = EmailTemplate.query.filter_by(name='Relatório Mensal Registrale').first()
                    if not template:
                        template = EmailTemplate.query.filter_by(name='Padrão Registrale').first()
                    
                    def build_html(mentions, source_label):
                        parts = []
                        for m in mentions:
                            trecho = re.sub(r'\s*-\s*PARTE\s*\d+', '', m.get('trecho',''), flags=re.IGNORECASE)
                            cnpj = m.get('cnpj', '')
                            if cnpj and cnpj in trecho:
                                trecho = trecho.replace(cnpj, f"<span class='highlight'>{cnpj}</span>")
                            
                            parts.append(f'''
                            <div class="container">
                                <div class="content">
                                    <section>
                                        <div class="results-section">
                                            <div class="result-header" title="{m.get("empresa","—")}">
                                                {m.get("empresa","—")}
                                            </div>
                                            <div class="result-body">
                                                <h3><strong>Resultados para: </strong> {cnpj}</h3>
                                                <div class="section-marker">{m.get("secao","—")}</div>
                                                <div class="abstract">
                                                    <span class="tag recort">Recorte:</span> {trecho}
                                                </div>
                                                <div class="date">{m.get("data","—")}</div>
                                                <div style="margin-top: 12px;">
                                                    <a href="{m.get("link","#")}" class="document-meta" target="_blank" style="text-decoration: none;">
                                                        <span style="color: #06acff; vertical-align: middle; margin-right: 4px;">&#8599;</span>
                                                        Ver Íntegra
                                                    </a>
                                                </div>
                                                <hr class="separator"></hr>
                                            </div>
                                        </div>
                                    </section>
                                </div>
                            </div>''')
                        mentions_html = ''.join(parts)
                        if template:
                            return template.body_html.replace('{content}', mentions_html)
                        return mentions_html
                    
                    if inlabs_m:
                        html = build_html(inlabs_m, "INLABS")
                        sender.send_custom_email(
                            to_emails=emails,
                            subject=f"Registrale - Relatório Mensal INLABS {month}/{year}",
                            html_content=html
                        )
                    
                    if dou_m and mode == 'full':
                        html = build_html(dou_m, "API-DOU")
                        sender.send_custom_email(
                            to_emails=emails,
                            subject=f"Registrale - Relatório Mensal API-DOU {month}/{year} (dias sem INLABS)",
                            html_content=html
                        )
                    
                    total = len(inlabs_m) + len(dou_m)
                    add_history_event("Busca Mensal Concluída",
                        f"{len(inlabs_m)} menções INLABS + {len(dou_m)} API-DOU = {total} total. "
                        f"E-mails enviados para {len(emails)} destinatário(s).")
                else:
                    add_history_event("Busca Mensal Concluída",
                        f"Nenhuma menção encontrada em {month}/{year}.")
            except Exception as e:
                logging.error(f"Erro ao consolidar busca mensal: {e}")
                add_history_event("Erro (Busca Mensal)", str(e))

    from flask import current_app
    app_context = current_app.app_context()
    threading.Thread(target=run_monthly_search_in_background, args=(app_context, routines, month, year, mode)).start()
    return jsonify({"status": "success", "message": "Busca mensal iniciada em segundo plano."})
