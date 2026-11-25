from flask import Blueprint, request, session, redirect, url_for, render_template, jsonify
import os
import glob
from datetime import datetime, timezone, timedelta
from functools import wraps
from ..models import User, Settings, SyncHistory, Company
from ..services.mention_service import get_mentions_kpis
from ..services.dag_config_service import get_monitored_cnpjs, get_last_search_time, get_next_search_time

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from ..services.access_service import is_login_required, is_same_origin_write, try_auto_login
        if not is_login_required():
            if not is_same_origin_write(request):
                return jsonify({"status": "error", "message": "Pedido recusado: origem diferente do painel."}), 403
            if try_auto_login(session, request):
                return f(*args, **kwargs)
        elif session.get('auto_login'):
            # Login foi religado: a sessão aberta sem senha não vale mais.
            session.clear()
        expires_at = session.get('expires_at')
        now_ts = datetime.now(timezone(timedelta(hours=-3))).timestamp()
        if 'user' not in session or (expires_at and now_ts > expires_at):
            session.clear()
            if request.path.startswith('/api') or request.is_json:
                return jsonify({"status": "error", "message": "Sessão expirada ou não autenticada."}), 401
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    from ..services.access_service import is_login_required, is_local_request
    if not is_login_required() and is_local_request(request):
        return redirect(url_for('auth.index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        # In a real app, from flask import current_app to get permanent_session_lifetime
        if user and user.check_password(password):
            session.clear()
            session.permanent = True
            session['user'] = {'username': user.username, 'role': user.role}
            session['expires_at'] = (datetime.now(timezone(timedelta(hours=-3))) + timedelta(minutes=30)).timestamp()
            return redirect(url_for('auth.index'))
        return render_template('login.html', error="Usuário ou senha inválidos")
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

@auth_bp.route('/api/extend_session', methods=['POST'])
@login_required
def extend_session():
    session.permanent = True
    session['expires_at'] = (datetime.now(timezone(timedelta(hours=-3))) + timedelta(minutes=60)).timestamp()
    return jsonify({"status": "ok", "time_left": 3600})

@auth_bp.route('/')
@login_required
def index():
    is_master = session['user']['role'] == 'master'
    
    from ..runtime.paths import get_default_pdf_dir
    from ..runtime.pdf_archiver import DEFAULT_LAYOUT, DEFAULT_SECTIONS

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
    users_list = []
    
    if is_master:
        settings_record = Settings.query.filter_by(key='global_settings').first()
        if settings_record:
            db_settings = settings_record.get_value()
            if isinstance(db_settings, dict):
                if "inlabs" not in db_settings:
                    db_settings["inlabs"] = {}
                for k, v in db_settings.items():
                    if isinstance(v, dict) and isinstance(settings.get(k), dict):
                        settings[k].update(v)
                    else:
                        settings[k] = v
        users_list = [{"username": u.username, "role": u.role} for u in User.query.all()]

    from ..services.email_service import is_smtp_enabled
    settings["smtp"]["enabled"] = is_smtp_enabled(settings.get("smtp"))
    settings["api_keys"]["gestaoclick_auto_sync"] = bool(settings["api_keys"].get("gestaoclick_auto_sync", False))
    settings["google_sheets"]["auto_sync"] = bool(settings["google_sheets"].get("auto_sync", False))
    settings["google_sheets"]["delete_obsolete"] = bool(settings["google_sheets"].get("delete_obsolete", False))
        
    history = [h.to_dict() for h in SyncHistory.query.order_by(SyncHistory.id.desc()).limit(50).all()]
    total_m, hoje_m, mes_m = get_mentions_kpis()
    
    last_sync = SyncHistory.get_last_sync_display()

    last_search = get_last_search_time()
    next_search = get_next_search_time()
    
    expires_at = session.get('expires_at')
    time_left = 0
    if expires_at:
        time_left = max(0, int(expires_at - datetime.now(timezone(timedelta(hours=-3))).timestamp()))

    init_data = {
        "kpis": {
            "cnpjs": Company.query.count(),
            "ativos": len(get_monitored_cnpjs()),
            "mencoes_hoje": hoje_m,
            "este_mes": mes_m,
            "mencoes_total": total_m
        }
    }

    from .admin import get_user_dismissed_notices
    dismissed_notices = get_user_dismissed_notices(session['user'].get('username', ''))

    from ..services.access_service import is_login_required
    return render_template('index.html', 
                           user=session['user'],
                           login_required=is_login_required(),
                           init_data=init_data,
                           last_sync=last_sync,
                           last_search=last_search,
                           next_search=next_search,
                           time_left=time_left,
                           settings=settings,
                           users=users_list,
                           dismissed_notices=dismissed_notices,
                           historico=history if history else [{"data": last_sync, "evento": "Status", "detalhes": "Aguardando sincronização."}])
