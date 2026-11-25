"""Expansão de siglas de órgãos para o nome oficial usado pelo DOU.

O núcleo (`src/searchers.py::DOUSearcher._match_department`) só mantém um
resultado quando o texto do filtro é **igual a um elemento** de
`hierarchyList` da publicação (ex.: "Agência Nacional de Vigilância
Sanitária"). Uma sigla como "ANVISA" nunca casa, e o filtro descartaria tudo.
Este módulo converte as siglas comuns antes de gravar `department` no YAML.

Grafias conferidas na API do DOU (`in.gov.br/consulta/-/buscar/dou`) em
24/11/2026: ANVISA, Ministério da Saúde, INPI, ANP, ANEEL, ANS, ANTT, IBAMA,
CADE, Receita Federal e Ministério da Agricultura e Pecuária.
"""

from __future__ import annotations

from typing import Iterable, Optional

ORGAN_ALIASES: dict[str, str] = {
    "ANVISA": "Agência Nacional de Vigilância Sanitária",
    "MS": "Ministério da Saúde",
    "INPI": "Instituto Nacional da Propriedade Industrial",
    "MAPA": "Ministério da Agricultura e Pecuária",
    "INMETRO": "Instituto Nacional de Metrologia, Qualidade e Tecnologia",
    "ANP": "Agência Nacional do Petróleo, Gás Natural e Biocombustíveis",
    "ANATEL": "Agência Nacional de Telecomunicações",
    "ANS": "Agência Nacional de Saúde Suplementar",
    "ANEEL": "Agência Nacional de Energia Elétrica",
    "ANTT": "Agência Nacional de Transportes Terrestres",
    "ANTAQ": "Agência Nacional de Transportes Aquaviários",
    "ANAC": "Agência Nacional de Aviação Civil",
    "ANM": "Agência Nacional de Mineração",
    "IBAMA": "Instituto Brasileiro do Meio Ambiente e dos Recursos Naturais Renováveis",
    "CADE": "Conselho Administrativo de Defesa Econômica",
    "RFB": "Secretaria Especial da Receita Federal do Brasil",
    "RECEITA": "Secretaria Especial da Receita Federal do Brasil",
    "RECEITA FEDERAL": "Secretaria Especial da Receita Federal do Brasil",
}


def expand_organ_filter(organ: str) -> str:
    """Retorna o nome oficial de uma sigla conhecida, ou o texto aparado."""
    cleaned = organ.strip()
    return ORGAN_ALIASES.get(cleaned.upper(), cleaned)


def expand_organ_filters(orgs: Optional[Iterable[object]]) -> list[str]:
    """Normaliza a lista de filtros de órgão para o formato do `hierarchyList`.

    Remove vazios, expande siglas (sem diferenciar maiúsculas) e elimina
    duplicatas preservando a ordem.
    """
    if not orgs:
        return []
    if isinstance(orgs, str):
        orgs = [orgs]

    expanded: list[str] = []
    for organ in orgs:
        if organ is None:
            continue
        name = expand_organ_filter(str(organ))
        if not name or name in expanded:
            continue
        expanded.append(name)
    return expanded
