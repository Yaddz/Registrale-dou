from flask import Blueprint, request, jsonify, session
from sqlalchemy import func
from .auth import login_required
from ..models import db, Company, Mention
from ..services.dag_config_service import normalize_cnpj, rebuild_yaml_from_db
from ..services.mention_service import get_real_mentions

companies_bp = Blueprint('companies', __name__)

def get_companies_data():
    all_metadata = Company.query.all()
    
    # Mapeamento de contagem agregada de menções por CNPJ
    mention_counts = {}
    try:
        norm_counts = db.session.query(Mention.cnpj_norm, func.count(Mention.id)).filter(Mention.cnpj_norm.isnot(None)).group_by(Mention.cnpj_norm).all()
        for c_norm, cnt in norm_counts:
            if c_norm:
                mention_counts[c_norm] = cnt
        raw_counts = db.session.query(Mention.cnpj, func.count(Mention.id)).filter(Mention.cnpj.isnot(None)).group_by(Mention.cnpj).all()
        for c_raw, cnt in raw_counts:
            if c_raw:
                c_clean = normalize_cnpj(c_raw)
                if c_clean and c_clean not in mention_counts:
                    mention_counts[c_clean] = cnt
    except Exception:
        pass

    empresas = []
    for meta in all_metadata:
        cnpj_bruto = meta.cnpj
        cnpj_norm = normalize_cnpj(cnpj_bruto)
        total_mencoes = mention_counts.get(cnpj_norm, 0)
        empresas.append({
            "id": meta.id,
            "nome": meta.nome or "N/A",
            "cnpj": cnpj_bruto,
            "cnpj_norm": cnpj_norm,
            "status": meta.status,
            "origem": meta.origem,
            "total_mencoes": total_mencoes
        })
    return sorted(empresas, key=lambda x: (x['nome'] or '').lower())

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
                status=data.get('status', True),
                origem=data.get('origem', 'Manual')
            )
            db.session.add(new_comp)
            db.session.commit()
            
            # Sincronização inteligente imediata do YAML da rotina padrão
            rebuild_yaml_from_db()
            
            return jsonify({"status": "success", "message": "Empresa adicionada!"})
        except Exception as e:
            db.session.rollback()
            return jsonify({"status": "error", "message": str(e)}), 500

