import os
import glob
import time
import re
import ast
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
LOGS_DIR = os.path.join(BASE_DIR, "mnt", "airflow-logs")

_mentions_cache = None
_mentions_cache_time = 0
_mentions_deleted_at = 0

def normalize_cnpj(cnpj):
    if not cnpj: return ""
    return re.sub(r'[^A-Za-z0-9]', '', str(cnpj)).upper()

import html as html_module

def clean_abstract_for_dashboard(raw_text, search_term=''):
    """Limpa o abstract removendo HTML e marcadores, centralizando no termo buscado."""
    if not raw_text:
        return ''
    
    # Preservar highlights de CNPJ e outros spans
    import uuid
    highlights = {}
    def preserve_highlight(match):
        key = f"__HL_{uuid.uuid4().hex[:8]}__"
        highlights[key] = match.group(0)
        return key
    
    # Limpa apenas marcadores internos obscuros
    text = text.replace("<%>", "").replace("</%>", "")
    
    # Extrai os spans highlight temporariamente
    text = re.sub(r"<span[^>]*class=['\"]highlight['\"][^>]*>.*?</span>", preserve_highlight, text)
    
    # Remove placeholders de tabela
    text = re.sub(r'\[Tabela de \d+ linhas omitida\]', '', text)
    
    # Remove TODAS as outras tags HTML
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Decodifica entidades HTML
    text = html_module.unescape(text)
    
    # Colapsa espaços múltiplos e quebras de linha
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Restaura highlights
    for key, val in highlights.items():
        text = text.replace(key, val)
    
    # Centralizar no termo buscado (CNPJ ou nome)
    if search_term:
        term_clean = re.sub(r'[^A-Za-z0-9]', '', search_term).upper()
        text_upper = re.sub(r'[^A-Za-z0-9]', '', text).upper()
        pos = text_upper.find(term_clean)
        if pos >= 0:
            # Mapear posição normalizada de volta ao texto original
            char_count = 0
            original_pos = 0
            for i, ch in enumerate(text):
                if re.match(r'[A-Za-z0-9]', ch):
                    if char_count == pos:
                        original_pos = i
                        break
                    char_count += 1
            
            start = max(0, original_pos - 250)
            end = min(len(text), original_pos + 250)
            excerpt = text[start:end]
            if start > 0:
                excerpt = '...' + excerpt
            if end < len(text):
                excerpt = excerpt + '...'
            return excerpt.strip()
    
    # Se não encontrou o termo, retorna os primeiros 500 chars
    if len(text) > 500:
        return text[:500] + '...'
    return text

