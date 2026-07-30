from flask import Blueprint, jsonify, request
from .auth import login_required
from ..services.mention_service import get_real_mentions
from ..models import db, Mention

mentions_bp = Blueprint('mentions', __name__)

@mentions_bp.route('/mentions', methods=['GET'])
@login_required
def api_mentions():
    return jsonify(get_real_mentions())

@mentions_bp.route('/mentions', methods=['DELETE'])
@login_required
def delete_mentions():
    data = request.json
    if not data or 'ids' not in data:
        return jsonify({"status": "error", "message": "Nenhum ID fornecido."}), 400
    
    ids = data['ids']
    try:
        Mention.query.filter(Mention.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({"status": "success", "message": f"{len(ids)} menções excluídas."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
