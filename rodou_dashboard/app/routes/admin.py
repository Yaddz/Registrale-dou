from flask import Blueprint, request, jsonify, session
import os
import shutil
from dotenv import set_key
from .auth import login_required
from ..models import db, User, Settings, Company, SyncHistory, Mention
from ..services.mention_service import clear_mentions_cache

admin_bp = Blueprint('admin', __name__)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
LOGS_DIR = os.path.join(BASE_DIR, "mnt", "airflow-logs")

@admin_bp.route('/save_settings', methods=['POST'])
@login_required
def save_settings():
    if session['user']['role'] != 'master': return jsonify({"status": "error"}), 403
    data = request.json
    
    try:
        settings_record = Settings.query.filter_by(key='global_settings').first()
        if not settings_record:
            settings_record = Settings(key='global_settings')
            db.session.add(settings_record)
        settings_record.set_value(data)
        db.session.commit()
        
        env_path = os.path.join(BASE_DIR, '.env')
        
        if 'api_keys' in data:
            ak = data['api_keys']
            mappings = {
                "gestaoclick_access_token": "ACCESS_TOKEN",
                "gestaoclick_secret_token": "SECRET_ACCESS_TOKEN",
                "gestaoclick_base_url": "BASE_URL",
                "yaml_path": "YAML_PATH"
            }
            for key, env_var in mappings.items():
                val = ak.get(key)
                if val:
                    set_key(env_path, env_var, val)
                    os.environ[env_var] = val
        
        if 'smtp' in data:
            smtp = data['smtp']
            smtp_mappings = {
                "server": "AIRFLOW__SMTP__SMTP_HOST",
                "port": "AIRFLOW__SMTP__SMTP_PORT",
                "user": "AIRFLOW__SMTP__SMTP_USER",
                "password": "AIRFLOW__SMTP__SMTP_PASSWORD",
                "from_email": "AIRFLOW__SMTP__SMTP_MAIL_FROM"
            }
            for key, env_var in smtp_mappings.items():
                val = smtp.get(key)
                if val:
                    set_key(env_path, env_var, str(val))
                    os.environ[env_var] = str(val)
            
            if not smtp.get('from_email') and smtp.get('user') and "@" in smtp.get('user'):
                set_key(env_path, "AIRFLOW__SMTP__SMTP_MAIL_FROM", smtp.get('user'))
                os.environ["AIRFLOW__SMTP__SMTP_MAIL_FROM"] = smtp.get('user')
                
        # Mapeamento para INLABS
        if 'inlabs' in data:
            inlabs = data['inlabs']
            inlabs_user = inlabs.get('user', '')
            inlabs_pass = inlabs.get('password', '')
            if inlabs_user and inlabs_pass:
                import requests
                airflow_url = os.getenv('AIRFLOW_URL', 'http://airflow-webserver:8080')
                auth = ("airflow", "airflow")
                
                try:
                    res = requests.get(f"{airflow_url}/api/v1/connections/inlabs_portal", auth=auth, timeout=5)
                    if res.status_code == 200:
                        requests.patch(
                            f"{airflow_url}/api/v1/connections/inlabs_portal?update_mask=login,password", 
                            json={"login": inlabs_user, "password": inlabs_pass}, 
                            auth=auth,
                            timeout=5
                        )
                    else:
                        payload = {
                            "connection_id": "inlabs_portal",
                            "conn_type": "http",
                            "host": "https://inlabs.in.gov.br/",
                            "login": inlabs_user,
                            "password": inlabs_pass
                        }
                        requests.post(f"{airflow_url}/api/v1/connections", json=payload, auth=auth, timeout=5)
                except Exception as e:
                    import logging
                    logging.error(f"Failed to update Airflow connection inlabs_portal: {e}")

        return jsonify({"status": "success", "message": "Configurações salvas e aplicadas!"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": "Erro ao salvar no BD: " + str(e)}), 500

@admin_bp.route('/users', methods=['GET', 'POST', 'DELETE'])
@login_required
def manage_users():
    if session['user']['role'] != 'master': return jsonify({"status": "error"}), 403
    
    if request.method == 'GET':
        users = User.query.all()
        return jsonify([{"username": u.username, "role": u.role} for u in users])
        
    if request.method == 'POST':
        data = request.json
        if not data.get('username') or not data.get('password'):
            return jsonify({"status": "error", "message": "Campos obrigatórios"}), 400
            
        if User.query.filter_by(username=data['username']).first():
            return jsonify({"status": "error", "message": "Já existe"}), 400
            
        new_user = User(username=data['username'], role=data.get('role', 'user'))
        new_user.set_password(data['password'])
        db.session.add(new_user)
        db.session.commit()
        return jsonify({"status": "success", "message": "Usuário criado com sucesso!"})
        
    elif request.method == 'DELETE':
        username = request.args.get('username')
        if username == session['user']['username']: return jsonify({"status": "error"}), 400
        user = User.query.filter_by(username=username).first()
        if user:
            db.session.delete(user)
            db.session.commit()
            return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 500

@admin_bp.route('/admin/clear_data', methods=['POST'])
@login_required
def admin_clear_data():
    if session['user']['role'] != 'master': return jsonify({"status": "error", "message": "Acesso negado"}), 403
    data = request.json
    action_type = data.get('type')
    
    try:
        if action_type == 'all':
            Company.query.delete()
            SyncHistory.query.delete()
            Mention.query.delete()
            Settings.query.filter_by(key='mentions_cache_meta').delete()
            db.session.commit()
            clear_mentions_cache()
            
            if os.path.exists(LOGS_DIR):
                for item in os.listdir(LOGS_DIR):
                    item_path = os.path.join(LOGS_DIR, item)
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path, ignore_errors=True)
            return jsonify({"status": "success", "message": "Banco de dados e logs completamente zerados."})
            
        elif action_type == 'history':
            SyncHistory.query.delete()
            Mention.query.delete()
            Settings.query.filter_by(key='mentions_cache_meta').delete()
            db.session.commit()
            clear_mentions_cache()
            return jsonify({"status": "success", "message": "Histórico e cache removidos."})
            
        elif action_type == 'mentions':
            Mention.query.delete()
            Settings.query.filter_by(key='mentions_cache_meta').delete()
            db.session.commit()
            clear_mentions_cache()
            return jsonify({"status": "success", "message": "Mentions (alertas) removidas do painel."})
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

import threading
import json
import re

@admin_bp.route('/sync', methods=['POST'])
@login_required
def manual_sync_route():
    from ..services.sync_cnpj import executar_sincronizacao
    if not executar_sincronizacao:
        return jsonify({"status": "error", "message": "Função de sincronização não encontrada."}), 500
    try:
        import threading
        
        def run_sync_in_background(app_context):
            from ..services.sync_cnpj import executar_sincronizacao
            try:
                import logging
                logging.info("Iniciando sincronização de CNPJs em segundo plano...")
                executar_sincronizacao()
                
                # Sincronizar JSON com o banco de dados
                metadata_file = os.path.join(BASE_DIR, "data", "monitored_companies.json")
                if os.path.exists(metadata_file):
                    import json
                    try:
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            empresas = json.load(f)
                            
                        with app_context:
                            count_new = 0
                            count_updated = 0
                            for emp in empresas:
                                cnpj = emp.get('cnpj', '')
                                if not cnpj: continue
                                from ..services.dag_config_service import normalize_cnpj
                                cnpj_norm = normalize_cnpj(cnpj)
                                existing = Company.query.filter_by(cnpj_norm=cnpj_norm).first()
                                if not existing:
                                    existing = Company(
                                        cnpj=cnpj,
                                        cnpj_norm=cnpj_norm,
                                        nome=emp.get('razao_social', emp.get('nome', 'N/A')),
                                        uf=emp.get('uf', ''),
                                        cidade=emp.get('cidade', ''),
                                        email=emp.get('email', ''),
                                        telefone=emp.get('telefone', ''),
                                        situacao=emp.get('situacao', 'Ativa'),
                                        origem='GestaoClick'
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
                            logging.info(f"Sync JSON->DB: {count_new} novas, {count_updated} atualizadas")
                    except Exception as e:
                        logging.error(f"Erro ao ler JSON de empresas: {e}")
                        
                from datetime import datetime, timezone, timedelta
                with app_context:
                    new_event = SyncHistory(
                        data=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m %H:%M'),
                        evento="Sincronização OK",
                        detalhes="Sincronização realizada com sucesso."
                    )
                    db.session.add(new_event)
                    db.session.commit()
                logging.info("Sincronização em segundo plano concluída com sucesso.")
            except Exception as e:
                import logging
                logging.error(f"Erro na sincronização em segundo plano: {e}")
                from datetime import datetime, timezone, timedelta
                with app_context:
                    new_event = SyncHistory(
                        data=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m %H:%M'),
                        evento="Erro Sync",
                        detalhes=str(e)
                    )
                    db.session.add(new_event)
                    db.session.commit()

        from flask import current_app
        app_context = current_app.app_context()
        threading.Thread(target=run_sync_in_background, args=(app_context,), daemon=True).start()
        
        from datetime import datetime, timezone, timedelta
        new_event = SyncHistory(
            data=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m %H:%M'),
            evento="Sincronização Iniciada",
            detalhes="Sincronização em segundo plano iniciada."
        )
        db.session.add(new_event)
        db.session.commit()
        
        return jsonify({"status": "success", "message": "Sincronização iniciada em segundo plano!"})
    except Exception as e:
        import logging
        logging.error(f"Erro na sincronização: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@admin_bp.route('/health_dou', methods=['GET'])
@login_required
def api_health_dou():
    try:
        import requests
        r = requests.get('https://www.in.gov.br/', timeout=5)
        if r.status_code == 200:
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error", "message": f"Erro {r.status_code}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@admin_bp.route('/status', methods=['GET'])
@login_required
def api_status():
    from ..models import Company, SyncHistory
    from ..services.mention_service import get_real_mentions
    from ..services.dag_config_service import get_last_search_time
    import glob
    from datetime import datetime, timezone, timedelta
    all_mentions = get_real_mentions()
    
    dag_confs_path = os.path.join(BASE_DIR, "dag_confs")
    yaml_files = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_sync.yaml"))
    if not yaml_files: 
        yaml_files = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_part_*.yaml"))
    
    last_sync = "N/A"
    if yaml_files:
        mtime = os.path.getmtime(yaml_files[0])
        last_sync = datetime.fromtimestamp(mtime, timezone(timedelta(hours=-3))).strftime('%d/%m %H:%M')
        
    last_search = get_last_search_time()
    history = [h.to_dict() for h in SyncHistory.query.order_by(SyncHistory.id.desc()).limit(5).all()]
    
    return jsonify({
        "last_sync": last_sync,
        "last_search": last_search,
        "historico": history,
        "mentions_count": len(all_mentions),
        "companies_count": Company.query.count()
    })

@admin_bp.route('/history/add', methods=['POST'])
@login_required
def api_history_add():
    data = request.get_json() or {}
    event = data.get('event', 'Evento Dashboard')
    details = data.get('details', '')
    
    try:
        from datetime import datetime, timezone, timedelta
        new_event = SyncHistory(
            data=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m %H:%M'),
            evento=event,
            detalhes=details
        )
        db.session.add(new_event)
        if SyncHistory.query.count() >= 50:
            oldest = SyncHistory.query.order_by(SyncHistory.id.asc()).first()
            if oldest:
                db.session.delete(oldest)
        db.session.commit()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success"})
