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
    
    if filename != "Pesquisa_cnpj.yaml":
        search["terms"] = data.get('terms', search.get('terms', []))
    
    search["dou_sections"] = data.get('sections', search.get('dou_sections', ["SECAO_1", "SECAO_2", "SECAO_3"]))
    search["field"] = search.get("field", "TUDO")
    search["is_exact_search"] = data.get('is_exact_search', True)
    search["force_rematch"] = data.get('force_rematch', True)
    search["terms_ignore"] = data.get('terms_ignore', [])
    search["full_text"] = search.get("full_text", True)
    search["date"] = search.get("date", "DIA")
    search["sources"] = [data.get('source', search.get('sources', ["DOU"])[0] if isinstance(search.get('sources'), list) and len(search.get('sources')) > 0 else 'DOU')]
    
    dag["search"] = [search]
    
    report = dag.get("report", {})
    report["title"] = data.get('name', report.get('title', 'Alerta'))
    report["emails"] = data.get('emails', report.get('emails', []))
    report["subject"] = data.get('subject', report.get('subject', ''))
    
    dag["report"] = report
    
    with open(file_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(new_dag, f, allow_unicode=True, sort_keys=False)
    
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

@dags_bp.route('/routines/trigger_monthly', methods=['POST'])
@login_required
def api_trigger_monthly():
    data = request.get_json() or {}
    year = int(data.get('year'))
    month = int(data.get('month'))
    routines = data.get('routines', [])
    
    import threading
    
    def run_monthly_search_in_background(app_context, routines, month, year):
        import calendar
        import time
        from datetime import datetime
        import requests
        from ..services.airflow_service import trigger_airflow_dag
        from ..services.mention_service import get_real_mentions
        from ..models import db, Settings, EmailTemplate
        from flask import current_app
        import logging
        
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
                time.sleep(10)

        needs_inlabs = False
        for routine_file in routines:
            file_path = os.path.join(dag_confs_path, routine_file)
            if not os.path.exists(file_path): continue
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    yaml_data = yaml.safe_load(f)
                    search = yaml_data.get('dag', {}).get('search', {})
                    if isinstance(search, list): search = search[0] if len(search) > 0 else {}
                    sources = search.get('sources', ['DOU'])
                    if 'INLABS' in sources:
                        needs_inlabs = True
                        break
            except: pass

        if needs_inlabs:
            with app_context:
                from ..routes.dags import add_history_event
                add_history_event("Busca Mensal", "Baixando base InLabs para o mês solicitado...")
            for day in range(1, last_day + 1):
                from datetime import date
                if date(year, month, day).weekday() >= 5: 
                    continue
                date_str = f"{year}-{str(month).zfill(2)}-{str(day).zfill(2)}"
                trigger_airflow_dag("ro-dou_inlabs_load_pg", date_str, skip_notifications=True)
                time.sleep(0.5)
            wait_for_dags(["ro-dou_inlabs_load_pg"])

        triggered_dags = []
        
        for routine_file in routines:
            file_path = os.path.join(dag_confs_path, routine_file)
            if not os.path.exists(file_path): continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    yaml_data = yaml.safe_load(f)
                    dag_id = yaml_data.get('dag', {}).get('id')
                    if not dag_id: dag_id = re.sub(r'\.[^.]*$', '', routine_file)
                    
                    for day in range(1, last_day + 1):
                        from datetime import date
                        if date(year, month, day).weekday() >= 5:
                            continue
                        date_str = f"{year}-{str(month).zfill(2)}-{str(day).zfill(2)}"
                        ok, msg = trigger_airflow_dag(dag_id, date_str, skip_notifications=True)
                        if ok and dag_id not in triggered_dags:
                            triggered_dags.append(dag_id)
                        time.sleep(0.5)
            except Exception as e:
                logging.error(f"Erro ao disparar rotina {routine_file}: {e}")
        
        if not triggered_dags:
            return
            
        with app_context:
            from ..routes.dags import add_history_event
            add_history_event("Busca Mensal Iniciada", f"Referência {month}/{year}. DAGs disparadas e aguardando conclusão...")
            
        wait_for_dags(triggered_dags)
        
        with app_context:
            from ..routes.dags import add_history_event
            all_mentions = get_real_mentions()
            month_str = f"/{str(month).zfill(2)}/{year}"
            
            monthly_mentions = [m for m in all_mentions if month_str in m.get('data', '')]
            
            if monthly_mentions:
                try:
                    mentions_html = ""
                    for m in monthly_mentions:
                        mentions_html += f'''
                        <div style="margin-bottom:20px;padding:15px;background-color:#f8fafc;border-radius:8px;border-left:4px solid #2563eb;">
                            <h4 style="margin:0 0 8px 0;color:#1e293b;font-size:15px;">{m.get('empresa')}</h4>
                            <div style="font-size:12px;color:#64748b;margin-bottom:8px;">
                                {m.get('cnpj')} | {m.get('secao')} | {m.get('data')}
                            </div>
                            <div style="font-size:14px;color:#475569;line-height:1.6;">
                                {m.get('trecho')}
                            </div>
                            <div style="margin-top:8px;">
                                <a href="{m.get('link')}" style="color:#2563eb;text-decoration:none;font-weight:600;">Acessar Publicação</a>
                            </div>
                        </div>
                        '''
                    
                    template = EmailTemplate.query.filter_by(name='Padrão Registrale').first()
                    html_content = ""
                    if template:
                        html_content = template.body_html.replace('{content}', mentions_html)
                    else:
                        html_content = mentions_html
                        
                    settings_record = Settings.query.filter_by(key='global_settings').first()
                    emails = []
                    if settings_record:
                        import json
                        s_val = settings_record.get_value()
                        notif = s_val.get('notifications', {})
                        if notif.get('send_email'):
                            emails = [e.strip() for e in notif.get('email_list', '').split(',') if e.strip()]
                    
                    if emails:
                        from ..services.email_service import EmailSender
                        sender = EmailSender(None)
                        sender.send_custom_email(
                            to_emails=emails,
                            subject=f"Registrale - Relatório Mensal Consolidado {month}/{year}",
                            html_content=html_content
                        )
                        add_history_event("Busca Mensal Concluída", f"Relatório consolidado enviado para {len(emails)} emails com {len(monthly_mentions)} menções.")
                    else:
                        add_history_event("Busca Mensal Concluída", f"Busca concluída com {len(monthly_mentions)} menções, mas envio de e-mail está desativado.")
                except Exception as e:
                    logging.error(f"Erro ao enviar email consolidado: {e}")
                    add_history_event("Busca Mensal Concluída (Erro Email)", f"Busca concluída, mas erro ao enviar email: {e}")
            else:
                add_history_event("Busca Mensal Concluída", f"Busca concluída. Nenhuma menção encontrada para o mês {month}/{year}.")

    from flask import current_app
    app_context = current_app.app_context()
    threading.Thread(target=run_monthly_search_in_background, args=(app_context, routines, month, year)).start()
    return jsonify({"status": "success", "message": "Busca mensal iniciada em segundo plano."})
