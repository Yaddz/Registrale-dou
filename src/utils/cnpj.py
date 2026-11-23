"""Utilitários de CNPJ compartilhados pelas buscas (API DOU e INLABS).

Uma empresa monitorada é identificada pela RAIZ do CNPJ (8 primeiros
caracteres): publicações que citam qualquer estabelecimento (matriz ou
filial) com a mesma raiz são atribuídas a ela. Suporta o CNPJ numérico e o
novo formato alfanumérico (12 caracteres alfanuméricos + 2 dígitos).
"""

import re
from typing import List, Optional

CNPJ_RAW_RE = re.compile(r"^[0-9A-Z]{12}[0-9]{2}$")
_STRIP_RE = re.compile(r"[.\-/\s\"]")


def normalize_cnpj(term) -> Optional[str]:
    """Retorna o CNPJ sem máscara (14 caracteres) ou None se não for CNPJ."""
    if not isinstance(term, str):
        return None
    raw = _STRIP_RE.sub("", term.strip()).upper()
    if not CNPJ_RAW_RE.match(raw) or not any(c.isdigit() for c in raw[:12]):
        return None
    return raw


def format_cnpj(raw: str) -> str:
    return f"{raw[0:2]}.{raw[2:5]}.{raw[5:8]}/{raw[8:12]}-{raw[12:14]}"


def cnpj_root(term) -> Optional[str]:
    """Raiz (8 caracteres) do CNPJ, ou None se `term` não for CNPJ."""
    raw = normalize_cnpj(term)
    return raw[:8] if raw else None


def format_root(root: str) -> str:
    """Raiz no formato publicado no DOU: XX.XXX.XXX"""
    return f"{root[0:2]}.{root[2:5]}.{root[5:8]}"


def _root_core(root: str) -> str:
    r = [re.escape(c) for c in root.upper()]
    return rf"{''.join(r[0:2])}\.?\s*{''.join(r[2:5])}\.?\s*{''.join(r[5:8])}"


def branch_regex(root: str) -> "re.Pattern":
    """Regex (Python) que casa qualquer CNPJ completo com essa raiz, com ou
    sem pontuação. O grupo 1 é o sufixo do estabelecimento e o 2 o DV."""
    return re.compile(
        rf"(?<![0-9A-Za-z]){_root_core(root)}\s*/?\s*([0-9A-Za-z]{{4}})\s*-?\s*([0-9]{{2}})(?![0-9])",
        re.IGNORECASE,
    )


def branch_sql_pattern(root: str) -> str:
    """Padrão POSIX (PostgreSQL ~*) equivalente a `branch_regex`."""
    return rf"{_root_core(root)}\s*/?\s*[0-9A-Za-z]{{4}}\s*-?\s*[0-9]{{2}}"


def find_branch_cnpjs(text: str, root: str) -> List[str]:
    """CNPJs (formatados) com essa raiz encontrados no texto, sem repetição."""
    if not text or not root:
        return []
    clean = re.sub(r"<[^>]+>", "", text)
    found = []
    for m in branch_regex(root).finditer(clean):
        raw = root.upper() + m.group(1).upper() + m.group(2)
        f = format_cnpj(raw)
        if f not in found:
            found.append(f)
    return found


# --- Menções só pela raiz -----------------------------------------------------
# Órgãos como a ANVISA (Resoluções-RE) publicam apenas a raiz do CNPJ
# ("Empresa X / 24.684.423"). A raiz pontuada é específica o bastante para
# identificar a empresa; exige-se o formato com pontos para não casar com
# números quaisquer de 8 dígitos.

def _root_dotted(root: str) -> str:
    r = [re.escape(c) for c in root.upper()]
    return rf"{''.join(r[0:2])}\.{''.join(r[2:5])}\.{''.join(r[5:8])}"


def root_only_regex(root: str) -> "re.Pattern":
    """Raiz pontuada isolada: não seguida de /estabelecimento nem de ",dd"
    (valor monetário como R$ 24.684.423,00)."""
    return re.compile(
        rf"(?<![0-9A-Za-z.]){_root_dotted(root)}(?![0-9A-Za-z]|\s*/\s*[0-9A-Za-z]|,\d)",
        re.IGNORECASE,
    )


def company_regex(root: str) -> "re.Pattern":
    """CNPJ completo de qualquer estabelecimento OU raiz pontuada isolada."""
    return re.compile(
        rf"(?:{branch_regex(root).pattern})|(?:{root_only_regex(root).pattern})",
        re.IGNORECASE,
    )


def company_sql_pattern(root: str) -> str:
    """Padrão POSIX (PostgreSQL ~*) equivalente a `company_regex`."""
    return (
        rf"({branch_sql_pattern(root)}"
        rf"|(^|[^0-9A-Za-z.]){_root_dotted(root)}([^0-9A-Za-z/,]|,[^0-9]|$))"
    )


_HIGHLIGHT_RE = re.compile(
    r"<span[^>]*class=['\"]highlight['\"][^>]*>(.*?)</span>", re.IGNORECASE | re.DOTALL
)


def find_company_mentions(text: str, root: str) -> List[str]:
    """CNPJs completos da raiz encontrados no texto; se não houver, a raiz
    pontuada ("XX.XXX.XXX") quando aparece isolada ou destacada pela própria
    busca do DOU (o trecho da API pode vir truncado logo após a raiz)."""
    found = find_branch_cnpjs(text, root)
    if found:
        return found
    if not text or not root:
        return []
    clean = re.sub(r"<[^>]+>", "", text)
    if root_only_regex(root).search(clean):
        return [format_root(root)]
    target = format_root(root)
    for inner in _HIGHLIGHT_RE.findall(text):
        if re.sub(r"<[^>]+>|\s", "", inner) == target:
            return [target]
    return []
