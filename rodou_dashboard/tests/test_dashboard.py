"""Testes do dashboard Flask - rotas e lógica de negócio."""

import pytest
import sys
import os
import json


class TestLogin:
    """Testes de autenticação."""

    def test_login_page_renders(self, client):
        response = client.get('/login')
        assert response.status_code == 200

    def test_login_with_invalid_credentials(self, client, app):
        with app.app_context():
            from app.models import db, User
            db.create_all()
        
        response = client.post('/login', data={
            'username': 'admin',
            'password': 'wrong_password'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with client.session_transaction() as sess:
            assert 'user' not in sess

    def test_protected_route_redirects_without_session(self, client):
        response = client.get('/', follow_redirects=False)
        assert response.status_code == 302
        assert '/login' in response.headers['Location']


class TestCompanies:
    """Testes de empresas."""

    def test_get_companies_empty(self, auth_client, app):
        with app.app_context():
            from app.models import db
            db.create_all()
        response = auth_client.get('/api/companies')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)

    def test_create_company(self, auth_client, app):
        with app.app_context():
            from app.models import db
            db.create_all()
        
        response = auth_client.post('/api/companies', json={
            'nome': 'Empresa Teste',
            'cnpj': '12.345.678/0001-90',
            'uf': 'SP',
            'cidade': 'São Paulo',
            'email': 'teste@teste.com',
            'telefone': '11999999999',
            'situacao': 'Ativa',
            'status': True,
            'origem': 'Manual'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data.get('status') == 'success' or data.get('id') is not None

    def test_create_company_duplicate_cnpj(self, auth_client, app):
        with app.app_context():
            from app.models import db, Company
            db.create_all()
            existing = Company(
                nome="Existente",
                cnpj="99.999.999/0001-99",
                cnpj_norm="99999999000199"
            )
            db.session.add(existing)
            db.session.commit()
        
        response = auth_client.post('/api/companies', json={
            'nome': 'Nova Empresa',
            'cnpj': '99.999.999/0001-99'
        })
        assert response.status_code in [400, 409]

    def test_create_company_missing_fields(self, auth_client, app):
        with app.app_context():
            from app.models import db
            db.create_all()
        
        response = auth_client.post('/api/companies', json={
            'nome': 'Empresa Sem CNPJ'
        })
        assert response.status_code >= 400

    def test_create_company_invalid_cnpj(self, auth_client, app):
        with app.app_context():
            from app.models import db
            db.create_all()
        
        response = auth_client.post('/api/companies', json={
            'nome': 'Empresa CNPJ Inválido',
            'cnpj': 'CNPJ_INVALIDO'
        })
        assert response.status_code >= 400


class TestTemplates:
    """Testes de templates de email."""

    def test_get_templates_empty(self, auth_client, app):
        with app.app_context():
            from app.models import db
            db.create_all()
        response = auth_client.get('/api/templates')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)

    def test_create_template(self, auth_client, app):
        with app.app_context():
            from app.models import db
            db.create_all()
        
        response = auth_client.post('/api/templates', json={
            'name': 'Template Teste',
            'subject': 'Assunto Teste',
            'body_html': '<h1>Teste</h1>'
        })
        assert response.status_code == 200

    def test_cannot_delete_default_template(self, auth_client, app):
        with app.app_context():
            from app.models import db, EmailTemplate
            template = EmailTemplate.query.filter_by(name='Padrão Registrale').first()
            template_id = template.id
        
        response = auth_client.delete(f'/api/templates/{template_id}')
        assert response.status_code == 400

    def test_create_template_missing_data(self, auth_client, app):
        with app.app_context():
            from app.models import db
            db.create_all()
        
        response = auth_client.post('/api/templates', json={
            'name': 'Sem Body HTML'
        })
        assert response.status_code >= 400

    def test_delete_nonexistent_template(self, auth_client, app):
        with app.app_context():
            from app.models import db
            db.create_all()
            
        response = auth_client.delete('/api/templates/999')
        assert response.status_code >= 400


class TestClearData:
    """Testes de limpeza de dados."""

    def test_clear_mentions(self, auth_client, app):
        with app.app_context():
            from app.models import db, Mention
            db.create_all()
            mention = Mention(id="test1", empresa="Teste", cnpj="123")
            db.session.add(mention)
            db.session.commit()
        
        response = auth_client.post('/api/admin/clear_data', json={'type': 'mentions'})
        assert response.status_code == 200
        
        with app.app_context():
            from app.models import Mention as M
            assert M.query.count() == 0

    def test_clear_requires_master_role(self, user_client, app):
        response = user_client.post('/api/admin/clear_data', json={'type': 'mentions'})
        assert response.status_code == 403
