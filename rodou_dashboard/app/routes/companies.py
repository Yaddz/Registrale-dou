from flask import Blueprint, request, jsonify, session
from .auth import login_required
from ..models import db, Company
from ..services.dag_config_service import get_monitored_cnpjs, normalize_cnpj
from ..services.mention_service import get_real_mentions

companies_bp = Blueprint('companies', __name__)

def get_companies_data():
    active_cnpjs = get_monitored_cnpjs()
    # current_app can be used if we need app context, but we are inside request
    all_metadata = Company.query.all()
    empresas = []
    for meta in all_metadata:
        cnpj_bruto = meta.cnpj
        cnpj_norm = normalize_cnpj(cnpj_bruto)
        is_active = cnpj_norm in active_cnpjs
        empresas.append({
            "id": meta.id,
            "nome": meta.nome or "N/A",
            "cnpj": cnpj_bruto,
            "uf": meta.uf or "N/A",
            "cidade": meta.cidade or "N/A",
            "email": meta.email or "N/A",
            "telefone": meta.telefone or "N/A",
            "situacao": meta.situacao or "Ativa",
            "status": is_active,
            "origem": meta.origem
        })
    return sorted(empresas, key=lambda x: x['nome'])

@companies_bp.route('/companies', methods=['GET', 'POST'])
@login_required
def api_companies():
    if request.method == 'GET':
        return jsonify(get_companies_data())
    elif request.method == 'POST':
        data = request.json
        if not data.get('cnpj'):
            return jsonify({"status": "error", "message": "CNPJ não informado."}), 400
        try:
            cnpj_norm = normalize_cnpj(data.get('cnpj'))
            if len(cnpj_norm) != 14:
                return jsonify({"status": "error", "message": "CNPJ inválido."}), 400
            existing = Company.query.filter_by(cnpj_norm=cnpj_norm).first()
            if existing:
                return jsonify({"status": "error", "message": "CNPJ já cadastrado."}), 400
            
            new_comp = Company(
                nome=data.get('nome', 'N/A'),
                cnpj=data.get('cnpj'),
                cnpj_norm=cnpj_norm,
                uf=data.get('uf', 'N/A'),
                cidade=data.get('cidade', 'N/A'),
                email=data.get('email', 'N/A'),
                telefone=data.get('telefone', 'N/A'),
                situacao=data.get('situacao', 'Ativa'),
                status=data.get('status', True),
                origem=data.get('origem', 'Manual')
            )
            db.session.add(new_comp)
            db.session.commit()
            return jsonify({"status": "success", "message": "Empresa adicionada!"})
        except Exception as e:
            db.session.rollback()
            return jsonify({"status": "error", "message": str(e)}), 500

@companies_bp.route('/companies/<int:cnpj_id>', methods=['PUT'])
@login_required
def update_company(cnpj_id):
    if session['user']['role'] != 'master':
        return jsonify({"status": "error", "message": "Acesso negado."}), 403
    company = Company.query.get(cnpj_id)
    if not company:
        return jsonify({"status": "error", "message": "Empresa não encontrada."}), 404
    data = request.json
    try:
        company.nome = data.get('nome', company.nome)
        company.email = data.get('email', company.email)
        company.telefone = data.get('telefone', company.telefone)
        company.situacao = data.get('situacao', company.situacao)
        company.status = data.get('status', company.status)
        company.origem = 'Manual'
        db.session.commit()
        return jsonify({"status": "success", "message": "Empresa atualizada!"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@companies_bp.route('/company_history/<path:cnpj>')
@login_required
def company_history(cnpj):
    all_mentions = get_real_mentions()
    cnpj_norm = normalize_cnpj(cnpj)
    history = [m for m in all_mentions if m['cnpj_norm'] == cnpj_norm]
    return jsonify(history)
