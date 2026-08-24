from flask import Blueprint, request, session, redirect, url_for, render_template, jsonify
from datetime import datetime, timezone, timedelta
from functools import wraps
from ..models import db, User, Settings, SyncHistory, Company
from ..services.mention_service import get_real_mentions, get_mentions_kpis
from ..services.dag_config_service import get_monitored_cnpjs, get_last_search_time, get_next_search_time
import os
import glob

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        # In a real app, from flask import current_app to get permanent_session_lifetime
        if user and user.check_password(password):
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
    expires_at = session.get('expires_at')
    if expires_at and datetime.now(timezone(timedelta(hours=-3))).timestamp() > expires_at:
        session.clear()
        return redirect(url_for('auth.login'))

    is_master = session['user']['role'] == 'master'
    
    settings = {"smtp":{}, "api_keys":{}, "google_sheets":{}, "inlabs":{}}
    users_list = []
    history = []
    
    if is_master:
        settings_record = Settings.query.filter_by(key='global_settings').first()
        if settings_record:
            db_settings = settings_record.get_value()
            if "inlabs" not in db_settings:
                db_settings["inlabs"] = {}
            settings.update(db_settings)
        users_list = [{"username": u.username, "role": u.role} for u in User.query.all()]
        
    history = [h.to_dict() for h in SyncHistory.query.order_by(SyncHistory.id.desc()).limit(50).all()]
    total_m, hoje_m, mes_m = get_mentions_kpis()
    
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
        if not yaml_files: yaml_files = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_part_*.yaml"))
        if not yaml_files:
            base = get_base_yaml_path()
            if os.path.exists(base): yaml_files = [base]
        last_sync = "N/A"
        if yaml_files:
            mtime = os.path.getmtime(yaml_files[0])
            last_sync = datetime.fromtimestamp(mtime, timezone(timedelta(hours=-3))).strftime('%d/%m %H:%M')

    last_search = get_last_search_time()
    next_search = get_next_search_time()
    
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

    return render_template('index.html', 
                           user=session['user'],
                           init_data=init_data,
                           last_sync=last_sync,
                           last_search=last_search,
                           next_search=next_search,
                           time_left=time_left,
                           settings=settings,
                           users=users_list,
                           historico=history if history else [{"data": last_sync, "evento": "Status", "detalhes": "Aguardando sincronização."}])
