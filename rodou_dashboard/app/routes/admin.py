from flask import Blueprint, request, jsonify, session
import os
import shutil
from dotenv import set_key, unset_key
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
        # Create empty .env if it doesn't exist to avoid errors
        if not os.path.exists(env_path):
            open(env_path, 'a').close()
        
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
                    set_key(env_path, env_var, str(val))
                    os.environ[env_var] = str(val)
                elif key in ak: # user sent empty string
                    unset_key(env_path, env_var)
                    os.environ.pop(env_var, None)
        
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
                elif key in smtp: # user sent empty string
                    unset_key(env_path, env_var)
                    os.environ.pop(env_var, None)
            
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
        from ..models import DeletedMention
        all_mentions = Mention.query.all()
        for m in all_mentions:
            if not DeletedMention.query.get(m.id):
                db.session.add(DeletedMention(id=m.id))
                
        if action_type == 'all':
            Company.query.delete()
            SyncHistory.query.delete()
            Mention.query.delete()
            import time
            cache_meta = Settings.query.filter_by(key='mentions_cache_meta').first()
            if not cache_meta:
                cache_meta = Settings(key='mentions_cache_meta')
                db.session.add(cache_meta)
            cache_meta.set_value({"last_parsed_at": time.time()})
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
            import time
            cache_meta = Settings.query.filter_by(key='mentions_cache_meta').first()
            if not cache_meta:
                cache_meta = Settings(key='mentions_cache_meta')
                db.session.add(cache_meta)
            cache_meta.set_value({"last_parsed_at": time.time()})
            db.session.commit()
            clear_mentions_cache()
            return jsonify({"status": "success", "message": "Histórico e cache removidos."})
            
        elif action_type == 'mentions':
            Mention.query.delete()
            import time
            cache_meta = Settings.query.filter_by(key='mentions_cache_meta').first()
            if not cache_meta:
                cache_meta = Settings(key='mentions_cache_meta')
                db.session.add(cache_meta)
            cache_meta.set_value({"last_parsed_at": time.time()})
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
                with app_context:
                    from ..services.dag_config_service import sync_json_to_db
                    sync_json_to_db()
                        
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
    from ..services.dag_config_service import get_last_search_time, get_next_search_time, get_monitored_cnpjs
    from ..services.mention_service import get_real_mentions
    from ..models import db, SyncHistory, Company
    from datetime import datetime, timezone, timedelta
    import glob
    import os
    
    now = datetime.now(timezone(timedelta(hours=-3)))
    all_mentions = get_real_mentions()

    try:
        history = [h.to_dict() for h in SyncHistory.query.order_by(SyncHistory.id.desc()).limit(5).all()]
    except:
        history = []

    kpis = {
        "cnpjs": Company.query.count(),
        "ativos": len(get_monitored_cnpjs()),
        "mencoes_hoje": len([m for m in all_mentions if m.get('data') == now.strftime('%d/%m/%Y')]),
        "este_mes": len([m for m in all_mentions if now.strftime('/%m/%Y') in m.get('data', '')]),
        "mencoes_total": len(all_mentions)
    }

    dag_confs_path = os.path.join(BASE_DIR, "dag_confs")
    yaml_files = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_sync.yaml"))
    if not yaml_files: 
        yaml_files = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_part_*.yaml"))
    if not yaml_files:
        base = os.path.join(dag_confs_path, "Pesquisa_cnpj.yaml")
        if os.path.exists(base):
            yaml_files = [base]
            
    last_sync = "N/A"
    if yaml_files:
        mtime = os.path.getmtime(yaml_files[0])
        last_sync = datetime.fromtimestamp(mtime, timezone(timedelta(hours=-3))).strftime('%d/%m %H:%M')

    return jsonify({
        "last_sync": last_sync,
        "last_search": get_last_search_time(),
        "next_search": get_next_search_time(),
        "historico": history,
        "kpis": kpis
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

@admin_bp.route('/inlabs_stats', methods=['GET'])
@login_required
def get_inlabs_stats():
    from sqlalchemy import create_engine, text
    import logging
    try:
        engine = create_engine('postgresql+pg8000://airflow:airflow@postgres:5432/inlabs')
        with engine.connect() as conn:
            size_res = conn.execute(text("SELECT pg_size_pretty(pg_database_size('inlabs'))")).scalar()
            days_res = conn.execute(text("SELECT COUNT(DISTINCT pubdate::date) FROM dou_inlabs.article_raw")).scalar()
            
        return jsonify({
            "status": "success",
            "size": size_res,
            "days_stored": days_res
        })
    except Exception as e:
        logging.error(f"Erro ao consultar DB Inlabs: {e}")
        return jsonify({"status": "error", "message": "Não foi possível conectar ao banco de dados INLABS."}), 500
