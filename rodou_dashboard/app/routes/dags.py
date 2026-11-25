from flask import Blueprint, request, jsonify, session, current_app
import os
import yaml
import glob
import re
import threading
import requests
import logging
from datetime import datetime, timezone, timedelta
from .auth import login_required
from ..models import db, Mention, Company, SyncHistory
from ..services.dag_config_service import get_routines, get_dag_confs_path, touch_dag_generator
from ..runtime.executor import get_executor, normalize_date_str

# Assumindo a mesma estrutura
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

dags_bp = Blueprint('dags', __name__)


def _is_safe_routine_name(name) -> bool:
    """Nome de arquivo de rotina seguro: relativo a dag_confs, sem '..',
    sem caminho absoluto e com extensão YAML (evita path traversal)."""
    if not isinstance(name, str) or not name.strip():
        return False
    n = name.strip().replace('\\', '/')
    if n.startswith('/') or os.path.isabs(n):
        return False
    if any(part in ('..', '') for part in n.split('/')):
        return False
    return n.lower().endswith(('.yaml', '.yml'))


@dags_bp.before_request
def _validate_routine_file_names():
    names = []
    if request.view_args and 'file' in request.view_args:
        names.append(request.view_args['file'])
    if request.is_json:
        body = request.get_json(silent=True) or {}
        if isinstance(body, dict):
            if body.get('file'):
                names.append(body.get('file'))
            routines = body.get('routines')
            if isinstance(routines, list):
                names.extend(routines)
    for n in names:
        if not _is_safe_routine_name(n):
            return jsonify({"status": "error", "message": "Nome de arquivo de rotina inválido."}), 400

# Parâmetros padrão iguais à baseline: Seções 1/2/3 + Edição Extra
DEFAULT_DOU_SECTIONS = ["SECAO_1", "SECAO_2", "SECAO_3", "EDICAO_EXTRA"]


def add_history_event(evento, detalhes):
    from ..models import SyncHistory
    SyncHistory.log_event(evento, detalhes)

def _fallback_sources():
    """Fonte das buscas sem INLABS conforme ``inlabs_fallback``."""
    try:
        from ..runtime.pdf_search import FALLBACK_PDF, get_fallback_mode
        if get_fallback_mode() == FALLBACK_PDF:
            return ["INLABS"]
    except Exception:
        pass
    return ["DOU"]


def _describe_local_fallback_source() -> str:
    """Rótulo legível da fonte de contingência ativa."""
    try:
        from ..runtime.pdf_search import FALLBACK_PDF, get_fallback_mode
        if get_fallback_mode() == FALLBACK_PDF:
            return "PDF integral + API do DOU"
    except Exception:
        pass
    return "API Oficial do DOU"


def _extract_sources_used_from_runs(run_ids) -> str:
    """Extrai os rótulos ``source_used`` gravados nos ``JobRun`` locais."""
    if not run_ids:
        return ""
    try:
        from ..models import JobRun
        labels = []
        for job in JobRun.query.filter(JobRun.id.in_(list(run_ids))).all():
            for block in job.get_resultado():
                if isinstance(block, dict):
                    src = (block.get("source_used") or "").strip()
                    if src and src not in labels:
                        labels.append(src)
        return ", ".join(labels)
    except Exception:
        return ""


def _summarize_coverage_from_runs(run_ids):
    """Resume a cobertura por seção das execuções: ``(texto, pendentes)``.

    Distingue "dia sem menções" (todas as seções cobertas) de "busca incompleta"
    (``pendentes`` não vazio).
    """
    if not run_ids:
        return "", []
    try:
        from ..models import JobRun
        by_label = {}
        notes = []
        for job in JobRun.query.filter(JobRun.id.in_(list(run_ids))).all():
            for block in job.get_resultado():
                if not isinstance(block, dict):
                    continue
                for note in block.get("notes") or []:
                    if note not in notes:
                        notes.append(note)
                for cov in block.get("coverage") or []:
                    if not isinstance(cov, dict):
                        continue
                    label = cov.get("label") or cov.get("section")
                    prev = by_label.get(label)
                    # pendente prevalece sobre os demais estados
                    if prev is None or cov.get("status") == "pendente":
                        by_label[label] = cov
        parts, pending = [], []
        names = {"coberta": "ok", "sem_edicao": "sem edição", "pendente": "PENDENTE"}
        for label, cov in by_label.items():
            parts.append(f"{label}: {names.get(cov.get('status'), cov.get('status'))} ({cov.get('source')})")
            if cov.get("status") == "pendente":
                pending.append(label)
        text = "; ".join(parts)
        if notes:
            text += (" | Avisos: " if text else "Avisos: ") + " ".join(notes)
        return text, pending
    except Exception:
        return "", []


def _is_pdf_mention_id(mention_id) -> bool:
    return str(mention_id or "").split("_", 1)[-1].startswith("pdf-")


def _section_key(secao) -> str:
    """Seção normalizada para a chave entre fontes (PDF: "DOU - Edição Extra"; API: "... Extra A")."""
    low = re.sub(r"\s+", " ", str(secao or "")).strip().lower()
    return "extra" if "extra" in low else low


def reconcile_mentions_across_sources(mentions):
    """Evita duplicar a mesma menção quando muda a fonte (PDF x API do DOU).

    O id da menção depende da fonte (``pdf-<data>-<jornal>-<página>`` x id da API), então
    uma nova tentativa do dia que troque de fonte criaria outra linha e outro e-mail. A
    chave estável entre fontes é (CNPJ, data, seção): uma menção de PDF e uma da API com a
    mesma chave são a mesma publicação. Cada linha existente de outra fonte "consome" no
    máximo uma menção nova (vários atos da mesma empresa/seção/dia continuam distintos).

    Retorna ``(menções_a_gravar, ids_ja_notificados)``: a API substitui a linha de PDF (a
    linha antiga é removida da sessão) e o PDF é descartado se já existe a da API; os ids
    devolvidos já foram gravados antes, logo não geram novo e-mail.
    """
    from ..models import Mention, db

    mentions = list(mentions or [])
    ids = [m["id"] for m in mentions if m.get("id")]
    existing_ids = {r.id for r in Mention.query.filter(Mention.id.in_(ids)).all()} if ids else set()
    norms = {m.get("cnpj_norm") for m in mentions if m.get("cnpj_norm")}
    dates = {m.get("data") for m in mentions if m.get("data")}
    if not norms or not dates:
        return mentions, set()

    by_key = {}
    for row in Mention.query.filter(Mention.cnpj_norm.in_(norms), Mention.data.in_(dates)).all():
        by_key.setdefault((row.cnpj_norm, row.data, _section_key(row.secao)), []).append(row)

    kept, already_notified = [], set()
    for m in mentions:
        if m.get("id") in existing_ids:
            kept.append(m)
            continue
        key = (m.get("cnpj_norm"), m.get("data"), _section_key(m.get("secao")))
        incoming_pdf = _is_pdf_mention_id(m.get("id"))
        match = next((r for r in by_key.get(key, []) if _is_pdf_mention_id(r.id) != incoming_pdf), None)
        if match is None:
            kept.append(m)
            continue
        by_key[key].remove(match)
        if incoming_pdf:
            continue  # a API já gravou esta publicação: o PDF não acrescenta nada
        db.session.delete(match)  # a API (com link e título corretos) substitui a linha de PDF
        already_notified.add(m["id"])
        kept.append(m)
    return kept, already_notified


def extract_mentions_from_results(results_raw_list, cnpj_map=None):
    """Extrai e normaliza menções a partir de uma lista de dicionários `result`."""
    import hashlib
    from datetime import datetime, timezone, timedelta
    from ..services.mention_service import clean_abstract_for_dashboard, normalize_cnpj
    from ..models import Company

    extracted_mentions = []
    seen_ids = set()

    if cnpj_map is None:
        companies = Company.query.with_entities(Company.cnpj_norm, Company.nome, Company.cnpj).all()
        cnpj_map = {c.cnpj_norm: c.nome for c in companies if c.cnpj_norm}
        cnpj_map.update({c.cnpj: c.nome for c in companies if c.cnpj})

    now_str = datetime.now(timezone(timedelta(hours=-3))).strftime('%Y-%m-%d %H:%M:%S')
    for raw_result in results_raw_list:
        if not isinstance(raw_result, dict):
            continue
        group_list = []
        if 'single_group' in raw_result and isinstance(raw_result['single_group'], dict):
            group_list.append(raw_result['single_group'])
        else:
            for _, g_val in raw_result.items():
                if isinstance(g_val, dict):
                    group_list.append(g_val)
        if not group_list and raw_result:
            group_list.append(raw_result)

        for results in group_list:
            for cnpj_raw_key, content_group in results.items():
                if not isinstance(content_group, dict):
                    continue
                cnpjs = [c.strip() for c in cnpj_raw_key.split(',')]
                for cnpj_log in cnpjs:
                    cnpj_norm = normalize_cnpj(cnpj_log)
                    for _, depts in content_group.items():
                        if not isinstance(depts, list):
                            continue
                        for pub in depts:
                            if not isinstance(pub, dict):
                                continue
                            raw_abstract = pub.get('abstract', '')
                            raw_date = pub.get('date', '')
                            hash_str = f"{cnpj_norm}_{raw_date}_{raw_abstract}"
                            fallback_id = hashlib.md5(hash_str.encode('utf-8', errors='ignore')).hexdigest()
                            pub_id = pub.get('id') or fallback_id
                            unique_key = f"{cnpj_norm}_{pub_id}"

                            if unique_key in seen_ids:
                                continue
                            seen_ids.add(unique_key)

                            empresa_nome = cnpj_map.get(cnpj_norm) or cnpj_map.get(cnpj_log) or cnpj_log
                            formatted_trecho = clean_abstract_for_dashboard(raw_abstract, cnpj_norm)

                            extracted_mentions.append({
                                "id": unique_key,
                                "empresa": empresa_nome,
                                "cnpj": cnpj_log,
                                "cnpj_norm": cnpj_norm,
                                "secao": pub.get('section', 'DOU'),
                                "data": pub.get('date', 'N/A'),
                                "detected_at": now_str,
                                "trecho": formatted_trecho,
                                "link": pub.get('href', '#')
                            })

    return extracted_mentions


def fetch_mentions_from_dag_run(dag_id, dag_run_id, cnpj_map=None):
    """Extrai as menções de uma execução concluída usando a camada Executor."""
    raw_items = get_executor().result(dag_run_id, routine=dag_id)
    results_raw_list = []
    for item in raw_items or []:
        if isinstance(item, dict):
            res_dict = item.get('result', item)
            if isinstance(res_dict, dict):
                results_raw_list.append(res_dict)
    return extract_mentions_from_results(results_raw_list, cnpj_map=cnpj_map)

