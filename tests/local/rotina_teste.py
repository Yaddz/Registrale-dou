"""Rotina de teste de 16 empresas, gerada em tempo de execução.

Usa só os CNPJs que tiveram menção em novembro/2026 (``nov2026_mentions.json``,
já públicos no DOU) e os parâmetros da baseline (todos os órgãos, busca não
exata, campo TUDO, Seções 1/2/3 + Edição Extra). Nenhuma lista de clientes é
versionada: o YAML existe só em memória ou em pasta temporária.

Esperado de 03 a 23/11/2026: 26 menções, 16 empresas.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "baseline" / "nov2026_mentions.json"
SECTIONS = ["SECAO_1", "SECAO_2", "SECAO_3", "EDICAO_EXTRA"]
LAST_DAY = "2026-11-23"


def load_expected_mentions() -> List[Dict[str, Any]]:
    with open(FIXTURE, "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_terms() -> List[str]:
    """CNPJs (sem pontuação) das 16 empresas da baseline."""
    return sorted({m["cnpj_norm"] for m in load_expected_mentions()})


test_terms.__test__ = False  # não é um teste do pytest


def build_test_routine(sources: List[str], routine_id: str = "rotina_teste_16") -> Dict[str, Any]:
    """Rotina de teste (dict para ``LocalExecutor.trigger``) com os parâmetros da baseline."""
    return {
        "dag": {
            "id": routine_id,
            "description": "Rotina de teste (16 empresas com menção em novembro/2026)",
            "schedule": None,
            "tags": ["temp", "teste"],
            "search": [
                {
                    "header": "ROTINA DE TESTE",
                    "is_exact_search": False,
                    "force_rematch": True,
                    "department": [],
                    "dou_sections": list(SECTIONS),
                    "field": "TUDO",
                    "full_text": False,
                    "date": "DIA",
                    "terms": test_terms(),
                    "sources": list(sources),
                }
            ],
            "report": {"title": "Rotina de teste", "emails": [], "subject": "Teste"},
        }
    }


build_test_routine.__test__ = False
