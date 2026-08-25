import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import create_app
from app.models import db as _db, User

@pytest.fixture(scope='session', autouse=True)
def preserve_dag_confs():
    target_yaml = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'dag_confs', 'Pesquisa_cnpj.yaml'))
    initial_content = None
    if os.path.exists(target_yaml):
        with open(target_yaml, 'r', encoding='utf-8') as f:
            initial_content = f.read()
    yield
    if initial_content is not None and os.path.exists(target_yaml):
        with open(target_yaml, 'w', encoding='utf-8') as f:
            f.write(initial_content)

@pytest.fixture
def app():
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False
    })
    return app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth_client(client, app):
    with app.app_context():
        _db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', role='master')
            admin.set_password('admin')
            _db.session.add(admin)
            _db.session.commit()
            
    with client.session_transaction() as sess:
        sess['user'] = {'username': 'admin', 'role': 'master'}
        sess['expires_at'] = 9999999999
    
    return client

@pytest.fixture
def user_client(client, app):
    with app.app_context():
        _db.create_all()
        if not User.query.filter_by(username='common_user').first():
            user = User(username='common_user', role='user')
            user.set_password('pass123')
            _db.session.add(user)
            _db.session.commit()
            
    with client.session_transaction() as sess:
        sess['user'] = {'username': 'common_user', 'role': 'user'}
        sess['expires_at'] = 9999999999
    
    return client