@dags_bp.route('/routines', methods=['GET', 'POST'])
@login_required
def manage_routines():
    if request.method == 'GET':
        return jsonify(get_routines())
    
    if session['user']['role'] != 'master': return jsonify({"status": "error", "message": "Acesso negado"}), 403
    data = request.get_json(silent=True) or {}
    
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"status": "error", "message": "Nome da rotina é obrigatório."}), 400
    
    terms = data.get('terms', [])
    if not terms or len(terms) == 0:
        return jsonify({"status": "error", "message": "Adicione pelo menos um termo de busca."}), 400
    
    sections = data.get('sections', [])
    if not sections or len(sections) == 0:
        return jsonify({"status": "error", "message": "Selecione pelo menos uma seção do DOU."}), 400
    
    from ..services.email_service import is_smtp_enabled
    smtp_on = is_smtp_enabled()
    emails = data.get('emails', [])
    if smtp_on and (not emails or len(emails) == 0):
        return jsonify({"status": "error", "message": "Adicione pelo menos um e-mail de destino."}), 400
    
    filename = data.get('file')
    if not filename:
        new_id = re.sub(r'\W+', '_', data['name'].lower())
        filename = f"{new_id}.yaml"
        
    file_path = os.path.join(get_dag_confs_path(), filename)
    
    existing_data = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                existing_data = yaml.safe_load(f)
        except: pass

    new_dag = existing_data or {"dag": {}}
    dag = new_dag["dag"]
    
    dag["id"] = dag.get("id") or re.sub(r'\.[^.]*$', '', filename)
    dag["description"] = data.get('description', dag.get('description', ''))
    dag["schedule"] = data.get('schedule', dag.get('schedule', '0 5 * * *'))
    dag["tags"] = dag.get("tags", ["custom"])
    
    source_input = data.get('source', 'INLABS')
    if source_input == 'INLABS':
        if "inlabs" not in dag["tags"]:
            dag["tags"].append("inlabs")
        dag["dataset"] = "inlabs"
    else:
        if "dataset" in dag:
            del dag["dataset"]
        if "inlabs" in dag["tags"]:
            dag["tags"].remove("inlabs")
            
    dag["owner"] = dag.get("owner", ["admin"])
    
    search = dag.get("search", {})
    if isinstance(search, list): 
        search = search[0] if len(search) > 0 else {}
    
    search["header"] = data.get('name', search.get('header', 'Busca'))
    search["department"] = data.get('organs', search.get('department', []))
    search["organs"] = data.get('organs', search.get('organs', []))
    
    class QuotedString(str): pass
    def quoted_scalar_representer(dumper, data):
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style="'")
    yaml.SafeDumper.add_representer(QuotedString, quoted_scalar_representer)
    
    if filename != "Pesquisa_cnpj.yaml":
        raw_terms = data.get('terms', search.get('terms', []))
        search["terms"] = [QuotedString(t) for t in raw_terms]
    
    search["dou_sections"] = data.get('sections', search.get('dou_sections', DEFAULT_DOU_SECTIONS))
    is_exact_val = data.get('is_exact_search')
    if is_exact_val is None:
        is_exact_val = search.get("is_exact_search", False)
    is_exact_val = bool(is_exact_val)
    search["is_exact_search"] = is_exact_val
    search["force_rematch"] = bool(data.get('force_rematch', True))
    search["terms_ignore"] = data.get('terms_ignore', [])
    search["full_text"] = search.get("full_text", True)
    search["date"] = search.get("date", "DIA")
    
    if source_input == 'INLABS':
        search["sources"] = ["INLABS"]
    else:
        if "sources" in search:
            del search["sources"]
            
    dag["search"] = [search]
    
    report = dag.get("report", {})
    report["title"] = data.get('name', report.get('title', 'Alerta'))
    existing_emails = report.get('emails', [])
    if not emails and not smtp_on and existing_emails:
        emails = existing_emails
    report["emails"] = emails if emails else (data.get('emails', []) if 'emails' in data else existing_emails)
    report["subject"] = data.get('subject', report.get('subject', ''))
    
    if 'active' in data:
        dag["active"] = bool(data['active'])
        dag["is_paused"] = not bool(data['active'])
        executor = get_executor()
        if dag["is_paused"]:
            executor.pause(dag.get("id"))
        else:
            executor.unpause(dag.get("id"))
        
    dag["report"] = report
    
    tmp_path = file_path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(new_dag, f, allow_unicode=True, sort_keys=False)
    os.replace(tmp_path, file_path)
    
    from ..services.dag_config_service import touch_dag_generator
    if filename == "Pesquisa_cnpj.yaml":
        from ..models import db, Settings
        from ..services.dag_config_service import rebuild_yaml_from_db
        s_rec = Settings.query.filter_by(key='main_dag_settings').first()
        if not s_rec:
            s_rec = Settings(key='main_dag_settings')
            db.session.add(s_rec)
        s_rec.set_value({
            "emails": emails,
            "subject": report.get("subject", ""),
            "schedule": dag.get("schedule", "0 8 * * MON-FRI"),
            "active": dag.get("active", True),
            "is_exact_search": is_exact_val,
            "force_rematch": bool(search.get("force_rematch", True)),
            "organs": search.get("department", []),
            "department": search.get("department", []),
            "sections": search.get("dou_sections", DEFAULT_DOU_SECTIONS),
            "terms_ignore": search.get("terms_ignore", []),
            "source": source_input
        })
        db.session.commit()
        rebuild_yaml_from_db()
    else:
        touch_dag_generator()
    
    return jsonify({"status": "success", "message": "Rotina salva com sucesso!"})

@dags_bp.route('/system/main_dag_status', methods=['GET'])
@dags_bp.route('/system/integrations_status', methods=['GET'])
@login_required
def api_integrations_status():
    """Retorna o diagnóstico completo de todas as integrações e pendências do sistema para o assistente/alerta."""
    from ..services.dag_config_service import get_main_dag_info
    from ..services.email_service import is_smtp_enabled
    from ..services.inlabs_service import is_inlabs_local_available
    from ..models import Settings
    
    # 1. Rotina Principal (Main DAG)
    main_info = get_main_dag_info()
    main_enabled = bool(main_info.get("active", True))
    main_dag_configured = bool(main_info.get("is_configured", False))
    
    # 2. Global Settings (SMTP, Google Sheets, GestãoClick, PDF, INLABS)
    settings_record = Settings.query.filter_by(key='global_settings').first()
    settings_data = settings_record.get_value() if settings_record else {}
    if not isinstance(settings_data, dict):
        settings_data = {}
    
    # SMTP
    smtp_data = settings_data.get('smtp', {}) or {}
    smtp_enabled = is_smtp_enabled(smtp_data)
    smtp_configured = bool(str(smtp_data.get('server') or '').strip() and str(smtp_data.get('user') or '').strip())
    
    # Com SMTP desligado, a rotina principal não exige e-mail nem assunto
    if not smtp_enabled:
        main_dag_configured = True
        main_missing = []
    else:
        main_missing = main_info.get("missing_fields", [])

    # Google Sheets
    sheets_data = settings_data.get('google_sheets', {}) or {}
    sheets_enabled = bool(sheets_data.get('auto_sync', False))
    has_creds = bool(str(sheets_data.get('credentials_json') or '').strip())
    has_sheet = bool(str(sheets_data.get('spreadsheet_url') or sheets_data.get('spreadsheet_id') or sheets_data.get('sheet_url') or '').strip())
    sheets_configured = has_creds and has_sheet

    # GestãoClick
    ak_data = settings_data.get('api_keys', {}) or {}
    gc_enabled = bool(ak_data.get('gestaoclick_auto_sync', False))
    gc_has_access = bool(str(ak_data.get('gestaoclick_access_token') or '').strip())
    gc_has_secret = bool(str(ak_data.get('gestaoclick_secret_token') or '').strip())
    gc_configured = gc_has_access and gc_has_secret

    # Arquivo PDF
    pa_data = settings_data.get('pdf_archive', {}) or {}
    pa_enabled = bool(pa_data.get('enabled', True))
    pa_configured = True  # pasta padrão sempre resolvida

    # INLABS
    inlabs_data = settings_data.get('inlabs', {}) or {}
    inlabs_local = is_inlabs_local_available()
    inlabs_enabled = bool(inlabs_data.get('enabled', True)) if inlabs_local else False
    inlabs_configured = bool(str(inlabs_data.get('user') or '').strip() and str(inlabs_data.get('password') or '').strip())

    def _status_for(enabled: bool, configured: bool, available: bool = True) -> str:
        if not available:
            return "unavailable"
        if not enabled:
            return "disabled"
        return "configured" if configured else "pending"

    integrations = [
        {
            "id": "main_dag",
            "name": "Rotina Principal",
            "title": "E-mails da Rotina Principal",
            "description": "Defina os e-mails de destino e o assunto para receber o relatório diário de publicações.",
            "enabled": main_enabled,
            "is_configured": main_dag_configured,
            "status": _status_for(main_enabled, main_dag_configured),
            "action_type": "modal_main_dag",
            "icon": "calendar-clock",
            "missing_fields": main_missing if main_enabled else [],
        },
        {
            "id": "smtp",
            "name": "Servidor SMTP",
            "title": "Servidor de Envio (SMTP)",
            "description": "Configure o servidor de e-mail (Host, Porta, Usuário e Senha) para disparo automático.",
            "enabled": smtp_enabled,
            "is_configured": smtp_configured,
            "status": _status_for(smtp_enabled, smtp_configured),
            "action_type": "modal_smtp",
            "icon": "mail",
            "missing_fields": [f for f in ["server", "user"] if not str(smtp_data.get(f) or '').strip()] if smtp_enabled else [],
        },
        {
            "id": "google_sheets",
            "name": "Google Sheets",
            "title": "Planilha Google Sheets",
            "description": "Conecte a planilha com credenciais de serviço para sincronização automática de empresas.",
            "enabled": sheets_enabled,
            "is_configured": sheets_configured,
            "status": _status_for(sheets_enabled, sheets_configured),
            "action_type": "tab_sheets",
            "icon": "file-spreadsheet",
            "missing_fields": (([ "credentials_json" ] if not has_creds else []) + ([ "spreadsheet_url" ] if not has_sheet else [])) if sheets_enabled else [],
        },
        {
            "id": "gestaoclick",
            "name": "API GestãoClick",
            "title": "API GestãoClick",
            "description": "Informe os tokens do GestãoClick para sincronização automática de empresas.",
            "enabled": gc_enabled,
            "is_configured": gc_configured,
            "status": _status_for(gc_enabled, gc_configured),
            "action_type": "tab_gestaoclick",
            "icon": "key",
            "missing_fields": (([ "gestaoclick_access_token" ] if not gc_has_access else []) + ([ "gestaoclick_secret_token" ] if not gc_has_secret else [])) if gc_enabled else [],
        },
        {
            "id": "pdf_archive",
            "name": "Arquivo PDF",
            "title": "Arquivo automático do PDF",
            "description": "Salva diariamente os PDFs completos do DOU na pasta escolhida.",
            "enabled": pa_enabled,
            "is_configured": pa_configured,
            "status": _status_for(pa_enabled, pa_configured),
            "action_type": "tab_pdf_archive",
            "icon": "file-text",
            "missing_fields": [],
        },
        {
            "id": "inlabs",
            "name": "Acesso INLABS",
            "title": "Credenciais INLABS",
            "description": (
                "Informe usuário e senha do portal INLABS (Imprensa Nacional) para download do DOU."
                if inlabs_local
                else "INLABS local não instalado nesta versão; a busca usa a contingência (PDF integral + API do DOU)."
            ),
            "enabled": inlabs_enabled,
            "local_available": inlabs_local,
            "is_configured": inlabs_configured if inlabs_local else False,
            "status": _status_for(inlabs_enabled, inlabs_configured, available=inlabs_local),
            "action_type": "tab_inlabs",
            "icon": "newspaper",
            "missing_fields": ([f for f in ["user", "password"] if not str(inlabs_data.get(f) or '').strip()] if inlabs_enabled else []),
        },
    ]
    
    pending = [i for i in integrations if i["status"] == "pending"]
    
    missing_all = [i["id"] for i in pending]
        
    main_dag_is_configured = bool((not main_enabled or main_dag_configured) and (smtp_configured or not smtp_enabled))
    
    return jsonify({
        "status": "ok",
        "is_configured": main_dag_is_configured,
        "all_configured": len(pending) == 0,
        "pending_count": len(pending),
        "next_pending": pending[0] if pending else None,
        "integrations": integrations,
        "missing_fields": missing_all,
        "main_dag": main_info,
        "smtp_enabled": smtp_enabled,
        "smtp_configured": smtp_configured,
        "smtp": {
            "enabled": smtp_enabled,
            "server": smtp_data.get("server", ""),
            "port": smtp_data.get("port", "587"),
            "user": smtp_data.get("user", ""),
            "from_email": smtp_data.get("from_email", ""),
            "has_password": bool(smtp_data.get("password"))
        }
    })

