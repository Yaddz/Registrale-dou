import os
import time
import re
import uuid
import html as html_module
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

_mentions_cache = None
_mentions_cache_time = 0

def normalize_cnpj(cnpj):
    if not cnpj: return ""
    return re.sub(r'[^A-Za-z0-9]', '', str(cnpj)).upper()

def clean_abstract_for_dashboard(raw_text, search_term=''):
    """Limpa o abstract removendo HTML e marcadores, centralizando no termo buscado."""
    if not raw_text:
        return ''
    
    text = raw_text
    
    # Preservar highlights de CNPJ e outros spans
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
    """Retorna as menções salvas no banco de dados com altíssima performance e integridade."""
    global _mentions_cache, _mentions_cache_time
    
    from ..models import Mention
    
    now = time.time()
    if _mentions_cache is not None and (now - _mentions_cache_time) < 10:
        return _mentions_cache
    
    cached = Mention.query.all()
    result = [m.to_dict() for m in cached]
    try:
        result.sort(key=lambda x: (
            datetime.strptime(x['data'], '%d/%m/%Y') if x['data'] != 'N/A' else datetime.min,
            x.get('detected_at', '')
        ), reverse=True)
    except Exception:
        pass
    
    _mentions_cache = result
    _mentions_cache_time = now
    return result

def clear_mentions_cache():
    """Invalida o cache em memória."""
    global _mentions_cache, _mentions_cache_time
    _mentions_cache = None
    _mentions_cache_time = 0

def get_mentions_kpis():
    """Retorna contadores de menções diretamente do banco de dados."""
    from ..models import Mention, db
    from sqlalchemy import func
    
    hoje = datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y')
    mes = datetime.now(timezone(timedelta(hours=-3))).strftime('/%m/%Y')
    
    total = db.session.query(func.count(Mention.id)).scalar() or 0
    hoje_count = db.session.query(func.count(Mention.id)).filter(Mention.data == hoje).scalar() or 0
    mes_count = db.session.query(func.count(Mention.id)).filter(Mention.data.like(f"%{mes}")).scalar() or 0
    
    return total, hoje_count, mes_count
