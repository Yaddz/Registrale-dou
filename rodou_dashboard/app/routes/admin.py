from flask import Blueprint, request, jsonify, session
import os
import shutil
from dotenv import set_key, unset_key
from .auth import login_required
from ..models import db, User, Settings, Company, SyncHistory, Mention
from ..runtime.paths import get_data_dir, get_logs_dir
from ..services.mention_service import clear_mentions_cache

admin_bp = Blueprint('admin', __name__)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
DATA_DIR = str(get_data_dir(create=True))
LOGS_DIR = str(get_logs_dir(create=False))

@admin_bp.route('/settings', methods=['GET'])
@login_required
def get_settings():
    if session['user']['role'] != 'master':
        return jsonify({"status": "error", "message": "Acesso negado."}), 403
    from ..runtime.paths import get_default_pdf_dir
    from ..runtime.pdf_archiver import DEFAULT_LAYOUT, DEFAULT_SECTIONS

    settings_record = Settings.query.filter_by(key='global_settings').first()
    settings = {
        "smtp": {},
        "api_keys": {},
        "google_sheets": {},
        "inlabs": {},
        "inlabs_fallback": "pdf",
        "pdf_archive": {
            "enabled": True,
            "folder": str(get_default_pdf_dir(create=False)),
            "layout": DEFAULT_LAYOUT,
            "sections": list(DEFAULT_SECTIONS),
        },
    }
    if settings_record:
        val = settings_record.get_value()
        if isinstance(val, dict):
            for k, v in val.items():
                if isinstance(v, dict) and isinstance(settings.get(k), dict):
                    settings[k].update(v)
                else:
                    settings[k] = v
    from ..services.email_service import is_smtp_enabled
    settings["smtp"]["enabled"] = is_smtp_enabled(settings.get("smtp"))
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
            
        if 'inlabs_fallback' in data:
            fb_val = str(data.get('inlabs_fallback') or '').strip().lower()
            if fb_val not in {'pdf', 'api', 'off'}:
                return jsonify({"status": "error", "message": "Opção inválida para fonte de contingência INLABS."}), 400
            data['inlabs_fallback'] = fb_val

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
            if smtp_server.lower().startswith('stmp.'):
                smtp_server = 'smtp.' + smtp_server[5:]
            elif smtp_server.lower().startswith('smpt.'):
                smtp_server = 'smtp.' + smtp_server[5:]
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
            from ..services.email_service import is_smtp_enabled
            smtp_enabled = bool(smtp['enabled']) if 'enabled' in smtp else is_smtp_enabled(existing_val.get('smtp', {}))

            merged_val['smtp'] = {
                "enabled": smtp_enabled,
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
                
            # Sincronizar conexão smtp_default no orquestrador (no-op no modo local)
            if smtp_server and smtp_user:
                try:
                    import json
                    from ..runtime.executor import get_executor

                    conn_payload = {
                        "connection_id": "smtp_default",
                        "conn_type": "smtp",
                        "host": smtp_server,
                        "login": smtp_user,
                        "password": smtp_password,
                        "port": int(smtp_port) if smtp_port.isdigit() else 587,
                        "extra": json.dumps({"from_email": smtp_from, "disable_tls": False})
                    }
                    get_executor().sync_connection("smtp_default", conn_payload)
                except Exception as e:
                    import logging
                    logging.error(f"Falha ao atualizar conexão smtp_default: {e}")
                
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
                try:
                    from ..runtime.executor import get_executor
                    payload = {
                        "connection_id": "inlabs_portal",
                        "conn_type": "http",
                        "host": "https://inlabs.in.gov.br/",
                        "login": inlabs_user,
                        "password": inlabs_pass
                    }
                    get_executor().sync_connection("inlabs_portal", payload)
                except Exception as e:
                    import logging
                    logging.error(f"Failed to update connection inlabs_portal: {e}")

        if 'pdf_archive' in data and isinstance(data['pdf_archive'], dict):
            from ..runtime.paths import get_default_pdf_dir
            from ..runtime.pdf_archiver import (
                normalize_pdf_layout,
                normalize_sections,
                validate_pdf_folder,
            )

            pa = data['pdf_archive']
            enabled_val = bool(pa.get('enabled', True))
            folder_val = str(pa.get('folder') or '').strip() or str(get_default_pdf_dir(create=False))
            if enabled_val or str(pa.get('folder') or '').strip():
                try:
                    checked = validate_pdf_folder(folder_val)
                    folder_val = checked["path"]
                except ValueError as exc:
                    return jsonify({"status": "error", "message": str(exc)}), 400
            layout_val = normalize_pdf_layout(
                pa.get('layout', existing_val.get('pdf_archive', {}).get('layout'))
            )
            merged_val['pdf_archive'] = {
                "enabled": enabled_val,
                "folder": folder_val,
                "layout": layout_val,
                "sections": normalize_sections(pa.get('sections')),
            }

        # Salvar o dicionário final com todos os campos e sanitizações
        settings_record.set_value(merged_val)
        db.session.commit()

        from ..runtime.scheduler import reload_scheduler_if_running
        reload_scheduler_if_running()

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
        data = request.get_json(silent=True) or {}
        if not data.get('username') or not data.get('password'):
            return jsonify({"status": "error", "message": "Campos obrigatórios"}), 400
            
        if User.query.filter_by(username=data['username']).first():
            return jsonify({"status": "error", "message": "Já existe"}), 400
            
        try:
            new_user = User(username=data['username'], role=data.get('role', 'user'))
            new_user.set_password(data['password'])
            db.session.add(new_user)
            db.session.commit()
            return jsonify({"status": "success", "message": "Usuário criado com sucesso!"})
        except Exception as e:
            db.session.rollback()
            return jsonify({"status": "error", "message": str(e)}), 500
        
    elif request.method == 'DELETE':
        username = request.args.get('username')
        if username == session['user']['username']:
            return jsonify({"status": "error", "message": "Não é possível excluir o usuário logado."}), 400
        user = User.query.filter_by(username=username).first()
        if user:
            try:
                db.session.delete(user)
                db.session.commit()
                return jsonify({"status": "success", "message": "Usuário excluído com sucesso."})
            except Exception as e:
                db.session.rollback()
                return jsonify({"status": "error", "message": str(e)}), 500
        return jsonify({"status": "error", "message": "Usuário não encontrado."}), 404
    return jsonify({"status": "error", "message": "Método não permitido."}), 405

@admin_bp.route('/admin/clear_data', methods=['POST'])
@login_required
def admin_clear_data():
    if session['user']['role'] != 'master': return jsonify({"status": "error", "message": "Acesso negado"}), 403
    data = request.get_json(silent=True) or {}
    action_type = data.get('type')
    
    try:
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
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@admin_bp.route('/sync', methods=['POST'])
@login_required
def manual_sync_route():
    try:
        from ..models import Settings
        from ..services.sync_cnpj import executar_sincronizacao
        import threading
        import os
        
        # Validar credenciais do GestãoClick antes de disparar
        settings_record = Settings.query.filter_by(key='global_settings').first()
        settings_data = settings_record.get_value() if settings_record else {}
        ak = settings_data.get('api_keys', {})
        access_token = (ak.get('gestaoclick_access_token') or os.getenv("ACCESS_TOKEN") or '').strip()
        secret_token = (ak.get('gestaoclick_secret_token') or os.getenv("SECRET_ACCESS_TOKEN") or '').strip()
        
        if not access_token or not secret_token:
            return jsonify({
                "status": "error",
                "message": "Credenciais do GestãoClick não configuradas. Acesse a aba Configurações > Integrações para cadastrar seu Access Token e Secret Token."
            }), 400
        
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

import threading

_inlabs_portal_lock = threading.Lock()
_inlabs_portal_cache = {'time': 0.0, 'ok': True, 'msg': ''}


def _get_cached_inlabs_portal_status(force_refresh: bool = False):
    import time
    with _inlabs_portal_lock:
        now = time.time()
        if force_refresh or (now - _inlabs_portal_cache['time'] > 60):
            try:
                from ..services.inlabs_service import check_inlabs_portal_status
                ok, msg = check_inlabs_portal_status()
            except Exception as exc:
                ok, msg = False, f"Não foi possível verificar o portal INLABS: {exc}"
            _inlabs_portal_cache.update({'time': now, 'ok': bool(ok), 'msg': str(msg or '')})
        return _inlabs_portal_cache['ok'], _inlabs_portal_cache['msg']


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

    last_sync = SyncHistory.get_last_sync_display()

    from ..runtime.pdf_search import FALLBACK_API, FALLBACK_OFF, FALLBACK_PDF, get_fallback_mode
    from ..services.inlabs_service import is_date_loaded

    today_iso = datetime.now(timezone(timedelta(hours=-3))).strftime('%Y-%m-%d')
    portal_ok, portal_msg = _get_cached_inlabs_portal_status(
        force_refresh=request.args.get('refresh', '').lower() in ('1', 'true', 'yes')
    )
    try:
        today_loaded, _ = is_date_loaded(today_iso)
    except Exception:
        today_loaded = False

    fb_mode = get_fallback_mode()
    fb_labels = {
        FALLBACK_PDF: "PDF integral + API do DOU",
        FALLBACK_API: "API do DOU",
        FALLBACK_OFF: "Desligado",
    }

    username = session.get('user', {}).get('username', '')
    if portal_ok and today_loaded and username:
        set_user_dismissed_notice(username, 'inlabs', None)

    return jsonify({
        "last_sync": last_sync,
        "last_search": get_last_search_time(),
        "next_search": get_next_search_time(),
        "historico": history,
        "kpis": kpis,
        "dismissed_notices": get_user_dismissed_notices(username),
        "inlabs_status": {
            "portal_ok": portal_ok,
            "portal_message": portal_msg,
            "today_loaded": bool(today_loaded),
            "fallback_mode": fb_mode,
            "fallback_label": fb_labels.get(fb_mode, "PDF integral + API do DOU"),
            "executor_mode": "local",
        },
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
        
    from sqlalchemy import text
    from ..services.inlabs_service import get_inlabs_postgres_engine
    import logging
    try:
        engine = get_inlabs_postgres_engine()
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
    from flask import send_file, request
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


@admin_bp.route('/admin/logs', methods=['GET'])
@login_required
def get_admin_logs():
    """Lista os arquivos de log e retorna o conteúdo recente do log selecionado."""
    from ..runtime.logging_setup import list_log_files, read_log_tail

    selected = request.args.get('file', 'registrale.log')
    lines = request.args.get('lines', 200, type=int) or 200
    try:
        files = list_log_files()
        tail = read_log_tail(selected, lines=lines)
        return jsonify({"status": "success", "files": files, "tail": tail})
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@admin_bp.route('/admin/first_run_status', methods=['GET'])
@login_required
def get_first_run_status():
    """Retorna estado da primeira execução, versão do app/schema e fontes legadas."""
    from ..models import Company, Mention, Settings, db
    from ..runtime.migrations import get_schema_version
    from ..runtime.migrator import detect_legacy_sources
    from ..runtime.pdf_archiver import get_pdf_archive_config
    from ..runtime.version import get_app_version
    from ..services.access_service import is_access_onboarding_done, is_login_required

    done_rec = Settings.query.filter_by(key='first_run_import_done').first()
    import_done = bool(done_rec and done_rec.get_value())
    pdf_done_rec = Settings.query.filter_by(key='pdf_onboarding_done').first()
    pdf_onboarding_done = bool(pdf_done_rec and pdf_done_rec.get_value())
    is_fresh = (Company.query.count() == 0 and Mention.query.count() == 0 and not import_done)
    return jsonify({
        "status": "success",
        "version": get_app_version(),
        "schema_version": get_schema_version(db.engine),
        "import_done": import_done,
        "is_fresh_install": is_fresh,
        "pdf_onboarding_done": pdf_onboarding_done,
        "needs_pdf_onboarding": not pdf_onboarding_done,
        "needs_access_onboarding": not is_access_onboarding_done(),
        "login_required": is_login_required(),
        "pdf_archive": get_pdf_archive_config(),
        "legacy_sources": detect_legacy_sources(),
    })


@admin_bp.route('/admin/pdf_onboarding', methods=['POST'])
@login_required
def save_pdf_onboarding():
    """Salva a configuração inicial de pasta/layout dos PDFs e marca o passo como concluído."""
    if session['user']['role'] != 'master':
        return jsonify({"status": "error", "message": "Acesso negado."}), 403

    from ..runtime.paths import get_default_pdf_dir
    from ..runtime.pdf_archiver import (
        normalize_pdf_layout,
        normalize_sections,
        validate_pdf_folder,
    )

    data = request.get_json(silent=True) or {}
    enabled_val = bool(data.get('enabled', True))
    raw_folder = str(data.get('folder') or '').strip() or str(get_default_pdf_dir(create=False))
    if enabled_val or str(data.get('folder') or '').strip():
        try:
            checked = validate_pdf_folder(raw_folder)
            folder_val = checked["path"]
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 400
    else:
        folder_val = raw_folder

    layout_val = normalize_pdf_layout(data.get('layout'))
    sections_val = normalize_sections(data.get('sections'))

    try:
        settings_record = Settings.query.filter_by(key='global_settings').first()
        existing_val = settings_record.get_value() if settings_record else {}
        if not isinstance(existing_val, dict):
            existing_val = {}
        if not settings_record:
            settings_record = Settings(key='global_settings')
            db.session.add(settings_record)

        merged_val = dict(existing_val)
        merged_val['pdf_archive'] = {
            "enabled": enabled_val,
            "folder": folder_val,
            "layout": layout_val,
            "sections": sections_val,
        }
        settings_record.set_value(merged_val)

        done_rec = Settings.query.filter_by(key='pdf_onboarding_done').first()
        if not done_rec:
            done_rec = Settings(key='pdf_onboarding_done')
            db.session.add(done_rec)
        done_rec.set_value(True)
        db.session.commit()

        SyncHistory.log_event(
            "Configuração Inicial PDF",
            f"Pasta: {folder_val} | Organização: {layout_val} | Seções: {', '.join(sections_val)}",
        )
        return jsonify({
            "status": "success",
            "message": "Preferências de arquivamento dos PDFs salvas!",
            "pdf_archive": merged_val['pdf_archive'],
            "pdf_onboarding_done": True,
        })
    except Exception as exc:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Erro ao salvar configuração inicial: {exc}"}), 500


@admin_bp.route('/admin/first_run_import', methods=['POST'])
@login_required
def run_first_run_import():
    """Importa database.db e/ou rotinas YAML de uma instalação anterior com backup prévio."""
    if session['user']['role'] != 'master':
        return jsonify({"status": "error", "message": "Acesso negado"}), 403

    import shutil
    import tempfile
    from pathlib import Path
    from werkzeug.utils import secure_filename
    from ..models import Settings, SyncHistory, db
    from ..runtime.migrator import import_docker_database, import_routines_from_dir
    from ..runtime.paths import get_routines_dir

    db_result = None
    routines_result = None
    tmp_dir = tempfile.mkdtemp(prefix="registrale_import_")
    try:
        if request.content_type and 'multipart/form-data' in request.content_type:
            overwrite = request.form.get('overwrite', 'false').lower() in ('true', '1', 'yes')
            uploaded_db = request.files.get('db_file')
            if uploaded_db and uploaded_db.filename:
                safe_db_name = secure_filename(uploaded_db.filename)
                if not safe_db_name:
                    return jsonify({"status": "error", "message": "Nome de arquivo de banco inválido."}), 400
                tmp_db = Path(tmp_dir) / safe_db_name
                uploaded_db.save(str(tmp_db))
                db_result = import_docker_database(tmp_db, overwrite_existing=overwrite)

            uploaded_routines = request.files.getlist('routine_files')
            valid_routines = [f for f in uploaded_routines if f and f.filename]
            if valid_routines:
                tmp_routines = Path(tmp_dir) / "rotinas"
                tmp_routines.mkdir(parents=True, exist_ok=True)
                for rf in valid_routines:
                    fname = secure_filename(rf.filename)
                    if fname.lower().endswith(('.yaml', '.yml')):
                        rf.save(str(tmp_routines / fname))
                routines_result = import_routines_from_dir(
                    tmp_routines, target_dir=get_routines_dir(create=True), overwrite=overwrite
                )
        else:
            data = request.get_json(silent=True) or {}
            overwrite = bool(data.get('overwrite', False))
            db_path_str = (data.get('db_path') or '').strip()
            routines_dir_str = (data.get('routines_dir') or '').strip()

            if db_path_str:
                db_result = import_docker_database(Path(db_path_str), overwrite_existing=overwrite)
            if routines_dir_str:
                routines_result = import_routines_from_dir(
                    Path(routines_dir_str), target_dir=get_routines_dir(create=True), overwrite=overwrite
                )

        if db_result is None and routines_result is None:
            return jsonify({"status": "error", "message": "Informe um banco database.db ou rotinas YAML para importar."}), 400

        done_rec = Settings.query.filter_by(key='first_run_import_done').first()
        if not done_rec:
            done_rec = Settings(key='first_run_import_done')
            db.session.add(done_rec)
        done_rec.set_value(True)
        db.session.commit()

        SyncHistory.log_event(
            "Importação Inicial",
            f"Banco: {(db_result or {}).get('imported', {})}; Rotinas: {(routines_result or {}).get('copied', [])}",
        )

        try:
            from ..runtime.scheduler import reload_scheduler
            reload_scheduler()
        except Exception:
            pass

        return jsonify({
            "status": "success",
            "db": db_result,
            "routines": routines_result,
        })
    except (FileNotFoundError, ValueError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"status": "error", "message": f"Erro ao importar dados: {exc}"}), 500
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@admin_bp.route('/admin/updates/check', methods=['GET'])
@login_required
def check_app_updates():
    """Consulta as Releases do GitHub e informa se há nova versão disponível."""
    from ..models import db
    from ..runtime.migrations import get_schema_version
    from ..runtime.updater import check_for_updates

    try:
        info = check_for_updates()
        info["status"] = "success"
        info["schema_version"] = get_schema_version(db.engine)
        return jsonify(info)
    except Exception as exc:
        return jsonify({"status": "error", "message": f"Falha ao verificar atualizações: {exc}"}), 502


@admin_bp.route('/admin/updates/download', methods=['POST'])
@login_required
def download_app_update():
    """Baixa o instalador da Release e valida o hash SHA-256."""
    if session['user']['role'] != 'master':
        return jsonify({"status": "error", "message": "Acesso negado"}), 403

    from ..runtime.updater import download_and_verify_update, launch_installer_windows

    data = request.get_json(silent=True) or {}
    installer_url = data.get('installer_url', '')
    sha256_url = data.get('sha256_url', '')
    filename = data.get('installer_name')
    launch = bool(data.get('launch', False))

    if not installer_url or not sha256_url:
        return jsonify({"status": "error", "message": "URLs do instalador e do .sha256 são obrigatórias."}), 400

    try:
        saved_path = download_and_verify_update(
            installer_url=installer_url,
            sha256_url=sha256_url,
            expected_filename=filename,
        )
        launched = False
        if launch and os.name == 'nt':
            launch_installer_windows(saved_path)
            launched = True
        return jsonify({
            "status": "success",
            "path": str(saved_path),
            "launched": launched,
            "message": "Instalador baixado e verificado via SHA-256.",
        })
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"status": "error", "message": f"Erro ao baixar atualização: {exc}"}), 502