@dags_bp.route('/system/configure_main_dag', methods=['POST'])
@login_required
def api_configure_main_dag():
    """Configura atomicamente os e-mails, assunto, agendamento da DAG principal e servidor SMTP."""
    if session['user']['role'] != 'master':
        return jsonify({"status": "error", "message": "Apenas administradores podem configurar a rotina principal."}), 403
        
    data = request.json or {}
    
    # Valida e-mails (exigido apenas com SMTP ligado)
    from ..services.email_service import is_smtp_enabled
    smtp_in = data.get('smtp') if isinstance(data.get('smtp'), dict) else None
    smtp_on = bool(smtp_in.get('enabled')) if (smtp_in and 'enabled' in smtp_in) else is_smtp_enabled()

    raw_emails = data.get('emails', [])
    if isinstance(raw_emails, str):
        emails = [e.strip() for e in raw_emails.replace('\n', ',').split(',') if e.strip()]
    elif isinstance(raw_emails, list):
        emails = [str(e).strip() for e in raw_emails if str(e).strip()]
    else:
        emails = []
        
    # Atualização parcial: só exige e-mails quando 'emails' veio no payload (Sprint 14).
    if 'emails' in data and smtp_on and not emails:
        return jsonify({"status": "error", "message": "Pelo menos um e-mail de destino é obrigatório para a rotina principal."}), 400
        
    # Valida formato dos e-mails
    email_regex = re.compile(r'^[\w\.-]+@[\w\.-]+\.\w+$')
    for em in emails:
        if not email_regex.match(em):
            return jsonify({"status": "error", "message": f"E-mail inválido: {em}"}), 400
            
    # 1. Salva configurações no SQLite (persistente no volume /data)
    from ..models import db, Settings
    s_rec = Settings.query.filter_by(key='main_dag_settings').first()
    existing_val = s_rec.get_value() if (s_rec and isinstance(s_rec.get_value(), dict)) else {}

    # subject/schedule/active só mudam quando vêm no payload; senão mantém o valor
    # existente (instalação nova usa o padrão).
    subject = str(data.get('subject') or '').strip() if 'subject' in data else ''
    if not subject:
        subject = str(existing_val.get('subject') or '').strip() or "[Registrale] Relatório Diário de Publicações do DOU"

    if 'schedule' in data:
        schedule = str(data.get('schedule') or '').strip() or '0 8 * * MON-FRI'
    else:
        schedule = str(existing_val.get('schedule') or '').strip() or '0 8 * * MON-FRI'

    if 'active' in data:
        active = bool(data.get('active'))
    else:
        active = bool(existing_val.get('active', True))

    if not s_rec:
        s_rec = Settings(key='main_dag_settings')
        db.session.add(s_rec)
    if not emails and ('emails' not in data or not smtp_on) and existing_val.get('emails'):
        emails = list(existing_val.get('emails') or [])
    
    updated_main_settings = dict(existing_val)
    updated_main_settings.update({
        "emails": emails,
        "subject": subject,
        "schedule": schedule,
        "active": active
    })
    if 'is_exact_search' in data:
        updated_main_settings['is_exact_search'] = bool(data['is_exact_search'])
    if 'force_rematch' in data:
        updated_main_settings['force_rematch'] = bool(data['force_rematch'])
    if 'organs' in data or 'department' in data:
        orgs = data.get('organs') or data.get('department')
        updated_main_settings['organs'] = orgs
        updated_main_settings['department'] = orgs
    if 'sections' in data:
        updated_main_settings['sections'] = data['sections']
    if 'terms_ignore' in data:
        updated_main_settings['terms_ignore'] = data['terms_ignore']

    s_rec.set_value(updated_main_settings)
    db.session.commit()
    
    # 2. Atualiza Pesquisa_cnpj.yaml e reconstrói blocos com base nas novas configurações
    from ..services.dag_config_service import rebuild_yaml_from_db
    rebuild_yaml_from_db()
    
    # 2. Configurar SMTP se fornecido
    if 'smtp' in data and isinstance(data['smtp'], dict):
        smtp = data['smtp']
        server = str(smtp.get('server') or '').strip()
        if server.lower().startswith('stmp.'):
            server = 'smtp.' + server[5:]
        elif server.lower().startswith('smpt.'):
            server = 'smtp.' + server[5:]
        user = str(smtp.get('user') or '').strip()
        
        if server and user:
            from ..models import db, Settings
            
            settings_record = Settings.query.filter_by(key='global_settings').first()
            if not settings_record:
                settings_record = Settings(key='global_settings')
                db.session.add(settings_record)
            current_val = settings_record.get_value() or {}
            if not isinstance(current_val, dict):
                current_val = {}
            
            port = str(smtp.get('port') or '587').strip()
            raw_password = str(smtp.get('password') or '').strip()
            # Se não enviou senha nova, preserva a senha anterior
            if not raw_password and current_val.get('smtp', {}).get('password'):
                raw_password = current_val.get('smtp', {}).get('password')
            if 'gmail.com' in server.lower():
                raw_password = raw_password.replace(' ', '')
            from_email = str(smtp.get('from_email') or user).strip()
            
            current_val['smtp'] = {
                "enabled": bool(smtp.get("enabled", True)),
                "server": server,
                "port": port,
                "user": user,
                "password": raw_password,
                "from_email": from_email
            }
            settings_record.set_value(current_val)
            db.session.commit()
            
            # Sincronizar conexão smtp_default no orquestrador (no-op no modo local)
            try:
                import json

                conn_payload = {
                    "connection_id": "smtp_default",
                    "conn_type": "smtp",
                    "host": server,
                    "login": user,
                    "password": raw_password,
                    "port": int(port) if port.isdigit() else 587,
                    "extra": json.dumps({"from_email": from_email, "disable_tls": False})
                }
                get_executor().sync_connection("smtp_default", conn_payload)
            except Exception as e:
                import logging
                logging.error(f"Falha ao atualizar conexão smtp_default via assistente: {e}")
                
    return jsonify({
        "status": "success",
        "message": "Configurações da rotina principal atualizadas com sucesso!",
        "main_dag": {
            "emails": emails,
            "subject": subject,
            "schedule": schedule,
            "active": active
        }
    })

