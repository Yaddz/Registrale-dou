from flask import Blueprint, request, jsonify, session
from .auth import login_required
from ..models import db, EmailTemplate

templates_bp = Blueprint('templates', __name__)

@templates_bp.route('/templates', methods=['GET', 'POST'])
@login_required
def manage_templates():
    if request.method == 'GET':
        templates = EmailTemplate.query.all()
        return jsonify([{"id": t.id, "name": t.name, "subject": t.subject, "body_html": t.body_html} for t in templates])
        
    if request.method == 'POST':
        if session['user']['role'] != 'master': return jsonify({"status": "error"}), 403
        data = request.json
        if not data.get('name') or not data.get('body_html'):
            return jsonify({"status": "error", "message": "Nome e corpo HTML são obrigatórios."}), 400
        try:
            template = None
            if data.get('id'):
                template = db.session.get(EmailTemplate, data.get('id'))
            if not template:
                template = EmailTemplate.query.filter_by(name=data.get('name')).first()
            if not template:
                template = EmailTemplate(name=data.get('name'))
                db.session.add(template)
            else:
                template.name = data.get('name')
            template.subject = data.get('subject', '')
            template.body_html = data.get('body_html', '')
            db.session.commit()
            return jsonify({"status": "success", "message": "Template salvo!"})
        except Exception as e:
            db.session.rollback()
            return jsonify({"status": "error", "message": str(e)}), 500

@templates_bp.route('/templates/<int:t_id>', methods=['DELETE'])
@login_required
def delete_template(t_id):
    if session['user']['role'] != 'master': return jsonify({"status": "error"}), 403
    try:
        template = db.session.get(EmailTemplate, t_id)
        if not template:
            return jsonify({"status": "error", "message": "Template não encontrado."}), 404
        if template.name in ('Padrão Registrale', 'Relatório Mensal Registrale'):
            return jsonify({"status": "error", "message": "Este template do sistema não pode ser excluído."}), 400
        db.session.delete(template)
        db.session.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
