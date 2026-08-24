import os
from flask import Flask
from flask_session import Session
from dotenv import load_dotenv
from .models import db, User, EmailTemplate
from sqlalchemy import event

def _init_default_data():
    """Inicializa dados padrão no banco (admin user e template de email)."""
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', role='master')
        admin.set_password('admin')
        db.session.add(admin)
        db.session.commit()
    if not EmailTemplate.query.filter_by(name='Padrão Registrale').first():
        template_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src', 'notification', 'templates', 'dashboard_template.html'
        )
        ro_dou_html_base = '''<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pesquisa DOU</title>
    <style>
        * { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; box-sizing: border-box; }
        body { margin: 0; padding: 20px; background-color: #f8f9fa; line-height: 1.6; color: #333; }
        h3 { color: #545b61; font-size: 16px; font-weight: normal; }
        .highlight, mark { background-color: #FFA !important; font-weight: bold; padding: 1px 4px; border-radius: 2px; color: #000; }
        .ext_header { max-width: 1200px; margin: 0 auto 30px auto; background-color: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1); padding: 30px; border-left: 4px solid #06acff; }
        .container { max-width: 1200px; margin: 0 auto 20px auto; background-color: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1); overflow: hidden; }
        .content { padding: 5px; }
        .result-header { background-color: #06acff; color: white; padding: 15px 20px; font-weight: 600; font-size: 16px; white-space: nowrap; overflow: hidden; position: relative; }
        .result-header:hover::after { content: attr(title); position: absolute; top: 100%; left: 0; right: 0; background-color: rgba(0, 0, 0, 0.9); color: white; padding: 10px; border-radius: 4px; font-size: 14px; font-weight: normal; z-index: 1000; white-space: normal; line-height: 1.4; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3); }
        .result-body { padding: 15px 5px 5px; }
        .section-marker { color: #06acff; font-size: 13px; font-weight: bold; padding: 0px; border-radius: 4px; }
        .document-meta { font-size: 13px; padding: 6px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #fafafa; text-decoration: none; color: #333; }
        .document-meta:hover { color: #003d82; }
        .abstract { background-color: #f8f9fa; padding: 10px 0; border-radius: 6px; margin-top: 2px; text-align: justify; font-size: 15px; line-height: 1.5; }
        .tag { display: inline-block; padding: 0.35em 0.65em; font-size: 0.75em; font-weight: 600; color: #333; line-height: 1; border-radius: 0.25rem; text-align: center; white-space: nowrap; vertical-align: baseline; }
        .recort { background-color: #ffebcc; }
        .date { color: #6c757d; font-size: 14px; font-weight: 500; text-align: right; margin-top: 10px; padding-top: 10px; }
        .footer { max-width: 1200px; margin: 20px auto; display: flex; flex-direction: row; justify-content: space-between; align-items: center; text-align: center; font-size: 12px; color: #b1b1b1; padding: 15px; background-color: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05); }
        .footer a { color: #06acff; text-decoration: none; }
        .separator { border:none; border-top:2px solid #06acff; }
        @media (max-width: 768px) { body { padding: 10px; } .container, .ext_header, .footer { margin: 0 0 15px 0; border-radius: 0; } .content { padding: 20px; } .result-header { white-space: normal; overflow: visible; } .footer { flex-direction: column; gap: 15px; } }
    </style>
</head>
<body>
    <div class="ext_header">
        <h2 style="color: #2563eb; margin:0;">[TITLE]</h2>
        <p style="color: #333; margin-top:10px;">[MESSAGE]</p>
    </div>
    {content}
    <section>
        <div class="footer">
            <small>Esta pesquisa foi gerada automaticamente pelo
                <a href="https://gestaogovbr.github.io/Ro-dou/"> Ro-DOU </a>
                e não substitui a verificação no Diário Oficial da União (D.O.U.).
            </small>
        </div>
    </section>
</body>
</html>'''

        body_html = ro_dou_html_base.replace("[TITLE]", "Notificação Registrale").replace("[MESSAGE]", "Foram detectadas as seguintes menções no Diário Oficial da União (DOU):")
        
        try:
            if os.path.exists(template_path):
                with open(template_path, 'r', encoding='utf-8') as f:
                    body_html = f.read()
        except Exception:
            pass
        template = EmailTemplate(
            name='Padrão Registrale',
            subject='[ro-dou] Relatório de Menções',
            body_html=body_html
        )
        db.session.add(template)
        db.session.commit()
    
    if not EmailTemplate.query.filter_by(name='Relatório Mensal Registrale').first():
        monthly_html = ro_dou_html_base.replace("[TITLE]", "Relatório Consolidado de Menções").replace("[MESSAGE]", "Abaixo constam as publicações identificadas pelo sistema Registrale no período consolidado:")
        monthly_template = EmailTemplate(
            name='Relatório Mensal Registrale',
            subject='Registrale - Relatório Mensal',
            body_html=monthly_html
        )
        db.session.add(monthly_template)
        db.session.commit()