@dags_bp.route('/routines/toggle/<path:file>', methods=['POST'])
@login_required
def toggle_routine_route(file):
    """Ativa ou desativa uma rotina de busca no YAML e no agendador local."""
    if session['user']['role'] != 'master':
        return jsonify({"status": "error", "message": "Acesso negado."}), 403
        
    data = request.get_json(silent=True) or {}
    dag_confs_path = get_dag_confs_path()
    file_path = os.path.join(dag_confs_path, file)
    
    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "Arquivo de rotina não encontrado."}), 404
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            yaml_data = yaml.safe_load(f) or {}
            
        dag = yaml_data.get('dag', {})
        dag_id = dag.get('id') or re.sub(r'\.[^.]*$', '', file)
        
        # Inverte ou define conforme passado
        current_active = dag.get('active', not dag.get('is_paused', False))
        new_active = data.get('active', not current_active)
        
        dag['active'] = bool(new_active)
        dag['is_paused'] = not bool(new_active)
        yaml_data['dag'] = dag
        
        tmp_path = file_path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(yaml_data, f, allow_unicode=True, sort_keys=False)
        os.replace(tmp_path, file_path)
        
        executor = get_executor()
        if new_active:
            executor.unpause(dag_id)
        else:
            executor.pause(dag_id)
        
        # Se for Pesquisa_cnpj.yaml, atualiza também no SQLite e propaga para partes
        if file == "Pesquisa_cnpj.yaml":
            from ..models import db, Settings
            s_rec = Settings.query.filter_by(key='main_dag_settings').first()
            if not s_rec:
                s_rec = Settings(key='main_dag_settings')
                db.session.add(s_rec)
            s_val = s_rec.get_value() if s_rec.value else {}
            if not isinstance(s_val, dict):
                s_val = {}
            s_val['active'] = bool(new_active)
            s_rec.set_value(s_val)
            db.session.commit()

            parts = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_sync.yaml")) + \
                    glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_part_*.yaml"))
            for p in parts:
                try:
                    with open(p, 'r', encoding='utf-8') as pf:
                        pdata = yaml.safe_load(pf) or {}
                    pdag = pdata.get('dag', {})
                    pdag_id = pdag.get('id')
                    pdag['active'] = bool(new_active)
                    pdag['is_paused'] = not bool(new_active)
                    pdata['dag'] = pdag
                    ptmp = p + '.tmp'
                    with open(ptmp, 'w', encoding='utf-8') as pf:
                        yaml.safe_dump(pdata, pf, allow_unicode=True, sort_keys=False)
                    os.replace(ptmp, p)
                    if pdag_id:
                        if new_active:
                            executor.unpause(pdag_id)
                        else:
                            executor.pause(pdag_id)
                except Exception as part_err:
                    pass
        
        from ..services.dag_config_service import touch_dag_generator
        touch_dag_generator()
        
        action_str = "ativada" if new_active else "desativada"
        add_history_event(
            f"Rotina {'Ativada' if new_active else 'Desativada'}",
            f"A rotina {dag.get('id', file)} foi {action_str} com sucesso."
        )
        
        return jsonify({
            "status": "success",
            "active": new_active,
            "message": f"Rotina {action_str} com sucesso!"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao alternar status: {str(e)}"}), 500


@dags_bp.route('/routines/<path:file>', methods=['DELETE'])
@login_required
def delete_routine(file):
    if session['user']['role'] != 'master': return jsonify({"status": "error", "message": "Acesso negado."}), 403
    
    if file == "Pesquisa_cnpj.yaml" or "_part_" in file or "_sync" in file or "gestaoclick" in file.lower():
        return jsonify({"status": "error", "message": "Não é possível excluir rotinas de sistema (Sync / GestãoClick)."}), 400
        
    dag_confs_path = get_dag_confs_path()
    file_path = os.path.join(dag_confs_path, file)
    if os.path.exists(file_path):
        try:
            # Tentar extrair dag_id
            dag_id = os.path.splitext(file)[0]
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    ydata = yaml.safe_load(f)
                    if isinstance(ydata, dict) and 'dag' in ydata:
                        dag_id = ydata['dag'].get('id', dag_id)
            except Exception:
                pass

            os.remove(file_path)

            # Desregistrar do orquestrador (no-op no modo local)
            get_executor().delete_routine(dag_id)
            touch_dag_generator()

            add_history_event("Rotina Excluída", f"Rotina {file} removida do sistema.")
            return jsonify({"status": "success", "message": "Rotina excluída com sucesso!"})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Erro ao excluir o arquivo: {str(e)}"}), 500
    
    return jsonify({"status": "error", "message": "Arquivo não encontrado."}), 404


@dags_bp.route('/routines/cleanup_temp', methods=['POST'])
@login_required
def cleanup_temp_dags_route():
    """Endpoint para forçar a limpeza imediata de rotinas temporárias do disco."""
    try:
        from ..services.dag_config_service import cleanup_orphaned_temp_dags
        cleaned = cleanup_orphaned_temp_dags(max_age_seconds=0, force_all=True)
        return jsonify({
            "status": "success",
            "message": f"{cleaned} DAG(s) e arquivo(s) temporário(s) removido(s) com sucesso.",
            "cleaned_count": cleaned
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def _dispatch_routine(dag_id, logical_date=None, yaml_dict=None):
    """Dispara uma rotina pelo Executor local."""
    try:
        target = yaml_dict if yaml_dict is not None else dag_id
        run_id = get_executor().trigger(target, date=logical_date)
        return True, f"Rotina {dag_id} disparada localmente.", {"dag_id": dag_id, "dag_run_id": run_id}
    except Exception as exc:
        return False, str(exc), {"dag_id": dag_id, "dag_run_id": None}


def watch_dag_and_update_mentions(app_context, runs_to_watch, routine_name, routine_emails=None, routine_subject=None, logical_date=None, target_terms=None, trigger_time_str=None, notify_only_new=False):
    import time
    import logging
    from datetime import datetime, timezone, timedelta
    from ..services.mention_service import clear_mentions_cache, get_mentions_kpis
    from ..services.email_service import EmailSender, build_mentions_email_html
    from ..models import db, Settings, Mention, Company

    # Garante lista estruturada de itens a monitorar
    normalized_runs = []
    for r in runs_to_watch:
        if isinstance(r, dict):
            normalized_runs.append(r)
        else:
            normalized_runs.append({"dag_id": str(r), "dag_run_id": None})

    run_ids = [item["dag_run_id"] for item in normalized_runs if item.get("dag_run_id")]
    if run_ids:
        with app_context:
            get_executor().wait(run_ids, timeout=1800)
    with app_context:
        try:
            # 2. Formatar data de referência
            if logical_date:
                try:
                    target_date_str = datetime.strptime(str(logical_date).strip(), '%Y-%m-%d').strftime('%d/%m/%Y')
                except Exception:
                    try:
                        target_date_str = datetime.strptime(str(logical_date).strip(), '%d/%m/%Y').strftime('%d/%m/%Y')
                    except Exception:
                        target_date_str = str(logical_date)
            else:
                target_date_str = datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y')

            # 3. Extrair menções diretamente dos DAG Runs concluídos (Ultrarrápido: ~0.05s)
            direct_mentions = []
            companies = Company.query.with_entities(Company.cnpj_norm, Company.nome, Company.cnpj).all()
            cnpj_map = {c.cnpj_norm: c.nome for c in companies if c.cnpj_norm}
            cnpj_map.update({c.cnpj: c.nome for c in companies if c.cnpj})

            for item in normalized_runs:
                did = item.get('dag_id')
                run_id = item.get('dag_run_id')
                if did:
                    run_res = fetch_mentions_from_dag_run(did, run_id, cnpj_map=cnpj_map)
                    direct_mentions.extend(run_res)

            # Mesma publicação vinda de outra fonte (PDF x API) não vira menção nova
            direct_mentions, already_notified_ids = reconcile_mentions_across_sources(direct_mentions)

            # Se obteve menções diretas, insere/atualiza no banco SQLite para o Dashboard
            if direct_mentions:
                from ..runtime.pdf_archiver import resolve_pdf_for_mention
                m_ids = [m['id'] for m in direct_mentions if m.get('id')]
                existing_records = {e.id: e for e in Mention.query.filter(Mention.id.in_(m_ids)).all()} if m_ids else {}
                new_mention_ids = {i for i in m_ids if i not in existing_records and i not in already_notified_ids}
                for m in direct_mentions:
                    pdf_path = m.get('pdf_path') or resolve_pdf_for_mention(m.get('data'), m.get('secao'))
                    existing = existing_records.get(m['id'])
                    if not existing:
                        payload = dict(m)
                        if pdf_path:
                            payload['pdf_path'] = pdf_path
                        db.session.add(Mention(**payload))
                    else:
                        existing.empresa = m.get('empresa', existing.empresa)
                        existing.secao = m.get('secao', existing.secao)
                        existing.data = m.get('data', existing.data)
                        existing.detected_at = m.get('detected_at', existing.detected_at)
                        existing.trecho = m.get('trecho', existing.trecho)
                        existing.link = m.get('link', existing.link)
                        if pdf_path:
                            existing.pdf_path = pdf_path
                db.session.commit()
                clear_mentions_cache()
                relevant_mentions = direct_mentions
                if notify_only_new:
                    # Nova tentativa do dia: só avisa o que ainda não tinha sido gravado/enviado.
                    relevant_mentions = [m for m in direct_mentions if m.get('id') in new_mention_ids]
            else:
                clear_mentions_cache()
                relevant_mentions = []

            # Filtragem opcional de termos para rotinas com termos específicos
            if target_terms and routine_name != "Pesquisa_cnpj.yaml":
                relevant_mentions = [
                    m for m in relevant_mentions 
                    if (m.get('cnpj_norm') in target_terms) or (m.get('cnpj') in target_terms)
                ]

            total, hoje, mes = get_mentions_kpis()

            # 4. Destinatários de E-mail
            emails = list(routine_emails or [])
            if not emails:
                settings_record = Settings.query.filter_by(key='global_settings').first()
                if settings_record:
                    smtp_data = settings_record.get_value().get('smtp', {})
                    smtp_from = smtp_data.get('from_email') or smtp_data.get('user', '')
                    if smtp_from:
                        emails = [smtp_from]
            emails = [e.strip() for e in emails if e and str(e).strip()]

            logging.info(f"[Watcher {routine_name}] relevant_mentions={len(relevant_mentions)}, emails={emails}")

            source_tag = ""
            run_ids = [item.get("dag_run_id") for item in normalized_runs if item.get("dag_run_id")]
            sources_label = _extract_sources_used_from_runs(run_ids)
            if sources_label:
                source_tag = f" [Fonte: {sources_label}]"
            coverage_text, pending_sections = _summarize_coverage_from_runs(run_ids)
            if coverage_text:
                source_tag += f" [Seções: {coverage_text}]"

            # 5. Envio do E-mail Formatado
            from ..services.email_service import is_smtp_enabled
            email_sent = False
            email_failed = False
            smtp_enabled = is_smtp_enabled()
            if not smtp_enabled:
                add_history_event(
                    "E-mail desativado",
                    f"Envio de e-mail desativado nas configurações. Rotina {routine_name} gravou {len(relevant_mentions)} menção(ões) para {target_date_str}{source_tag}."
                )
            elif emails and relevant_mentions:
                from ..services.email_service import render_email_subject
                subject = render_email_subject(
                    routine_subject, relevant_mentions, template_name='Padrão Registrale',
                    date_str=target_date_str,
                    fallback=f"Registrale - Alerta DOU ({routine_name}) - {target_date_str}")
                html = build_mentions_email_html(
                    relevant_mentions,
                    template_name='Padrão Registrale',
                    title=routine_subject or f"Notificação DOU: {routine_name}",
                    subtitle=f"Foram identificadas {len(relevant_mentions)} publicações no Diário Oficial da União para a data {target_date_str}:"
                )
                try:
                    sender = EmailSender(None)
                    sender.send_custom_email(
                        to_emails=emails,
                        subject=subject,
                        html_content=html
                    )
                    email_sent = True
                    add_history_event("E-mail Enviado", f"Alerta {routine_name} enviado para {', '.join(emails)} ({len(relevant_mentions)} menções){source_tag}.")
                except Exception as e_mail:
                    email_failed = True
                    logging.error(f"Erro ao enviar e-mail da rotina {routine_name}: {e_mail}")
                    add_history_event("Erro Envio E-mail", f"Falha ao enviar e-mail da rotina {routine_name}: {str(e_mail)}")

            if not email_sent and not email_failed:
                motivo = []
                if not smtp_enabled:
                    motivo.append("e-mail desativado")
                elif not emails:
                    motivo.append("nenhum destinatário configurado")
                if not relevant_mentions:
                    motivo.append(f"0 menções encontradas para {target_date_str}")
                motivo_str = f" ({'; '.join(motivo)})" if motivo else ""
                if pending_sections:
                    add_history_event(
                        "Busca Concluída com Pendências",
                        f"Rotina {routine_name} concluída com pendências: {', '.join(pending_sections)} não foram cobertas por nenhuma fonte, "
                        f"então o resultado de {target_date_str} está INCOMPLETO{motivo_str}{source_tag}."
                    )
                else:
                    add_history_event("Busca Concluída", f"Rotina {routine_name} concluída{motivo_str}{source_tag}. Total no painel: {total} ({hoje} hoje).")
            elif pending_sections:
                add_history_event(
                    "Busca com Pendências",
                    f"Atenção: {', '.join(pending_sections)} não foram cobertas em {target_date_str}; o resultado está incompleto{source_tag}."
                )

        except Exception as e:
            import logging
            logging.error(f"Erro ao atualizar menções pós-busca: {e}")


@dags_bp.route('/routines/trigger/<path:file>', methods=['POST'])
@login_required
def trigger_routine(file):
    req_data = request.get_json(silent=True) or {}
    logical_date = req_data.get('logical_date')
    
    if logical_date:
        try:
            logical_date = normalize_date_str(logical_date)
        except ValueError:
            return jsonify({"status": "error", "message": "Data inválida. Use o formato DD/MM/AAAA ou AAAA-MM-DD."}), 400

    dag_confs_path = get_dag_confs_path()
    
    # ----------------------------------------------------
    # Lógica de verificação e leitura da rotina
    # ----------------------------------------------------
    is_inlabs = False
    dag_id_to_trigger = None
    routine_emails = []
    routine_subject = None
    routine_title = file
    routine_cnpjs = set()

    file_path = os.path.join(dag_confs_path, file)
    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "Arquivo de rotina não encontrado."}), 404

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            yaml_check = yaml.safe_load(f) or {}
            
            # Bloqueio de rotina pausada
            is_active = yaml_check.get('dag', {}).get('active')
            if is_active is None:
                is_active = yaml_check.get('active', True)
            if is_active is False:
                return jsonify({"status": "error", "message": "Esta rotina está pausada. Ative-a antes de disparar pesquisas."}), 400
                
            dag_data = yaml_check.get('dag', {})
            dag_id_to_trigger = dag_data.get('id')
            if not dag_id_to_trigger and file != "Pesquisa_cnpj.yaml":
                dag_id_to_trigger = re.sub(r'\.[^.]*$', '', file)
                
            report_data = dag_data.get('report', {})
            routine_emails = report_data.get('emails', [])
            if isinstance(routine_emails, str): routine_emails = [routine_emails]
            routine_subject = report_data.get('subject')
            routine_title = report_data.get('title') or file
            
            search_entries = dag_data.get('search', [])
            if isinstance(search_entries, dict): search_entries = [search_entries]
            for s_item in search_entries:
                sources = s_item.get('sources', ['DOU'])
                if 'INLABS' in sources:
                    is_inlabs = True
                for t in s_item.get('terms', []):
                    clean_t = re.sub(r'[^A-Za-z0-9]', '', str(t)).upper()
                    if clean_t:
                        routine_cnpjs.add(clean_t)
    except Exception: pass

    # Rotina sem empresas/termos (ex.: antes da primeira sincronização): mensagem clara
    # em vez do erro técnico de validação do YAML.
    from ..runtime.runner import NO_COMPANIES_MESSAGE, routine_has_no_terms
    if routine_has_no_terms(file_path):
        return jsonify({"status": "error", "code": "no_companies", "message": NO_COMPANIES_MESSAGE}), 400

    # ----------------------------------------------------
    # SE FOR ROTINA INLABS COM DATA ESPECÍFICA (EX: 2026-08-15)
    # ----------------------------------------------------
    if is_inlabs and logical_date:
        from ..services.inlabs_service import is_date_loaded, record_inlabs_download_success, enforce_inlabs_retention_limit
        from ..services.holiday_service import is_within_inlabs_retention_window

        already_loaded, articles_found = is_date_loaded(logical_date)
        app_ctx = current_app._get_current_object().app_context()

        if already_loaded:
            add_history_event("Busca Iniciada", f"Dados de {logical_date} já disponíveis ({articles_found} artigos). Disparando pesquisa na rotina {file}...")
            ok, msg, run_info = _dispatch_routine(dag_id_to_trigger, logical_date)
            threading.Thread(
                target=watch_dag_and_update_mentions,
                args=(
                    app_ctx, 
                    [run_info], 
                    file, 
                    routine_emails, 
                    routine_subject, 
                    logical_date, 
                    routine_cnpjs,
                    run_info.get("trigger_time") if isinstance(run_info, dict) else None
                ),
                daemon=True
            ).start()
            return jsonify({"status": "success", "message": f"Dados já disponíveis no banco. Pesquisa iniciada com sucesso para {logical_date}!"})

        # Busca via API Oficial do DOU (usada para datas fora da janela de 120 dias
        # do INLABS e como fallback quando o portal INLABS está fora do ar).
        def run_adhoc_dou_search(app_context_obj, source_file, target_date, r_emails, r_subject, r_terms):
            temp_dag_id = None
            with app_context_obj:
                try:
                    routine_path = os.path.join(dag_confs_path, source_file)
                    with open(routine_path, 'r', encoding='utf-8') as f:
                        base_yaml = yaml.safe_load(f) or {}

                    original_searches = base_yaml.get('dag', {}).get('search', [])
                    if not isinstance(original_searches, list):
                        original_searches = [original_searches] if original_searches else []

                    temp_search_blocks = []
                    for block in original_searches:
                        temp_block = {
                            "header": block.get("header", f"Busca API-DOU {source_file}"),
                            "is_exact_search": block.get("is_exact_search", False),
                            "force_rematch": True,
                            "terms": block.get("terms", []),
                            "dou_sections": block.get("dou_sections", DEFAULT_DOU_SECTIONS),
                            "field": block.get("field", "TUDO"),
                            "full_text": block.get("full_text", True),
                            "date": "DIA",
                            "sources": _fallback_sources(),
                        }
                        if block.get("department"): temp_block["department"] = block["department"]
                        if block.get("organs"): temp_block["organs"] = block["organs"]
                        if block.get("terms_ignore"): temp_block["terms_ignore"] = block["terms_ignore"]
                        temp_search_blocks.append(temp_block)

                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    temp_dag_id = f"temp_adhoc_dou_{timestamp}"

                    temp_yaml = {
                        "dag": {
                            "id": temp_dag_id,
                            "description": f"Busca ad-hoc API-DOU para {target_date}",
                            "schedule": None,
                            "tags": ["temp", "api_dou", "adhoc"],
                            "search": temp_search_blocks,
                            "report": {
                                "page_title": f"Busca API-DOU {target_date}",
                                "emails": [],
                                "subject": f"Registrale - API-DOU {target_date}"
                            }
                        }
                    }

                    ok, msg, run_info = _dispatch_routine(temp_dag_id, target_date, yaml_dict=temp_yaml)
                    if ok:
                        watch_dag_and_update_mentions(
                            app_context_obj,
                            [run_info],
                            source_file,
                            r_emails,
                            r_subject,
                            target_date,
                            r_terms,
                            run_info.get("trigger_time") if isinstance(run_info, dict) else None
                        )
                except Exception as e:
                    logging.error(f"Erro na busca ad-hoc API DOU para {target_date}: {e}")

        # Verifica se o INLABS local está disponível (Postgres portátil/URL) e com credenciais configuradas
        def _local_inlabs_ready():
            from ..services.inlabs_service import is_inlabs_local_available
            if not is_inlabs_local_available():
                return False
            try:
                from ..models import Settings
                rec = Settings.query.filter_by(key="global_settings").first()
                inlabs_cfg = (rec.get_value() or {}).get("inlabs", {}) if rec else {}
                if not (inlabs_cfg.get("user") and inlabs_cfg.get("password")):
                    return False
            except Exception:
                return False
            return True

        # Se o INLABS local não estiver pronto (sem Postgres portátil
        # ou sem credenciais), pesquisa via contingência configurada (PDF integral ou API do DOU).
        if not _local_inlabs_ready():
            src_label = _describe_local_fallback_source()
            add_history_event(f"Busca Individual ({src_label})", f"Modo local: pesquisando {logical_date} via {src_label}...")
            threading.Thread(
                target=run_adhoc_dou_search,
                args=(app_ctx, file, logical_date, routine_emails, routine_subject, routine_cnpjs),
                daemon=True
            ).start()
            return jsonify({"status": "success", "source_used": src_label, "message": f"Busca para {logical_date} iniciada via {src_label}!"})

        from ..services.inlabs_service import check_inlabs_portal_status
        portal_ok, portal_msg = check_inlabs_portal_status()

        if not portal_ok:
            src_label = _describe_local_fallback_source()
            add_history_event(f"Busca Individual ({src_label})", f"{portal_msg}. Pesquisando {logical_date} via {src_label}...")
            threading.Thread(
                target=run_adhoc_dou_search,
                args=(app_ctx, file, logical_date, routine_emails, routine_subject, routine_cnpjs),
                daemon=True
            ).start()
            return jsonify({"status": "success", "source_used": src_label, "message": f"{portal_msg}. Busca iniciada via {src_label}!"})

        # Se for anterior à janela de 120 dias do portal INLABS, executa via contingência
        if not is_within_inlabs_retention_window(logical_date, 120):
            src_label = _describe_local_fallback_source()
            add_history_event(f"Busca Individual ({src_label})", f"Data {logical_date} anterior a 120 dias (fora da retenção do INLABS). Disparando busca via {src_label}...")
            threading.Thread(
                target=run_adhoc_dou_search,
                args=(app_ctx, file, logical_date, routine_emails, routine_subject, routine_cnpjs),
                daemon=True
            ).start()
            return jsonify({"status": "success", "source_used": src_label, "message": f"Data anterior a 120 dias. Busca iniciada via {src_label}!"})

        def run_inlabs_then_search(app_context_obj, target_dag_id, target_date, filename, r_emails, r_subject, r_terms):
            from ..services.inlabs_service import record_inlabs_download_success, enforce_inlabs_retention_limit

            with app_context_obj:
                enforce_inlabs_retention_limit(max_days=120, protected_dates=[target_date])

            exec_inst = get_executor()
            inlabs_run_id = exec_inst.trigger("ro-dou_inlabs_load_pg", date=target_date)
            load_state = None
            if inlabs_run_id:
                _, states = exec_inst.wait([inlabs_run_id], timeout=900)
                load_state = states.get(inlabs_run_id)
            msg_inlabs = load_state or ""

            from ..services.inlabs_service import is_date_loaded
            with app_context_obj:
                loaded, _cnt = is_date_loaded(target_date)
            if not loaded:
                # Carga INLABS falhou (portal fora do ar, sem edição etc.):
                # cai para a contingência em vez de pesquisar um banco vazio.
                src_label = _describe_local_fallback_source()
                with app_context_obj:
                    add_history_event("Carga INLABS Falhou", f"Sem dados INLABS para {target_date} (estado da carga: {load_state or msg_inlabs}). Pesquisando via {src_label}...")
                run_adhoc_dou_search(app_context_obj, filename, target_date, r_emails, r_subject, r_terms)
                return

            with app_context_obj:
                record_inlabs_download_success(target_date)
                add_history_event("Carga INLABS Concluída", f"Download concluído para {target_date}. Disparando agora a busca {filename}...")
                
            with app_context_obj:
                ok, msg, run_info = _dispatch_routine(target_dag_id, target_date)
            if ok and run_info:
                watch_dag_and_update_mentions(
                    app_context_obj,
                    [run_info],
                    filename,
                    r_emails,
                    r_subject,
                    target_date,
                    r_terms,
                    run_info.get("trigger_time") if isinstance(run_info, dict) else None,
                )
        
        add_history_event("Carga INLABS", f"Iniciando download dos dados INLABS para {logical_date}...")
        threading.Thread(target=run_inlabs_then_search, args=(app_ctx, dag_id_to_trigger, logical_date, file, routine_emails, routine_subject, routine_cnpjs), daemon=True).start()
        return jsonify({"status": "success", "message": f"Download INLABS iniciado em background. A busca iniciará automaticamente logo após."})
    # ----------------------------------------------------

    if file == "Pesquisa_cnpj.yaml":
        parts = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_sync.yaml"))
        if not parts:
            parts = glob.glob(os.path.join(dag_confs_path, "Pesquisa_cnpj_part_*.yaml"))
        if not parts:
            file_path = os.path.join(dag_confs_path, file)
            if not os.path.exists(file_path):
                return jsonify({"status": "error", "message": "Arquivo base não encontrado."}), 404
            parts = [file_path]
            
        success_count = 0
        triggered_runs = []
        errors = []
        for p in parts:
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    dag_id = data.get('dag', {}).get('id')
                    if dag_id:
                        ok, msg, run_info = _dispatch_routine(dag_id, logical_date)
                        if ok:
                            success_count += 1
                            triggered_runs.append(run_info)
                        else: errors.append(msg)
            except: continue
        
        if success_count > 0:
            add_history_event("Busca Iniciada", f"Rotina {file} ({success_count} parte(s)) disparada localmente. Data Lógica: {logical_date or 'Atual'}")
            app_ctx = current_app._get_current_object().app_context()
            first_trigger_time = triggered_runs[0].get("trigger_time") if triggered_runs else None
            threading.Thread(
                target=watch_dag_and_update_mentions, 
                args=(app_ctx, triggered_runs, file, routine_emails, routine_subject, logical_date, routine_cnpjs, first_trigger_time), 
                daemon=True
            ).start()
            return jsonify({"status": "success", "message": f"{success_count} parte(s) disparada(s)!"})
        else:
            return jsonify({"status": "error", "message": "Nenhuma parte pôde ser disparada.", "details": errors}), 500

    file_path = os.path.join(dag_confs_path, file)
    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "Arquivo de rotina não encontrado."}), 404
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            dag_id = data.get('dag', {}).get('id')
            if not dag_id: dag_id = re.sub(r'\.[^.]*$', '', file)
            
            ok, msg, run_info = _dispatch_routine(dag_id, logical_date)
            if ok:
                add_history_event("Busca Iniciada", f"Rotina {file} disparada localmente. Data Lógica: {logical_date or 'Atual'}")
                app_ctx = current_app._get_current_object().app_context()
                threading.Thread(
                    target=watch_dag_and_update_mentions, 
                    args=(app_ctx, [run_info], file, routine_emails, routine_subject, logical_date, routine_cnpjs, run_info.get("trigger_time")), 
                    daemon=True
                ).start()
                return jsonify({"status": "success", "message": f"Busca {dag_id} iniciada!"})
            else:
                add_history_event("Busca (Tentativa)", f"Tentativa de disparar {dag_id}: {msg}")
                return jsonify({"status": "warning", "message": "Busca solicitada, mas houve erro ao iniciar a execução.", "details": msg})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@dags_bp.route('/routines/check_date', methods=['GET'])