@companies_bp.route('/companies/<int:cnpj_id>', methods=['PUT', 'DELETE'])
@login_required
def update_company(cnpj_id):
    if session['user']['role'] != 'master':
        return jsonify({"status": "error", "message": "Acesso negado."}), 403
    company = db.session.get(Company, cnpj_id)
    if not company:
        return jsonify({"status": "error", "message": "Empresa não encontrada."}), 404
        
    if request.method == 'DELETE':
        try:
            db.session.delete(company)
            db.session.commit()
            rebuild_yaml_from_db()
            return jsonify({"status": "success", "message": "Empresa removida com sucesso!"})
        except Exception as e:
            db.session.rollback()
            return jsonify({"status": "error", "message": str(e)}), 500

    data = request.json
    try:
        if 'nome' in data:
            company.nome = data.get('nome') or company.nome
        if 'status' in data:
            company.status = bool(data.get('status'))
        if 'origem' in data:
            company.origem = data.get('origem', company.origem)
        db.session.commit()
        rebuild_yaml_from_db()
        return jsonify({"status": "success", "message": "Empresa atualizada!"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@companies_bp.route('/companies/search', methods=['GET'])
@login_required
def search_companies():
    """Busca rápida de empresas cadastradas para a barra de pesquisa das rotinas."""
    q = (request.args.get('q') or '').strip().lower()
    q_norm = normalize_cnpj(q)
    
    query = Company.query
    if q:
        if q_norm:
            query = query.filter(
                (Company.nome.ilike(f"%{q}%")) | (Company.cnpj_norm.like(f"%{q_norm}%")) | (Company.cnpj.ilike(f"%{q}%"))
            )
        else:
            query = query.filter(Company.nome.ilike(f"%{q}%"))
            
    companies = query.limit(30).all()
    return jsonify([{
        "id": c.id,
        "nome": c.nome,
        "cnpj": c.cnpj,
        "cnpj_norm": c.cnpj_norm,
        "origem": c.origem,
        "status": c.status
    } for c in companies])

@companies_bp.route('/sheets/cnpjs', methods=['GET'])
@login_required
def get_sheets_cnpjs_route():
    """Retorna os CNPJs da planilha do Google Sheets (da API do Sheets ou da base local)."""
    cnpjs = []
    seen = set()
    
    # 1. Tentar buscar diretamente da API do Google Sheets se configurada
    try:
        from ..services.sheets_service import get_sheet_cnpjs_list
        sheet_cnpjs = get_sheet_cnpjs_list()
        for item in sheet_cnpjs:
            cn = item.get('cnpj_norm') or item.get('cnpj')
            if cn and cn not in seen:
                seen.add(cn)
                cnpjs.append(item)
    except Exception as e:
        logger.warning(f"Não foi possível buscar diretamente da API do Sheets: {e}")
        
    # 2. Complementar com empresas já salvas no banco de dados com origem 'Planilha'
    try:
        all_comps = Company.query.all()
        for comp in all_comps:
            orig = (comp.origem or '').lower()
            if 'planilha' in orig or 'sheet' in orig:
                cn = comp.cnpj_norm or (comp.cnpj or '').replace('.', '').replace('/', '').replace('-', '').strip()
                if cn and cn not in seen:
                    seen.add(cn)
                    cnpjs.append({
                        "cnpj": comp.cnpj or comp.cnpj_norm,
                        "cnpj_norm": comp.cnpj_norm or cn,
                        "nome": comp.nome or 'N/A'
                    })
    except Exception as db_err:
        logger.warning(f"Erro ao buscar empresas da base local: {db_err}")
        
    return jsonify({"status": "success", "data": cnpjs, "total": len(cnpjs)})



@companies_bp.route('/company_history/<path:cnpj>')
@login_required
def company_history(cnpj):
    all_mentions = get_real_mentions()
    cnpj_norm = normalize_cnpj(cnpj)
    history = [m for m in all_mentions if m['cnpj_norm'] == cnpj_norm]
    return jsonify(history)
@companies_bp.route('/google_sheets/test', methods=['POST'])
@login_required
def test_google_sheets_route():
    """Testa credenciais e conexão com a planilha privada do Google Sheets."""
    from ..models import Settings
    from ..services.sheets_service import test_sheets_connection

    data = request.get_json(silent=True) or {}
    
    credentials_json = data.get('credentials_json')
    spreadsheet_url = data.get('spreadsheet_url')
    sheet_name = data.get('sheet_name')

    # Fallback para configurações salvas no banco caso não enviadas no body
    if not credentials_json or not spreadsheet_url:
        settings_record = Settings.query.filter_by(key='global_settings').first()
        if settings_record:
            gs_saved = settings_record.get_value().get('google_sheets', {})
            credentials_json = credentials_json or gs_saved.get('credentials_json')
            spreadsheet_url = spreadsheet_url or gs_saved.get('spreadsheet_url')
            sheet_name = sheet_name or gs_saved.get('sheet_name')

    if not spreadsheet_url:
        return jsonify({"status": "error", "message": "URL ou ID da planilha não informado."}), 400
    if not credentials_json:
        return jsonify({"status": "error", "message": "Credenciais da Conta de Serviço (JSON) não informadas."}), 400

    try:
        result = test_sheets_connection(credentials_json, spreadsheet_url, sheet_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@companies_bp.route('/google_sheets/sync', methods=['POST'])
@login_required
def sync_google_sheets_route():
    """Executa a sincronização da planilha Google Sheets via API para o banco SQLite."""
    from ..services.sheets_service import executar_sincronizacao_sheets

    data = request.get_json(silent=True) or {}
    config_override = data.get('google_sheets') if data.get('google_sheets') else None

    try:
        from flask import current_app
        result = executar_sincronizacao_sheets(app=current_app, config_override=config_override)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def _match_origin(target_origin, comp_origin):
    """Verifica de forma robusta se a origem da empresa corresponde à origem alvo."""
    if not target_origin:
        return False
    t_norm = target_origin.lower().replace('ã', 'a').replace('ç', 'c').replace(' ', '').replace('_', '').replace('-', '')
    c_raw = (comp_origin or 'manual').lower().replace('ã', 'a').replace('ç', 'c').replace(' ', '').replace('_', '').replace('-', '')
    
    if 'gestao' in t_norm and 'gestao' in c_raw:
        return True
    if ('planilha' in t_norm or 'sheet' in t_norm) and ('planilha' in c_raw or 'sheet' in c_raw):
        return True
    if 'manual' in t_norm and ('manual' in c_raw or not comp_origin):
        return True
    return t_norm in c_raw or c_raw in t_norm


@companies_bp.route('/companies/unmonitor_by_origin', methods=['POST'])
@login_required
def unmonitor_by_origin():
    """Desmarca do monitoramento (status=False) as empresas das origens selecionadas."""
    data = request.json or {}
    origins = data.get('origins', [])
    if not origins:
        return jsonify({"status": "error", "message": "Nenhuma origem selecionada."}), 400
        
    try:
        all_companies = Company.query.filter_by(status=True).all()
        updated_count = 0
        
        for comp in all_companies:
            if any(_match_origin(o, comp.origem) for o in origins):
                comp.status = False
                updated_count += 1
                
        db.session.commit()
        rebuild_yaml_from_db()
        
        return jsonify({
            "status": "success",
            "message": f"{updated_count} empresa(s) desmarcada(s) do monitoramento com sucesso.",
            "updated_count": updated_count
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@companies_bp.route('/companies/toggle_origin_monitoring', methods=['POST'])
@login_required
def toggle_origin_monitoring():
    """Ativa ou desativa o monitoramento (status=True/False) das empresas de uma origem específica."""
    data = request.json or {}
    origin = data.get('origin')
    status = bool(data.get('status', True))
    if not origin:
        return jsonify({"status": "error", "message": "Origem não informada."}), 400
        
    try:
        all_companies = Company.query.all()
        updated_count = 0
        for comp in all_companies:
            if _match_origin(origin, comp.origem):
                if comp.status != status:
                    comp.status = status
                    updated_count += 1
                    
        db.session.commit()
        rebuild_yaml_from_db()
        action = "ativadas" if status else "desativadas"
        return jsonify({
            "status": "success",
            "message": f"{updated_count} empresa(s) do {origin} foram {action} no monitoramento.",
            "updated_count": updated_count
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500