def create_app(config=None):
    app = Flask(__name__,
                template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'))
    
    # Configuração base
    app.secret_key = os.getenv("SECRET_KEY", "rodou-secret-key-123")
    
    DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data'))
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Carrega variáveis persistidas no volume montado /data/.env
    _data_env = os.path.join(DATA_DIR, '.env')
    if os.path.exists(_data_env):
        try:
            load_dotenv(_data_env, override=True)
        except Exception:
            pass
    
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(DATA_DIR, 'database.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config.update(
        SESSION_TYPE='filesystem',
        SESSION_FILE_DIR=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'flask_sessions')),
        SESSION_PERMANENT=True,
        SESSION_REFRESH_EACH_REQUEST=False,
        SESSION_USE_SIGNER=True,
        SESSION_COOKIE_NAME='registrale_secure_sid',
        SESSION_COOKIE_SAMESITE='Strict',
        SESSION_COOKIE_HTTPONLY=True,
    )
    
    if config:
        app.config.update(config)
    
    # Inicializar extensões
    db.init_app(app)

    # Pragmas SQLite para performance e resiliência
    with app.app_context():
        @event.listens_for(db.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    Session(app)
    
    # Registrar Blueprints (serão criados nos próximos passos)
    from .routes.auth import auth_bp
    from .routes.dags import dags_bp
    from .routes.templates_bp import templates_bp
    from .routes.companies import companies_bp
    from .routes.mentions import mentions_bp
    from .routes.admin import admin_bp
    from .routes.exports import exports_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(dags_bp, url_prefix='/api')
    app.register_blueprint(templates_bp, url_prefix='/api')
    app.register_blueprint(companies_bp, url_prefix='/api')
    app.register_blueprint(mentions_bp, url_prefix='/api')
    app.register_blueprint(admin_bp, url_prefix='/api')
    app.register_blueprint(exports_bp, url_prefix='/api')
    
    # Inicializar dados padrão
    with app.app_context():
        db.create_all()
        _init_default_data()
        
    # Limpeza de DAGs temporárias órfãs na inicialização
    try:
        from .services.dag_config_service import cleanup_orphaned_temp_dags
        cleanup_orphaned_temp_dags(max_age_seconds=0, force_all=True)
    except Exception as e:
        app.logger.warning(f"Erro ao limpar DAGs temporárias na inicialização: {e}")

    # Inicializar scheduler em background para Google Sheets (se não for modo teste)
    if not app.config.get('TESTING'):
        try:
            from .services.sheets_service import start_sheets_scheduler
            start_sheets_scheduler(app)
        except Exception as e:
            app.logger.error(f"Erro ao iniciar scheduler do Google Sheets: {e}")

    @app.after_request
    def add_header(response):
        """Previne o cache do navegador para evitar que páginas logadas apareçam após logout."""
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    
    return app