@login_required
def api_check_date():
    """Verifica se uma data específica já possui dados baixados no INLABS/PostgreSQL."""
    from sqlalchemy import text
    from ..models import InlabsDownloadLog
    from ..services.holiday_service import is_business_day, is_within_inlabs_retention_window
    from ..services.inlabs_service import InlabsUnavailable, get_inlabs_postgres_engine
    
    target_date = request.args.get('date', '').strip()
    if not target_date:
        return jsonify({"status": "error", "message": "Parâmetro date é obrigatório."}), 400
        
    try:
        target_date = normalize_date_str(target_date)
    except ValueError:
        return jsonify({"status": "error", "message": "Data inválida. Use o formato DD/MM/AAAA."}), 400
    
    already_loaded = False
    articles_count = 0
    
    try:
        engine = get_inlabs_postgres_engine()
        with engine.connect() as conn:
            conn.execute(text("SET statement_timeout = 5000"))
            res = conn.execute(
                text("SELECT COUNT(*) FROM dou_inlabs.article_raw WHERE CAST(pubdate AS DATE) = :dt"),
                {"dt": target_date}
            ).scalar()
            if res and int(res) > 0:
                already_loaded = True
                articles_count = int(res)
    except InlabsUnavailable:
        pass  # sem INLABS local: o dia nunca está "carregado"
    except Exception:
        log = InlabsDownloadLog.query.filter_by(date_str=target_date, status='success').first()
        if log:
            already_loaded = True
            articles_count = 1
            
    is_bus = True
    holiday_reason = ""
    try:
        d_obj = datetime.strptime(target_date, '%Y-%m-%d').date()
        is_bus, holiday_reason = is_business_day(d_obj)
    except Exception:
        pass

    is_within_120 = is_within_inlabs_retention_window(target_date, 120)
            
    return jsonify({
        "status": "success",
        "date": target_date,
        "already_loaded": already_loaded,
        "articles_count": articles_count,
        "is_business_day": is_bus,
        "holiday_reason": holiday_reason,
        "is_within_120": is_within_120
    })

