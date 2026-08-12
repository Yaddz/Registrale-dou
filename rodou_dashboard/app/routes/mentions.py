from flask import Blueprint, jsonify, request
from .auth import login_required
from ..services.mention_service import get_real_mentions, clear_mentions_cache
from ..models import db, Mention, Settings

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
        from ..models import DeletedMention
        for mid in ids:
            if not DeletedMention.query.get(mid):
                db.session.add(DeletedMention(id=mid))
        
        Mention.query.filter(Mention.id.in_(ids)).delete(synchronize_session=False)
        
        cache_setting = Settings.query.filter_by(key='mentions_cache_meta').first()
        if cache_setting:
            cache_setting.set_value({"last_parsed_at": 0})
            
        db.session.commit()
        clear_mentions_cache()
        return jsonify({"status": "success", "message": f"{len(ids)} menções excluídas."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