_VALID_NOTICES = ("inlabs", "integrations")


def get_user_dismissed_notices(username: str) -> dict:
    """Retorna o mapa de avisos dispensados para o usuário informado."""
    if not username:
        return {}
    rec = Settings.query.filter_by(key="dismissed_notices").first()
    val = rec.get_value() if rec else {}
    if not isinstance(val, dict):
        return {}
    user_map = val.get(username, {})
    return dict(user_map) if isinstance(user_map, dict) else {}


def set_user_dismissed_notice(username: str, notice: str, signature):
    """Persiste ou limpa o fechamento de um aviso da Visão geral para o usuário."""
    if not username or notice not in _VALID_NOTICES:
        return {}
    rec = Settings.query.filter_by(key="dismissed_notices").first()
    val = rec.get_value() if rec else {}
    if not isinstance(val, dict):
        val = {}
    user_map = val.get(username)
    if not isinstance(user_map, dict):
        user_map = {}

    changed = False
    if signature is None or signature == "":
        if notice in user_map:
            user_map.pop(notice, None)
            changed = True
    else:
        sig_str = str(signature)
        if user_map.get(notice) != sig_str:
            user_map[notice] = sig_str
            changed = True

    if changed:
        val[username] = user_map
        if not rec:
            rec = Settings(key="dismissed_notices")
            db.session.add(rec)
        rec.set_value(val)
        db.session.commit()
    return dict(user_map)