@dags_bp.route('/routines/monthly_inlabs_check', methods=['GET'])
@login_required
def api_monthly_inlabs_check():
    from ..services.holiday_service import get_business_days_for_month, is_within_inlabs_retention_window
    from ..services.inlabs_service import get_downloaded_dates
    
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    routine_file = request.args.get('routine', '')
    
    if not month or not year:
        return jsonify({"status": "error", "message": "Mês e ano são obrigatórios."}), 400
    
    # Checar se a rotina usa INLABS
    dag_confs_path = get_dag_confs_path()
    file_path = os.path.join(dag_confs_path, routine_file)
    uses_inlabs = False
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                yaml_data = yaml.safe_load(f)
                search = yaml_data.get('dag', {}).get('search', {})
                if isinstance(search, list): search = search[0] if search else {}
                sources = search.get('sources', ['DOU'])
                uses_inlabs = 'INLABS' in sources
        except: pass
    
    # Gerar dias úteis do mês descontando fins de semana e feriados nacionais (fixos e móveis)
    weekdays = get_business_days_for_month(year, month, cap_today=True)
    if not weekdays:
        return jsonify({
            "status": "ok",
            "scenario": "complete",
            "uses_inlabs": uses_inlabs,
            "total_weekdays": 0,
            "inlabs_days": [],
            "inlabs_count": 0,
            "missing_days": [],
            "missing_count": 0,
            "downloadable_inlabs_days": [],
            "downloadable_count": 0,
            "api_dou_days": [],
            "api_dou_count": 0
        })
    
    first_day = weekdays[0]
    last_day_str = weekdays[-1]
    downloaded = get_downloaded_dates(first_day, last_day_str)
    
    inlabs_days = sorted([d for d in weekdays if d in downloaded])
    missing_days = sorted([d for d in weekdays if d not in downloaded])
    
    # Segregar dias faltantes: dentro da janela de 120 dias do INLABS vs anteriores (API DOU)
    downloadable_inlabs_days = [d for d in missing_days if is_within_inlabs_retention_window(d, 120)]
    api_dou_days = [d for d in missing_days if not is_within_inlabs_retention_window(d, 120)]
    
    if not missing_days:
        scenario = "complete"
    elif len(inlabs_days) == 0 and len(downloadable_inlabs_days) == 0:
        scenario = "all_api_dou"
    elif len(api_dou_days) > 0 and (len(inlabs_days) > 0 or len(downloadable_inlabs_days) > 0):
        scenario = "mixed"
    else:
        scenario = "download_only"

    return jsonify({
        "status": "ok",
        "scenario": scenario,
        "uses_inlabs": uses_inlabs,
        "total_weekdays": len(weekdays),
        "inlabs_days": inlabs_days,
        "inlabs_count": len(inlabs_days),
        "missing_days": missing_days,
        "missing_count": len(missing_days),
        "downloadable_inlabs_days": downloadable_inlabs_days,
        "downloadable_count": len(downloadable_inlabs_days),
        "api_dou_days": api_dou_days,
        "api_dou_count": len(api_dou_days)
    })

@dags_bp.route('/routines/download_missing_inlabs', methods=['POST'])
@login_required
def api_download_missing_inlabs():
    """Dispara o download no INLABS (ro-dou_inlabs_load_pg) para os dias faltantes dentro da janela de 120 dias."""
    from ..services.holiday_service import get_business_days_for_month, is_within_inlabs_retention_window
    from ..services.inlabs_service import get_downloaded_dates, enforce_inlabs_retention_limit, record_inlabs_download_success

    data = request.get_json() or {}
    days = data.get('days', [])
    if not days:
        try:
            year = int(data.get('year'))
            month = int(data.get('month'))
            weekdays = get_business_days_for_month(year, month, cap_today=True)
            if weekdays:
                downloaded = get_downloaded_dates(weekdays[0], weekdays[-1])
                days = [d for d in weekdays if d not in downloaded]
        except Exception as e:
            return jsonify({"status": "error", "message": f"Erro ao identificar dias: {e}"}), 400

    # Filtra apenas dias dentro da janela de 120 dias do INLABS
    downloadable_days = [d for d in days if is_within_inlabs_retention_window(d, 120)]

    if not downloadable_days:
        return jsonify({"status": "ok", "message": "Nenhum dia disponível para download no portal INLABS (fora da janela de 120 dias). A busca será realizada via API DOU."})

    if not os.getenv("INLABS_DB_URL"):
        try:
            from ..runtime.pg_portable import get_portable_postgres
            pg = get_portable_postgres()
            if pg.get_connection_info() is None or not pg.is_running():
                return jsonify({
                    "status": "ok",
                    "message": "PostgreSQL portátil INLABS indisponível no momento. A busca utilizará a API Oficial do DOU.",
                    "days": downloadable_days,
                })
        except Exception:
            return jsonify({
                "status": "ok",
                "message": "PostgreSQL portátil INLABS indisponível no momento. A busca utilizará a API Oficial do DOU.",
                "days": downloadable_days,
            })

    from ..services.inlabs_service import check_inlabs_portal_status
    portal_ok, portal_msg = check_inlabs_portal_status()
    if not portal_ok:
        return jsonify({
            "status": "ok",
            "message": f"{portal_msg}. A busca utilizará a API Oficial do DOU.",
            "days": downloadable_days,
        })

    import threading
    def run_downloads(app_context, target_days):
        import time
        from datetime import datetime, timezone, timedelta
        with app_context:
            from ..models import db, SyncHistory
            # Aplica limite de 120 dias protegendo os dias solicitados
            enforce_inlabs_retention_limit(max_days=120, protected_dates=target_days)
            
            sucessos = 0
            run_ids = []
            date_by_run = {}
            exec_inst = get_executor()
            for d_str in target_days:
                try:
                    r_id = exec_inst.trigger("ro-dou_inlabs_load_pg", date=d_str)
                    if r_id:
                        run_ids.append(r_id)
                        date_by_run[r_id] = d_str
                        sucessos += 1
                except Exception as exc:
                    logging.warning("Falha ao disparar carga INLABS local (%s): %s", d_str, exc)
                
            try:
                hist = SyncHistory(
                    data=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M:%S'),
                    evento="Download INLABS Solicitado",
                    detalhes=f"Disparado download INLABS para {len(target_days)} dia(s) faltantes ({sucessos} execuções acionadas)."
                )
                db.session.add(hist)
                db.session.commit()
            except: pass

            if run_ids:
                max_wait_sec = max(1800, 300 * len(run_ids))
                finished_all, run_states = exec_inst.wait(run_ids, timeout=max_wait_sec)
                for r_id, st in run_states.items():
                    if st == 'success' and r_id in date_by_run:
                        record_inlabs_download_success(date_by_run[r_id])

    threading.Thread(target=run_downloads, args=(current_app._get_current_object().app_context(), downloadable_days), daemon=True).start()

    return jsonify({
        "status": "success",
        "message": f"Download de {len(downloadable_days)} dia(s) faltantes disparado em segundo plano no INLABS.",
        "days": downloadable_days
    })