def get_real_mentions():
    """Varre os logs do Airflow para extrair as menções reais encontradas, com cache otimizado."""
    global _mentions_cache, _mentions_cache_time, _mentions_deleted_at
    
    now = time.time()
    
    if not os.path.exists(LOGS_DIR): return []

    log_files = glob.glob(os.path.join(LOGS_DIR, "dag_id=*", "run_id=*", "task_id=exec_searchs.exec_search_*", "attempt=*.log"), recursive=True)
    if not log_files: return []

    try:
        latest_log_mtime = max(os.path.getmtime(f) for f in log_files)
    except:
        latest_log_mtime = 0

    from ..models import db, Settings, Company, Mention
    
    # We need a way to access app config, we'll assume we are within app_context
    from flask import current_app
    
    cache_data = {"last_parsed_at": 0, "mentions": []}
    cache_setting = Settings.query.filter_by(key='mentions_cache_meta').first()
    if cache_setting:
        cache_data["last_parsed_at"] = cache_setting.get_value().get("last_parsed_at", 0)
        
    if cache_data["last_parsed_at"] >= latest_log_mtime:
        cached_mentions = Mention.query.all()
        if cached_mentions:
            from ..models import DeletedMention
            deleted_ids = {dm.id for dm in DeletedMention.query.all()}
            result = [m.to_dict() for m in cached_mentions if m.id not in deleted_ids]
            _mentions_cache = result
            _mentions_cache_time = now
            return result

    metadata = Company.query.all()
    cnpj_map = {m.cnpj_norm: m.nome for m in metadata}

    mentions_dict = {}
    
    for log_path in log_files:
        try:
            with open(log_path, 'rb') as f:
                size = os.path.getsize(log_path)
                if size > 100000: # 100KB
                    f.seek(size - 100000)
                content = f.read().decode('utf-8', errors='ignore')
                
                matches = re.finditer(r"\[(.*?)\].*?Done\. Returned value was: (\{.*?\})$", content, re.MULTILINE)
                
                for match in matches:
                    log_time = match.group(1)
                    dict_str = match.group(2).strip()
                    
                    try:
                        result_dict = ast.literal_eval(dict_str)
                        results = result_dict.get('result', {}).get('single_group', {})
                        if not results: continue

                        for cnpj_raw_key, content_group in results.items():
                            cnpjs = [c.strip() for c in cnpj_raw_key.split(',')]
                            for cnpj_log in cnpjs:
                                cnpj_norm = normalize_cnpj(cnpj_log)
                            for dept_name, depts in content_group.items():
                                for pub in depts:
                                    import hashlib
                                    raw_abstract = pub.get('abstract', '')
                                    fallback_id = hashlib.md5(f"{cnpj_norm}_{pub.get('date', '')}_{raw_abstract}".encode('utf-8', errors='ignore')).hexdigest()
                                    pub_id = pub.get('id')
                                    if not pub_id:
                                        pub_id = fallback_id
                                    unique_key = f"{cnpj_norm}_{pub_id}"
                                    
                                    if unique_key not in mentions_dict or log_time > mentions_dict[unique_key]['detected_at']:
                                        raw_trecho = raw_abstract

                                        formatted_trecho = clean_abstract_for_dashboard(raw_trecho, cnpj_norm)

                                        empresa_nome = cnpj_map.get(cnpj_norm)
                                        if not empresa_nome:
                                            comp = Company.query.filter_by(cnpj_norm=cnpj_norm).first()
                                            if not comp or comp.nome == 'N/A':
                                                comp = Company.query.filter_by(cnpj=cnpj_log).first()
                                            empresa_nome = comp.nome if comp and comp.nome != 'N/A' else cnpj_log

                                        mentions_dict[unique_key] = {
                                            "id": unique_key,
                                            "empresa": empresa_nome,
                                            "cnpj": cnpj_log,
                                            "cnpj_norm": cnpj_norm,
                                            "secao": pub.get('section', 'DOU'),
                                            "data": pub.get('date', 'N/A'),
                                            "detected_at": log_time,
                                            "trecho": formatted_trecho,
                                            "link": pub.get('href', '#')
                                        }
                    except: continue
        except: continue

    mentions = list(mentions_dict.values())

    try:
        mentions.sort(key=lambda x: (
            datetime.strptime(x['data'], '%d/%m/%Y') if x['data'] != 'N/A' else datetime.min,
            x['detected_at']
        ), reverse=True)
    except: pass

    try:
        Mention.query.delete()
        
        from ..models import DeletedMention
        deleted_ids = {dm.id for dm in DeletedMention.query.all()}
        
        filtered_mentions = []
        for m in mentions:
            if m['id'] not in deleted_ids:
                new_m = Mention(**m)
                db.session.add(new_m)
                filtered_mentions.append(m)
        
        cache_setting = Settings.query.filter_by(key='mentions_cache_meta').first()
        if not cache_setting:
            cache_setting = Settings(key='mentions_cache_meta')
            db.session.add(cache_setting)
        cache_setting.set_value({"last_parsed_at": datetime.now(timezone(timedelta(hours=-3))).timestamp()})
        db.session.commit()
    except Exception as e:
        logger.error(f"Erro ao salvar cache de menções no BD: {e}")
        db.session.rollback()

    _mentions_cache = filtered_mentions
    _mentions_cache_time = time.time()
    return filtered_mentions

def clear_mentions_cache():
    global _mentions_cache, _mentions_cache_time, _mentions_deleted_at
    _mentions_cache = None
    _mentions_cache_time = 0
    _mentions_deleted_at = time.time()
