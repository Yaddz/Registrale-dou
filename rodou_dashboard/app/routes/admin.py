from flask import Blueprint, request, jsonify, session
import os
import shutil
from dotenv import set_key, unset_key
from .auth import login_required
from ..models import db, User, Settings, Company, SyncHistory, Mention
from ..services.mention_service import clear_mentions_cache

admin_bp = Blueprint('admin', __name__)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data'))
os.makedirs(DATA_DIR, exist_ok=True)
LOGS_DIR = os.path.join(BASE_DIR, "mnt", "airflow-logs")

@admin_bp.route('/settings', methods=['GET'])
@login_required
def get_settings():
    if session['user']['role'] != 'master':
        return jsonify({"status": "error", "message": "Acesso negado."}), 403
    settings_record = Settings.query.filter_by(key='global_settings').first()
    settings = {"smtp": {}, "api_keys": {}, "google_sheets": {}, "inlabs": {}}
    if settings_record:
        val = settings_record.get_value()
        if isinstance(val, dict):
            settings.update(val)
    return jsonify({"status": "ok", "settings": settings})

@admin_bp.route('/save_settings', methods=['POST'])
@login_required
def save_settings():
    if session['user']['role'] != 'master': return jsonify({"status": "error"}), 403
    data = request.json or {}
    
    try:
        settings_record = Settings.query.filter_by(key='global_settings').first()
        existing_val = settings_record.get_value() if settings_record else {}
        if not isinstance(existing_val, dict):
            existing_val = {}
            
        if not settings_record:
            settings_record = Settings(key='global_settings')
            db.session.add(settings_record)
            
        merged_val = dict(existing_val)
        for k, v in data.items():
            if isinstance(v, dict) and isinstance(merged_val.get(k), dict):
                merged_sub = dict(merged_val[k])
                merged_sub.update(v)
                merged_val[k] = merged_sub
            else:
                merged_val[k] = v
                
        env_path = os.path.join(DATA_DIR, '.env')
        # Create empty .env in persistent data dir if it doesn't exist
        if not os.path.exists(env_path):
            open(env_path, 'a').close()
        
        if 'api_keys' in data and isinstance(data['api_keys'], dict):
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
        
        if 'smtp' in data and isinstance(data['smtp'], dict):
            smtp = data['smtp']
            
            # Sanitizar campos SMTP
            smtp_server = str(smtp.get('server') or '').strip()
            smtp_port = str(smtp.get('port') or '587').strip()
            smtp_user = str(smtp.get('user') or '').strip()
            raw_password = str(smtp.get('password') or '').strip()
            
            # Se não enviou senha nova, preserva a senha anterior salva
            if not raw_password and existing_val.get('smtp', {}).get('password'):
                raw_password = existing_val.get('smtp', {}).get('password')
                
            smtp_password = raw_password
            if 'gmail.com' in smtp_server.lower() or 'googlemail.com' in smtp_server.lower():
                smtp_password = raw_password.replace(' ', '')
            smtp_from = str(smtp.get('from_email') or smtp_user).strip()
            
            merged_val['smtp'] = {
                "server": smtp_server,
                "port": smtp_port,
                "user": smtp_user,
                "password": smtp_password,
                "from_email": smtp_from
            }
            
            smtp_mappings = {
                "AIRFLOW__SMTP__SMTP_HOST": smtp_server,
                "AIRFLOW__SMTP__SMTP_PORT": smtp_port,
                "AIRFLOW__SMTP__SMTP_USER": smtp_user,
                "AIRFLOW__SMTP__SMTP_PASSWORD": smtp_password,
                "AIRFLOW__SMTP__SMTP_MAIL_FROM": smtp_from
            }
            for env_var, val in smtp_mappings.items():
                if val:
                    set_key(env_path, env_var, str(val))
                    os.environ[env_var] = str(val)
                else:
                    unset_key(env_path, env_var)
                    os.environ.pop(env_var, None)
                    
            if smtp_port in ('587', '25'):
                set_key(env_path, "AIRFLOW__SMTP__SMTP_STARTTLS", "true")
                os.environ["AIRFLOW__SMTP__SMTP_STARTTLS"] = "true"
            elif smtp_port == '465':
                set_key(env_path, "AIRFLOW__SMTP__SMTP_SSL", "true")
                os.environ["AIRFLOW__SMTP__SMTP_SSL"] = "true"
                
            # Sincronizar conexão smtp_default no Airflow
            if smtp_server and smtp_user:
                try:
                    import requests
                    import json
                    airflow_url = os.getenv('AIRFLOW_URL', 'http://airflow-webserver:8080')
                    auth = ("airflow", "airflow")
                    
                    conn_payload = {
                        "connection_id": "smtp_default",
                        "conn_type": "smtp",
                        "host": smtp_server,
                        "login": smtp_user,
                        "password": smtp_password,
                        "port": int(smtp_port) if smtp_port.isdigit() else 587,
                        "extra": json.dumps({"from_email": smtp_from, "disable_tls": False})
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
                    logging.error(f"Falha ao atualizar conexão smtp_default no Airflow: {e}")
                
        # Mapeamento para INLABS
        if 'inlabs' in data and isinstance(data['inlabs'], dict):
            inlabs = data['inlabs']
            inlabs_user = str(inlabs.get('user') or '').strip()
            inlabs_pass = str(inlabs.get('password') or '').strip()
            
            # Se não enviou senha nova, preserva a senha anterior salva
            if not inlabs_pass and existing_val.get('inlabs', {}).get('password'):
                inlabs_pass = existing_val.get('inlabs', {}).get('password')
                
            merged_val['inlabs'] = {
                "user": inlabs_user,
                "password": inlabs_pass
            }
            
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

        # Salvar o dicionário final com todos os campos e sanitizações
        settings_record.set_value(merged_val)
        db.session.commit()

        return jsonify({"status": "success", "message": "Configurações salvas e aplicadas!", "settings": merged_val})
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
        import time
        
        if action_type == 'all':
            Company.query.delete()
            SyncHistory.query.delete()
            Mention.query.delete()
            cache_meta = Settings.query.filter_by(key='mentions_cache_meta').first()
            if not cache_meta:
                cache_meta = Settings(key='mentions_cache_meta')
                db.session.add(cache_meta)
            cache_meta.set_value({"last_parsed_at": 0})
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
            db.session.commit()
            return jsonify({"status": "success", "message": "Histórico de sincronização removido."})
            
        elif action_type == 'mentions':
            Mention.query.delete()
            cache_meta = Settings.query.filter_by(key='mentions_cache_meta').first()
            if not cache_meta:
                cache_meta = Settings(key='mentions_cache_meta')
                db.session.add(cache_meta)
            cache_meta.set_value({"last_parsed_at": 0})
            db.session.commit()
            clear_mentions_cache()
            return jsonify({"status": "success", "message": "Menções (alertas) limpas do painel com sucesso."})
            
        elif action_type == 'inlabs_old':
            try:
                from ..services.inlabs_service import enforce_inlabs_retention_limit
                deleted_days = enforce_inlabs_retention_limit(max_days=120)
                return jsonify({"status": "success", "message": f"Limpeza INLABS concluída: {deleted_days} dia(s) mais antigo(s) removido(s) para manter o limite de 120 dias."})
            except Exception as inner_e:
                return jsonify({"status": "error", "message": f"Falha na limpeza INLABS: {str(inner_e)}"}), 500
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

import threading
import json
import re

@admin_bp.route('/sync', methods=['POST'])
@login_required
def manual_sync_route():
    try:
        from ..services.sync_cnpj import executar_sincronizacao
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
                        data=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M:%S'),
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
                        data=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M:%S'),
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
            data=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M:%S'),
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

@admin_bp.route('/status', methods=['GET'])
@login_required
def api_status():
    from ..services.dag_config_service import get_last_search_time, get_next_search_time, get_monitored_cnpjs
    from ..services.mention_service import get_mentions_kpis
    from ..models import db, SyncHistory, Company, Settings
    from datetime import datetime, timezone, timedelta
    import glob
    import os

    total_mentions, hoje_count, mes_count = get_mentions_kpis()

    try:
        history = [h.to_dict() for h in SyncHistory.query.order_by(SyncHistory.id.desc()).limit(5).all()]
    except:
        history = []

    kpis = {
        "cnpjs": Company.query.count(),
        "ativos": len(get_monitored_cnpjs()),
        "mencoes_hoje": hoje_count,
        "este_mes": mes_count,
        "mencoes_total": total_mentions
    }

    last_sync_record = SyncHistory.query.filter(
        (SyncHistory.evento.like('%GestãoClick%')) | 
        (SyncHistory.evento.like('%Google Sheets%')) |
        (SyncHistory.evento.like('%Sincronização%')) |
        (SyncHistory.evento.like('%Sync%'))
    ).order_by(SyncHistory.id.desc()).first()

    if last_sync_record:
        last_sync = last_sync_record.data
    else:
        from ..services.dag_config_service import get_dag_confs_path, get_base_yaml_path
        dag_confs_path = get_dag_confs_path()
        yaml_files = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_sync.yaml"))
        if not yaml_files: 
            yaml_files = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_part_*.yaml"))
        if not yaml_files:
            base = get_base_yaml_path()
            if os.path.exists(base):
                yaml_files = [base]
                
        last_sync = "N/A"
        if yaml_files:
            mtime = os.path.getmtime(yaml_files[0])
            last_sync = datetime.fromtimestamp(mtime, timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M')

    return jsonify({
        "last_sync": last_sync,
        "last_search": get_last_search_time(),
        "next_search": get_next_search_time(),
        "historico": history,
        "kpis": kpis
    })

_inlabs_cache = {'time': 0, 'data': None}

@admin_bp.route('/inlabs_stats', methods=['GET'])
@login_required
def get_inlabs_stats():
    global _inlabs_cache
    import time
    from flask import request
    
    force_refresh = request.args.get('refresh', '').lower() in ('true', '1', 'yes')
    if not force_refresh and (time.time() - _inlabs_cache['time'] < 10) and _inlabs_cache['data']:
        return jsonify(_inlabs_cache['data'])
        
    from sqlalchemy import create_engine, text
    import logging
    try:
        engine = create_engine('postgresql+pg8000://airflow:airflow@postgres:5432/inlabs')
        with engine.connect() as conn:
            conn.execute(text("SET statement_timeout = 5000"))
            size_res = conn.execute(text("SELECT pg_size_pretty(pg_database_size('inlabs'))")).scalar()
            
            try:
                rows = conn.execute(text(
                    "SELECT CAST(pubdate AS DATE)::text AS dt, COUNT(*) AS total "
                    "FROM dou_inlabs.article_raw "
                    "GROUP BY dt "
                    "ORDER BY dt DESC"
                )).fetchall()
                
                days_list = [
                    {
                        "date": str(row[0]),
                        "count": int(row[1]),
                        "status": "Disponível"
                    }
                    for row in rows if row[0] is not None
                ]
                days_res = len(days_list)
            except Exception as q_err:
                logging.error(f"Erro ao listar datas do INLABS: {q_err}")
                days_list = []
                days_res = "Desconhecido"
            
        _inlabs_cache['data'] = {
            "status": "success",
            "size": size_res,
            "days_stored": days_res,
            "days": days_list
        }
        _inlabs_cache['time'] = time.time()
        return jsonify(_inlabs_cache['data'])
    except Exception as e:
        logging.error(f"Erro ao consultar DB Inlabs: {e}")
        return jsonify({"status": "error", "message": "Não foi possível conectar ao banco de dados INLABS."}), 500

@admin_bp.route('/manual', methods=['GET'])
@login_required
def get_user_manual():
    """Retorna o conteúdo do Manual do Usuário em Markdown ou como download."""
    from flask import send_file, Response, request
    manual_candidates = [
        os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'MANUAL.md'),
        os.path.join(BASE_DIR, 'MANUAL.md'),
        os.path.join(BASE_DIR, 'rodou_dashboard', 'docs', 'MANUAL.md'),
    ]
    manual_path = None
    for p in manual_candidates:
        if os.path.exists(p):
            manual_path = p
            break
            
    if not manual_path:
        return jsonify({"status": "error", "message": "Manual não encontrado."}), 404
        
    if request.args.get('download', '').lower() in ('true', '1', 'yes'):
        return send_file(manual_path, as_attachment=True, download_name='MANUAL.md', mimetype='text/markdown')
        
    try:
        with open(manual_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({"status": "success", "content": content})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