@dags_bp.route('/routines/trigger_monthly', methods=['POST'])
@login_required
def api_trigger_monthly():
    data = request.get_json() or {}
    try:
        year = int(data.get('year'))
        month = int(data.get('month'))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Ano ou mês inválidos."}), 400
    routines = data.get('routines', [])
    mode = data.get('mode', 'full')  # 'full' ou 'inlabs_only'
    
    dag_confs_path = get_dag_confs_path()
    if not routines:
        # Pega todas as rotinas disponíveis
        yaml_files = [f for f in os.listdir(dag_confs_path) if f.endswith('.yaml') and not f.startswith('temp_') and '_part_' not in f]
        routines = yaml_files

    # Validar se as rotinas selecionadas estão ativas
    for rf in routines:
        fpath = os.path.join(dag_confs_path, rf)
        if os.path.exists(fpath):
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    yd = yaml.safe_load(f) or {}
                    is_act = yd.get('dag', {}).get('active')
                    if is_act is None:
                        is_act = yd.get('active', True)
                    if is_act is False:
                        return jsonify({"status": "error", "message": f"A rotina '{rf}' está pausada. Ative-a antes de disparar a busca mensal."}), 400
            except Exception:
                pass
    
    import threading
    
    def run_monthly_search_in_background(app_context, routines, month, year, mode='full'):
        import time
        from datetime import datetime, date
        import requests
        import yaml
        import re
        import os
        import glob
        import logging
        from ..services.holiday_service import get_business_days_for_month, is_within_inlabs_retention_window
        from ..services.inlabs_service import get_downloaded_dates, enforce_inlabs_retention_limit, record_inlabs_download_success
        from ..models import db, Settings

        confs_path = get_dag_confs_path()
                
        # Calcular dias úteis do mês (excluindo feriados e finais de semana) em ordem cronológica
        weekdays = get_business_days_for_month(year, month, cap_today=True)
        if not weekdays:
            with app_context:
                add_history_event("Busca Mensal Concluída", f"Nenhum dia útil com circulação do DOU encontrado para o mês {month}/{year}.")
            return

        with app_context:
            # 1. Aplica limite de retenção de 120 dias protegendo TODOS os dias úteis do mês pesquisado
            enforce_inlabs_retention_limit(max_days=120, protected_dates=weekdays)

            # 2. Verificar dias INLABS disponíveis
            first_day = weekdays[0]
            last_day_str = weekdays[-1]
            downloaded = get_downloaded_dates(first_day, last_day_str)
            
            inlabs_days = sorted([d for d in weekdays if d in downloaded])
            missing_days = sorted([d for d in weekdays if d not in downloaded])
            
            add_history_event("Busca Mensal Iniciada",
                f"Mês {str(month).zfill(2)}/{year} • {len(inlabs_days)} dias INLABS disponíveis, "
                f"{len(missing_days)} dias faltantes (período: {weekdays[0]} a {weekdays[-1]}), modo: {mode}")

        # ─── FASE 0: Se houver dias faltantes e modo for 'download_and_search' (ou 'full'), baixa no INLABS os dias na janela de 120 dias ───
        if mode in ('download_and_search', 'full') and missing_days:
            downloadable_missing = [d for d in missing_days if is_within_inlabs_retention_window(d, 120)]

            if downloadable_missing and not os.getenv("INLABS_DB_URL"):
                local_pg_ok = False
                try:
                    from ..runtime.pg_portable import get_portable_postgres
                    pg = get_portable_postgres()
                    local_pg_ok = (pg.get_connection_info() is not None and pg.is_running())
                except Exception:
                    local_pg_ok = False
                if not local_pg_ok:
                    with app_context:
                        add_history_event(
                            "INLABS Indisponível",
                            f"PostgreSQL portátil INLABS indisponível. Os {len(missing_days)} dia(s) faltantes de {str(month).zfill(2)}/{year} serão pesquisados via API Oficial do DOU.",
                        )
                    downloadable_missing = []

            if downloadable_missing:
                from ..services.inlabs_service import check_inlabs_portal_status
                portal_ok, portal_msg = check_inlabs_portal_status()
                if not portal_ok:
                    # Portal fora do ar: não enfileira downloads que só falhariam
                    # (e travariam a fila); os dias faltantes seguem pela API DOU (FASE 2).
                    with app_context:
                        add_history_event("INLABS Indisponível",
                            f"{portal_msg}. Os {len(missing_days)} dia(s) faltantes de {str(month).zfill(2)}/{year} serão pesquisados via API Oficial do DOU.")
                    downloadable_missing = []
            
            if downloadable_missing:
                with app_context:
                    add_history_event("Download INLABS Solicitado",
                        f"Iniciando download dos {len(downloadable_missing)} dia(s) faltantes no INLABS antes da pesquisa mensal ({str(month).zfill(2)}/{year}).")
                
                triggered_load_run_ids = []
                date_by_run = {}
                exec_inst = get_executor()
                for d_str in downloadable_missing:
                    try:
                        with app_context:
                            r_id = exec_inst.trigger("ro-dou_inlabs_load_pg", date=d_str)
                        if r_id:
                            triggered_load_run_ids.append(r_id)
                            date_by_run[r_id] = d_str
                    except Exception as exc:
                        logging.warning("Falha ao disparar carga INLABS local (%s): %s", d_str, exc)

                if triggered_load_run_ids:
                    max_wait_sec = max(1800, 300 * len(triggered_load_run_ids))
                    with app_context:
                        finished_all, run_states = exec_inst.wait(
                            triggered_load_run_ids, timeout=max_wait_sec
                        )
                    
                    with app_context:
                        for r_id, st in run_states.items():
                            if st == 'success' and r_id in date_by_run:
                                record_inlabs_download_success(date_by_run[r_id])

                    if not finished_all:
                        logging.warning("Downloads INLABS não concluídos no tempo limite; dias pendentes seguirão pela API DOU.")

                    # Revalidação direta no PostgreSQL
                    first_day = weekdays[0]
                    last_day_str = weekdays[-1]
                    with app_context:
                        actual_downloaded = get_downloaded_dates(first_day, last_day_str)
                    inlabs_days = sorted([d for d in weekdays if d in actual_downloaded])
                    missing_days = sorted([d for d in weekdays if d not in actual_downloaded])

                    with app_context:
                        add_history_event("Download INLABS Concluído",
                            f"Download finalizado. {len(inlabs_days)} de {len(weekdays)} dias úteis disponíveis no PostgreSQL. Iniciando agora as pesquisas nas rotinas...")

        # ─── FASE 1: Disparar DAGs INLABS para dias com dados ───
        all_emails = set()
        triggered_inlabs_dags = []
        all_triggered_runs = []
        
        # Coleta os e-mails de todas as rotinas selecionadas
        for routine_file in routines:
            file_path = os.path.join(confs_path, routine_file)
            if not os.path.exists(file_path): continue
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    yaml_data = yaml.safe_load(f) or {}
                r_emails = yaml_data.get('dag', {}).get('report', {}).get('emails', [])
                if isinstance(r_emails, list):
                    all_emails.update(r_emails)
            except Exception:
                pass

        inlabs_run_ids = []
        if mode != 'api_dou_only' and inlabs_days:
            for routine_file in routines:
                file_path = os.path.join(confs_path, routine_file)
                if not os.path.exists(file_path): continue
                
                # Tratamento unificado para rotinas de CNPJ (sync, particionadas ou arquivo único)
                files_to_process = [file_path]
                if routine_file in ("Pesquisa_cnpj.yaml", "Pesquisa_cnpj_sync.yaml"):
                    parts = glob.glob(os.path.join(confs_path, "Pesquisa_cnpj_sync.yaml"))
                    if not parts:
                        parts = glob.glob(os.path.join(confs_path, "Pesquisa_cnpj_part_*.yaml"))
                    if parts:
                        files_to_process = parts

                for p_file in files_to_process:
                    if not os.path.exists(p_file): continue
                    try:
                        with open(p_file, 'r', encoding='utf-8') as pf:
                            pdata = yaml.safe_load(pf) or {}
                        
                        r_emails = pdata.get('dag', {}).get('report', {}).get('emails', [])
                        if isinstance(r_emails, list):
                            all_emails.update(r_emails)
                            
                        pid = pdata.get('dag', {}).get('id')
                        if not pid:
                            pid = re.sub(r'\.[^.]*$', '', os.path.basename(p_file))
                            
                        for date_str in inlabs_days:
                            ok, msg, run_info = _dispatch_routine(pid, date_str)
                            if ok:
                                if pid not in triggered_inlabs_dags:
                                    triggered_inlabs_dags.append(pid)
                                if isinstance(run_info, dict) and run_info.get("dag_run_id"):
                                    all_triggered_runs.append(run_info)
                                    inlabs_run_ids.append(run_info["dag_run_id"])
                    except Exception as e:
                        logging.error(f"Erro ao disparar rotina INLABS {p_file}: {e}")

            if inlabs_run_ids:
                with app_context:
                    get_executor().wait(inlabs_run_ids, timeout=1200)

        # ─── FASE 2: DAG Temporária para dias sem INLABS (modo 'full', 'download_and_search' ou 'api_dou_only') ───
        temp_dag_id = None
        temp_yaml_path = None
        
        dou_target_days = weekdays if mode == 'api_dou_only' else missing_days
        
        if mode in ('full', 'download_and_search', 'api_dou_only') and dou_target_days and routines:
            try:
                temp_search_blocks = []
                for routine_file in routines:
                    routine_path = os.path.join(confs_path, routine_file)
                    
                    files_to_read = [routine_path]
                    if routine_file in ("Pesquisa_cnpj.yaml", "Pesquisa_cnpj_sync.yaml"):
                        parts = glob.glob(os.path.join(confs_path, "Pesquisa_cnpj_sync.yaml"))
                        if not parts:
                            parts = glob.glob(os.path.join(confs_path, "Pesquisa_cnpj_part_*.yaml"))
                        if parts:
                            files_to_read = parts

                    for r_subfile in files_to_read:
                        if not os.path.exists(r_subfile):
                            continue
                        try:
                            with open(r_subfile, 'r', encoding='utf-8') as f:
                                base_yaml = yaml.safe_load(f) or {}
                        except Exception:
                            continue
                        
                        original_searches = base_yaml.get('dag', {}).get('search', [])
                        if not isinstance(original_searches, list):
                            original_searches = [original_searches] if original_searches else []
                        
                        for idx, block in enumerate(original_searches):
                            temp_block = {
                                "header": block.get("header", f"Busca API-DOU {os.path.basename(r_subfile)} - PARTE {idx+1}"),
                                "is_exact_search": block.get("is_exact_search", False),
                                "force_rematch": True,
                                "terms": block.get("terms", []),
                                "dou_sections": block.get("dou_sections", DEFAULT_DOU_SECTIONS),
                                "field": block.get("field", "TUDO"),
                                "full_text": block.get("full_text", True),
                                "date": "DIA",
                                "sources": ["DOU"] if mode == 'api_dou_only' else _fallback_sources(),
                            }
                            if block.get("department"): temp_block["department"] = block["department"]
                            if block.get("organs"): temp_block["organs"] = block["organs"]
                            if block.get("terms_ignore"): temp_block["terms_ignore"] = block["terms_ignore"]
                            temp_search_blocks.append(temp_block)
                
                if temp_search_blocks:
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    temp_dag_id = f"temp_monthly_dou_{timestamp}"
                    
                    temp_yaml = {
                        "dag": {
                            "id": temp_dag_id,
                            "description": f"Busca temporária API-DOU para mês {str(month).zfill(2)}/{year}",
                            "schedule": None,
                            "tags": ["temp", "api_dou", "monthly"],
                            "search": temp_search_blocks,
                            "report": {
                                "page_title": f"Busca Mensal API-DOU {str(month).zfill(2)}/{year}",
                                "emails": [],
                                "subject": f"Registrale - Mensal API-DOU {str(month).zfill(2)}/{year}"
                            }
                        }
                    }
                    
                    triggered_dou_dags = []
                    dou_run_ids = []
                    with app_context:
                        monthly_src = "API do DOU" if mode == 'api_dou_only' else _describe_local_fallback_source()
                        add_history_event(f"Busca Mensal ({monthly_src})",
                            f"Disparando busca via {monthly_src} para {len(dou_target_days)} dia(s) históricos/fora do INLABS.")

                    for date_str in dou_target_days:
                        ok, msg, run_info = _dispatch_routine(
                            temp_dag_id,
                            date_str,
                            yaml_dict=temp_yaml,
                        )
                        if ok:
                            if temp_dag_id not in triggered_dou_dags:
                                triggered_dou_dags.append(temp_dag_id)
                            if isinstance(run_info, dict) and run_info.get("dag_run_id"):
                                all_triggered_runs.append(run_info)
                                dou_run_ids.append(run_info["dag_run_id"])

                    if dou_run_ids:
                        with app_context:
                            get_executor().wait(dou_run_ids, timeout=max(1800, 300 * len(dou_run_ids)))
                            _cov_text, _pend = _summarize_coverage_from_runs(dou_run_ids)
                            if _pend:
                                add_history_event(
                                    "Busca Mensal com Pendências",
                                    f"Seções sem cobertura em algum dia: {', '.join(_pend)}. O resultado do mês pode estar incompleto; repita a busca mensal mais tarde.",
                                )
                        
            except Exception as e:
                logging.error(f"Erro ao criar/executar DAG temporária API-DOU: {e}")

        # ─── FASE 3: Consolidar menções recém-executadas e enviar e-mails ───
        with app_context:
            from ..services.mention_service import clear_mentions_cache
            from ..models import db, Settings, Mention, Company
            try:
                companies = Company.query.with_entities(Company.cnpj_norm, Company.nome, Company.cnpj).all()
                cnpj_map = {c.cnpj_norm: c.nome for c in companies if c.cnpj_norm}
                cnpj_map.update({c.cnpj: c.nome for c in companies if c.cnpj})
                
                # 1. Extrai as menções geradas especificamente pelos DAG Runs disparados
                monthly_new_mentions = []
                seen_ids = set()
                
                for r_info in all_triggered_runs:
                    did = r_info.get("dag_id")
                    run_id = r_info.get("dag_run_id")
                    if did and run_id:
                        extracted = fetch_mentions_from_dag_run(did, run_id, cnpj_map=cnpj_map)
                        for m in extracted:
                            if m['id'] not in seen_ids:
                                seen_ids.add(m['id'])
                                monthly_new_mentions.append(m)
                
                # 2. Persistir novas menções no banco SQLite
                if monthly_new_mentions:
                    from ..runtime.pdf_archiver import resolve_pdf_for_mention
                    m_ids = [m['id'] for m in monthly_new_mentions if m.get('id')]
                    existing_records = {e.id: e for e in Mention.query.filter(Mention.id.in_(m_ids)).all()} if m_ids else {}
                    for m in monthly_new_mentions:
                        pdf_path = m.get('pdf_path') or resolve_pdf_for_mention(m.get('data'), m.get('secao'))
                        existing = existing_records.get(m['id'])
                        if not existing:
                            payload = dict(m)
                            if pdf_path:
                                payload['pdf_path'] = pdf_path
                            db.session.add(Mention(**payload))
                        else:
                            existing.empresa = m.get('empresa', existing.empresa)
                            existing.secao = m.get('secao', existing.secao)
                            existing.data = m.get('data', existing.data)
                            existing.detected_at = m.get('detected_at', existing.detected_at)
                            existing.trecho = m.get('trecho', existing.trecho)
                            existing.link = m.get('link', existing.link)
                            if pdf_path:
                                existing.pdf_path = pdf_path
                    db.session.commit()
                
                clear_mentions_cache()
                
                month_str_slash = f"/{str(month).zfill(2)}/{year}"
                month_str_iso = f"{year}-{str(month).zfill(2)}-"
                month_str_alt = f"-{str(month).zfill(2)}-{year}"
                relevant_monthly_mentions = [
                    m for m in monthly_new_mentions
                    if month_str_slash in m.get('data', '') or month_str_iso in m.get('data', '') or month_str_alt in m.get('data', '')
                ]
                if not relevant_monthly_mentions and monthly_new_mentions:
                    relevant_monthly_mentions = monthly_new_mentions
                
                logging.info(f"Busca Mensal FASE 3: {len(monthly_new_mentions)} menções novas extraídas, {len(relevant_monthly_mentions)} para o relatório do mês {month}/{year}")
                
                emails = list(all_emails)
                if not emails:
                    settings_record = Settings.query.filter_by(key='global_settings').first()
                    if settings_record:
                        smtp_data = settings_record.get_value().get('smtp', {})
                        smtp_from = smtp_data.get('from_email') or smtp_data.get('user', '')
                        if smtp_from: emails = [smtp_from]
                emails = [e.strip() for e in emails if e and str(e).strip()]
                
                monthly_source_tag = ""
                monthly_run_ids = [
                    r_info.get("dag_run_id") for r_info in all_triggered_runs
                    if isinstance(r_info, dict) and r_info.get("dag_run_id")
                ]
                monthly_sources_label = _extract_sources_used_from_runs(monthly_run_ids)
                if monthly_sources_label:
                    monthly_source_tag = f" [Fonte: {monthly_sources_label}]"

                from ..services.email_service import is_smtp_enabled
                if not is_smtp_enabled():
                    add_history_event(
                        "E-mail desativado",
                        f"Envio de e-mail desativado nas configurações. Busca mensal {month}/{year} gravou {len(relevant_monthly_mentions)} menção(ões){monthly_source_tag}."
                    )
                elif not emails:
                    add_history_event("Busca Mensal Concluída", f"Busca finalizada ({len(relevant_monthly_mentions)} menções em {month}/{year}){monthly_source_tag}, mas nenhum destinatário de e-mail configurado.")
                elif not relevant_monthly_mentions:
                    add_history_event("Busca Mensal Concluída", f"Nenhuma menção encontrada para o mês {month}/{year}{monthly_source_tag}.")
                else:
                    from ..services.email_service import EmailSender, build_mentions_email_html, render_email_subject
                    sender = EmailSender(None)
                    
                    html = build_mentions_email_html(
                        relevant_monthly_mentions,
                        template_name='Relatório Mensal Registrale',
                        title=f"Relatório Consolidado de Menções ({month}/{year})",
                        subtitle=f"Abaixo constam as {len(relevant_monthly_mentions)} publicações identificadas pelo sistema Registrale no período consolidado:"
                    )
                    try:
                        sender.send_custom_email(
                            to_emails=emails,
                            subject=render_email_subject(
                                None, relevant_monthly_mentions, template_name='Relatório Mensal Registrale',
                                date_str=f"{str(month).zfill(2)}/{year}",
                                fallback=f"Registrale - Relatório Mensal {month}/{year}"),
                            html_content=html
                        )
                        add_history_event("Busca Mensal Concluída",
                            f"Relatório mensal {month}/{year} enviado com {len(relevant_monthly_mentions)} menções para {len(emails)} destinatário(s){monthly_source_tag}.")
                    except Exception as e_mail:
                        logging.error(f"Erro ao enviar e-mail da busca mensal {month}/{year}: {e_mail}")
                        add_history_event("Erro Envio E-mail", f"Falha ao enviar e-mail do relatório mensal {month}/{year}: {str(e_mail)}")
            except Exception as e:
                logging.error(f"Erro ao consolidar busca mensal: {e}")
                add_history_event("Erro (Busca Mensal)", str(e))

    app_context = current_app._get_current_object().app_context()
    threading.Thread(target=run_monthly_search_in_background, args=(app_context, routines, month, year, mode), daemon=True).start()
    return jsonify({"status": "success", "message": "Busca mensal iniciada em segundo plano."})