@admin_bp.route('/notices/dismissed', methods=['GET'])
@login_required
def api_get_dismissed_notices():
    username = session.get('user', {}).get('username', '')
    return jsonify({"status": "ok", "dismissed": get_user_dismissed_notices(username)})


@admin_bp.route('/notices/dismiss', methods=['POST'])
@login_required
def api_dismiss_notice():
    data = request.get_json(silent=True) or {}
    notice = str(data.get('notice') or '').strip()
    if notice not in _VALID_NOTICES:
        return jsonify({"status": "error", "message": "Aviso inválido."}), 400
    signature = data.get('signature')
    username = session.get('user', {}).get('username', '')
    updated = set_user_dismissed_notice(username, notice, signature)
    return jsonify({"status": "ok", "dismissed": updated})


@admin_bp.route('/admin/access_settings', methods=['GET'])
@login_required
def get_access_settings():
    from ..services.access_service import (
        is_access_onboarding_done,
        is_local_request,
        is_login_required,
    )
    return jsonify({
        "status": "ok",
        "login_required": is_login_required(),
        "onboarding_done": is_access_onboarding_done(),
        "can_disable": is_local_request(request),
    })


@admin_bp.route('/admin/access_settings', methods=['POST'])
@login_required
def save_access_settings():
    """Liga/desliga o login (Configurações → Usuários e passo do primeiro acesso)."""
    if session.get('user', {}).get('role') != 'master':
        return jsonify({"status": "error", "message": "Acesso negado."}), 403

    from ..services.access_service import (
        get_auto_login_user,
        is_local_request,
        is_login_required,
        mark_access_onboarding_done,
        set_login_required,
    )

    data = request.get_json(silent=True) or {}
    if 'login_required' not in data:
        return jsonify({"status": "error", "message": "Informe login_required."}), 400
    required = bool(data.get('login_required'))

    if not required:
        if not is_local_request(request):
            return jsonify({
                "status": "error",
                "message": "O login só pode ser desligado acessando o painel neste computador (127.0.0.1).",
            }), 400
        if not get_auto_login_user():
            return jsonify({"status": "error", "message": "É preciso ter um usuário master."}), 400

    changed = required != is_login_required()
    set_login_required(required)
    mark_access_onboarding_done()
    if changed:
        SyncHistory.log_event(
            "Acesso ao painel",
            "Login exigido para abrir o painel." if required
            else "Login desligado: o painel abre direto neste computador.",
        )
    if required:
        from datetime import datetime, timedelta, timezone
        # A sessão aberta sem senha vira uma sessão normal até expirar.
        if session.pop('auto_login', None):
            session.permanent = True
            session['expires_at'] = (datetime.now(timezone(timedelta(hours=-3))) + timedelta(minutes=30)).timestamp()
    return jsonify({"status": "ok", "login_required": required, "onboarding_done": True})
