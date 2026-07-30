import os
from flask import Flask
from flask_session import Session
from .models import db, User, EmailTemplate

def _init_default_data():
    """Inicializa dados padrão no banco (admin user e template de email)."""
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', role='master')
        admin.set_password('admin')
        db.session.add(admin)
        db.session.commit()
    if not EmailTemplate.query.filter_by(name='Padrão Registrale').first():
        template = EmailTemplate(
            name='Padrão Registrale',
            subject='[ro-dou] Relatório de Menções',
            body_html='<p>Template padrão</p>'
        )
        db.session.add(template)
        db.session.commit()

def create_app(config=None):
    app = Flask(__name__,
                template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'))
    
    # Configuração base
    app.secret_key = os.getenv("SECRET_KEY", "rodou-secret-key-123")
    
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data')
    os.makedirs(DATA_DIR, exist_ok=True)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(DATA_DIR, 'database.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config.update(
        SESSION_TYPE='filesystem',
        SESSION_FILE_DIR=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'flask_sessions'),
        SESSION_PERMANENT=True,
        SESSION_REFRESH_EACH_REQUEST=False,
        SESSION_USE_SIGNER=True,
    )
    
    if config:
        app.config.update(config)
    
    # Inicializar extensões
    db.init_app(app)
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
        
    @app.after_request
    def add_header(response):
        """Previne o cache do navegador para evitar que páginas logadas apareçam após logout."""
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    
    return app