_MANUAL_ARCHIVE_LOCK = threading.Lock()
_MANUAL_ARCHIVE_RUNNING = False


@dags_bp.route('/pdf_archive/status', methods=['GET'])
@login_required
def api_pdf_archive_status():
    from ..runtime.pdf_archiver import get_pdf_archive_config, get_pdf_archive_status
    archive_status = get_pdf_archive_status()
    archive_status["running"] = bool(archive_status.get("running") or _MANUAL_ARCHIVE_RUNNING)
    return jsonify({
        "status": "ok",
        "config": get_pdf_archive_config(),
        "archive_status": archive_status,
    })


@dags_bp.route('/pdf_archive/run', methods=['POST'])
@login_required
def api_pdf_archive_run():
    global _MANUAL_ARCHIVE_RUNNING
    if session.get('user', {}).get('role') != 'master':
        return jsonify({"status": "error", "message": "Acesso negado."}), 403

    from ..runtime.pdf_archiver import (
        _BRASILIA_TZ,
        _save_pdf_archive_status,
        archive_date_pdfs,
        archive_month_pdfs,
        normalize_date_iso,
    )

    data = request.json or {}
    raw_date = str(data.get("date") or "").strip()
    year = data.get("year")
    month = data.get("month")
    run_sync = bool(data.get("sync", False))
    sections = data.get("sections")

    if not raw_date and (not year or not month):
        return jsonify({"status": "error", "message": "Informe uma data ou mês/ano."}), 400

    parsed_year = None
    parsed_month = None
    if raw_date:
        try:
            raw_date = normalize_date_iso(raw_date)
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 400
    else:
        try:
            parsed_year = int(year)
            parsed_month = int(month)
            if not (2000 <= parsed_year <= 2100 and 1 <= parsed_month <= 12):
                raise ValueError("Ano ou mês fora do intervalo válido.")
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "Ano ou mês inválido."}), 400

    def _execute(app_ctx):
        global _MANUAL_ARCHIVE_RUNNING
        with app_ctx:
            try:
                if raw_date:
                    res = archive_date_pdfs(raw_date, sections=sections)
                else:
                    res = archive_month_pdfs(parsed_year, parsed_month, sections=sections)
                add_history_event("Arquivo PDF DOU", res.get("message", "Arquivamento concluído."))
                return res
            except Exception as exc:
                now_str = datetime.now(_BRASILIA_TZ).strftime("%d/%m/%Y %H:%M:%S")
                ref_label = raw_date if raw_date else f"{str(parsed_month).zfill(2)}/{parsed_year}"
                _save_pdf_archive_status({
                    "last_run_at": now_str,
                    "last_date": ref_label,
                    "last_source": "-",
                    "last_status": "error",
                    "last_message": f"Falha ao arquivar PDFs: {exc}",
                    "saved_files": [],
                    "skipped_files": [],
                    "errors": [str(exc)],
                })
                add_history_event("Erro Arquivo PDF", str(exc))
                return {"status": "error", "message": str(exc)}
            finally:
                with _MANUAL_ARCHIVE_LOCK:
                    _MANUAL_ARCHIVE_RUNNING = False

    app_obj = current_app._get_current_object()
    if run_sync:
        with _MANUAL_ARCHIVE_LOCK:
            _MANUAL_ARCHIVE_RUNNING = True
        res = _execute(app_obj.app_context())
        code = 200 if res.get("status") != "error" else 500
        return jsonify(res), code

    with _MANUAL_ARCHIVE_LOCK:
        _MANUAL_ARCHIVE_RUNNING = True
    threading.Thread(target=_execute, args=(app_obj.app_context(),), daemon=True).start()
    target_label = raw_date if raw_date else f"{str(parsed_month).zfill(2)}/{parsed_year}"
    return jsonify({
        "status": "success",
        "message": f"Arquivamento de PDFs para {target_label} iniciado em segundo plano.",
    })


@dags_bp.route('/pdf_archive/open', methods=['GET'])
@login_required
def api_pdf_archive_open():
    from pathlib import Path
    from flask import send_file
    from ..runtime.pdf_archiver import get_pdf_archive_config, resolve_pdf_for_mention

    mention_id = request.args.get("mention_id")
    raw_date = request.args.get("date")
    raw_section = request.args.get("section") or "1"

    cfg = get_pdf_archive_config()
    base_folder = Path(cfg["folder"]).resolve()
    pdf_path_str = None

    if mention_id:
        mention = Mention.query.get(mention_id)
        if not mention:
            return jsonify({"status": "error", "message": "Menção não encontrada."}), 404
        if mention.pdf_path and os.path.isfile(mention.pdf_path):
            pdf_path_str = mention.pdf_path
        else:
            pdf_path_str = resolve_pdf_for_mention(mention.data, mention.secao, folder=base_folder)
    elif raw_date:
        pdf_path_str = resolve_pdf_for_mention(raw_date, raw_section, folder=base_folder)
    else:
        return jsonify({"status": "error", "message": "Parâmetro mention_id ou date obrigatório."}), 400

    if not pdf_path_str:
        return jsonify({"status": "error", "message": "PDF do dia não encontrado no arquivo local."}), 404

    resolved = Path(pdf_path_str).resolve()
    if not resolved.is_relative_to(base_folder) or not resolved.is_file():
        return jsonify({"status": "error", "message": "Acesso negado ao arquivo PDF."}), 403

    return send_file(str(resolved), mimetype="application/pdf", as_attachment=False, download_name=resolved.name)


@dags_bp.route('/pdf_archive/reorganize', methods=['POST'])
@login_required
def api_pdf_archive_reorganize():
    if session.get('user', {}).get('role') != 'master':
        return jsonify({"status": "error", "message": "Acesso negado."}), 403

    from ..runtime.pdf_archiver import (
        get_pdf_archive_config,
        normalize_pdf_layout,
        reorganize_pdfs,
    )

    data = request.get_json(silent=True) or {}
    dry_run = bool(data.get("dry_run", False))
    confirm = bool(data.get("confirm", False))
    if not dry_run and not confirm:
        return jsonify({
            "status": "error",
            "message": "Confirmação obrigatória para reorganizar os PDFs existentes.",
        }), 400

    cfg = get_pdf_archive_config()
    target_layout = normalize_pdf_layout(data.get("layout") or cfg.get("layout"))
    res = reorganize_pdfs(cfg["folder"], target_layout, dry_run=dry_run)
    if not dry_run and res.get("status") == "success":
        try:
            from ..models import Settings

            rec = Settings.query.filter_by(key="global_settings").first()
            val = rec.get_value() if rec else {}
            if not isinstance(val, dict):
                val = {}
            if not rec:
                rec = Settings(key="global_settings")
                db.session.add(rec)
            pa = dict(val.get("pdf_archive") or {})
            pa.setdefault("enabled", cfg.get("enabled", True))
            pa.setdefault("folder", cfg.get("folder"))
            pa.setdefault("sections", cfg.get("sections"))
            pa["layout"] = target_layout
            val["pdf_archive"] = pa
            rec.set_value(val)
            db.session.commit()
        except Exception:
            db.session.rollback()
    if not dry_run and res.get("moved", 0) > 0:
        add_history_event("Reorganização de PDFs", res.get("message", "Reorganização concluída."))
    code = 200 if res.get("status") == "success" else 500
    return jsonify(res), code
