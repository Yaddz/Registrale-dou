import os
import time
import re
import uuid
import html as html_module
from datetime import datetime, timezone, timedelta

_mentions_cache = None
_mentions_cache_time = 0

RE_TAGS_INTERNAL = re.compile(r"</?%>")
RE_HIGHLIGHT = re.compile(r"<span[^>]*class=['\"]highlight['\"][^>]*>.*?</span>", re.IGNORECASE)
RE_TABLE_PLACEHOLDER = re.compile(r'\[Tabela de \d+ linhas omitida\]', re.IGNORECASE)
RE_ALL_TAGS = re.compile(r'<[^>]+>')
RE_WHITESPACE = re.compile(r'\s+')
RE_ALPHANUMERIC = re.compile(r'[^A-Za-z0-9]')
RE_IS_ALPHANUMERIC = re.compile(r'[A-Za-z0-9]')

def _cnpj_branch_regex(term_clean):
    """Para um CNPJ (14 caracteres), regex que casa qualquer estabelecimento
    da mesma raiz (matriz/filial), com ou sem pontuação. Espelha
    src/utils/cnpj.py (o painel não importa o código das DAGs)."""
    if not term_clean or not re.match(r'^[0-9A-Z]{12}[0-9]{2}$', term_clean):
        return None
    r = [re.escape(c) for c in term_clean[:8]]
    core = rf"{''.join(r[0:2])}\.?\s*{''.join(r[2:5])}\.?\s*{''.join(r[5:8])}"
    dotted = rf"{''.join(r[0:2])}\.{''.join(r[2:5])}\.{''.join(r[5:8])}"
    # CNPJ completo de qualquer estabelecimento OU raiz pontuada isolada
    # (ANVISA publica só a raiz; ",dd" excluído para não casar valores em R$)
    return re.compile(
        rf"(?<![0-9A-Za-z]){core}\s*/?\s*[0-9A-Za-z]{{4}}\s*-?\s*[0-9]{{2}}(?![0-9])"
        rf"|(?<![0-9A-Za-z.]){dotted}(?![0-9A-Za-z]|\s*/\s*[0-9A-Za-z]|,\d)",
        re.IGNORECASE,
    )


def normalize_cnpj(cnpj):
    if not cnpj: return ""
    return RE_ALPHANUMERIC.sub('', str(cnpj)).upper()

def clean_abstract_for_dashboard(raw_text, search_term=''):
    """Limpa o abstract removendo HTML e marcadores, centralizando no termo buscado."""
    if not raw_text:
        return ''
    
    text = raw_text
    
    # Recorte e centralização são feitos sobre o TEXTO VISÍVEL (sem tags).
    # Antes os spans de destaque eram restaurados antes do recorte: os
    # caracteres dos atributos (class/style) deslocavam a posição do termo e o
    # corte caía no meio da tag, exibindo HTML cru no painel.
    highlighted_terms = []

    def unwrap_highlight(match):
        inner = RE_ALL_TAGS.sub('', match.group(0))
        if inner.strip():
            highlighted_terms.append(html_module.unescape(inner).strip())
        return inner

    text = RE_TAGS_INTERNAL.sub('', text)
    text = RE_HIGHLIGHT.sub(unwrap_highlight, text)
    text = RE_TABLE_PLACEHOLDER.sub('', text)
    text = RE_ALL_TAGS.sub(' ', text)
    text = html_module.unescape(text)
    text = RE_WHITESPACE.sub(' ', text).strip()

    excerpt = None
    term_clean = RE_ALPHANUMERIC.sub('', search_term or '').upper()
    branch_rx = _cnpj_branch_regex(term_clean)
    branch_match = branch_rx.search(text) if branch_rx else None
    if branch_match:
        # CNPJ: centraliza no estabelecimento citado (matriz ou filial da raiz)
        original_pos = branch_match.start()
        start = max(0, original_pos - 250)
        end = min(len(text), original_pos + 250)
        excerpt = text[start:end].strip()
        if start > 0:
            excerpt = '...' + excerpt
        if end < len(text):
            excerpt = excerpt + '...'
    elif term_clean:
        text_upper = RE_ALPHANUMERIC.sub('', text).upper()
        pos = text_upper.find(term_clean)
        if pos >= 0:
            # Mapear posição normalizada de volta ao texto original
            char_count = 0
            original_pos = 0
            for i, ch in enumerate(text):
                if RE_IS_ALPHANUMERIC.match(ch):
                    if char_count == pos:
                        original_pos = i
                        break
                    char_count += 1
            start = max(0, original_pos - 250)
            end = min(len(text), original_pos + 250)
            excerpt = text[start:end].strip()
            if start > 0:
                excerpt = '...' + excerpt
            if end < len(text):
                excerpt = excerpt + '...'
    if excerpt is None:
        excerpt = text[:500] + '...' if len(text) > 500 else text

    # Escapa o texto e reaplica o destaque (termo buscado, tolerando a
    # pontuação da máscara de CNPJ, e trechos já destacados pela fonte).
    safe = html_module.escape(excerpt, quote=False)
    patterns = []
    if branch_rx:
        patterns.append(branch_rx.pattern)
    elif term_clean:
        patterns.append(r'[^A-Za-z0-9]{0,3}'.join(re.escape(c) for c in term_clean))
    for t in highlighted_terms:
        if len(RE_ALPHANUMERIC.sub('', t)) >= 3:
            patterns.append(re.escape(html_module.escape(t, quote=False)))
    if patterns:
        patterns.sort(key=len, reverse=True)
        rx = re.compile('(' + '|'.join(patterns) + ')', re.IGNORECASE)
        safe = rx.sub(lambda m: f"<span class='highlight' style='background:#FFA;'>{m.group(0)}</span>", safe)
    return safe

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
