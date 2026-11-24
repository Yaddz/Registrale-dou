"""Teste de paridade live do Sprint 2: novembro/2026 no modo local vs baseline Docker."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import yaml

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = REPO_ROOT / "rodou_dashboard"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "baseline"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from app import create_app
from app.models import db
from app.routes.dags import extract_mentions_from_results
from app.runtime.executor import LocalExecutor
from app.services.email_service import build_mentions_email_html
from app.services.holiday_service import get_business_days_for_month


def _build_nov2026_dou_yaml() -> dict:
    with open(REPO_ROOT / "dag_confs" / "Pesquisa_cnpj.yaml", "r", encoding="utf-8") as f:
        base_yaml = yaml.safe_load(f) or {}

    original_searches = base_yaml.get("dag", {}).get("search", [])
    if not isinstance(original_searches, list):
        original_searches = [original_searches] if original_searches else []

    temp_search_blocks = []
    for block in original_searches:
        temp_block = {
            "header": block.get("header", "Busca API-DOU Pesquisa_cnpj.yaml"),
            "is_exact_search": block.get("is_exact_search", True),
            "force_rematch": True,
            "terms": block.get("terms", []),
            "dou_sections": block.get("dou_sections", ["SECAO_1", "SECAO_2", "SECAO_3", "EDICAO_EXTRA"]),
            "field": block.get("field", "TUDO"),
            "full_text": block.get("full_text", True),
            "date": "DIA",
            "sources": ["DOU"],
        }
        if block.get("department"):
            temp_block["department"] = block["department"]
        if block.get("organs"):
            temp_block["organs"] = block["organs"]
        if block.get("terms_ignore"):
            temp_block["terms_ignore"] = block["terms_ignore"]
        temp_search_blocks.append(temp_block)

    return {
        "dag": {
            "id": "parity_nov2026_local",
            "description": "Paridade novembro/2026 modo local",
            "schedule": None,
            "tags": ["temp", "api_dou", "parity"],
            "search": temp_search_blocks,
            "report": {
                "title": "Paridade Novembro/2026",
                "emails": [],
                "subject": "Registrale - Paridade Novembro/2026",
            },
        }
    }


@pytest.mark.live
def test_parity_nov2026_local_matches_baseline(tmp_path):
    with open(FIXTURES_DIR / "nov2026_mentions.json", "r", encoding="utf-8") as f:
        expected_mentions = json.load(f)

    expected_set = {
        (m["cnpj_norm"], m["data"], m["link"])
        for m in expected_mentions
    }
    expected_companies = {m["cnpj_norm"] for m in expected_mentions}
    assert len(expected_mentions) == 26
    assert len(expected_companies) == 16

    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'parity.db'}",
            "WTF_CSRF_ENABLED": False,
        }
    )
    with app.app_context():
        db.create_all()

    yaml_dict = _build_nov2026_dou_yaml()
    weekdays = [
        d for d in get_business_days_for_month(2026, 11, cap_today=False)
        if d <= "2026-11-23"
    ]
    assert len(weekdays) == 14

    executor = LocalExecutor(app=app, max_workers=2)
    try:
        with app.app_context():
            run_ids = []
            for d_str in weekdays:
                run_ids.append(executor.trigger(yaml_dict, date=d_str))

            finished, states = executor.wait(run_ids, timeout=max(3600, 300 * len(run_ids)))
            assert finished is True
            assert all(st == "success" for st in states.values()), states

            all_mentions = []
            seen_ids = set()
            for rid in run_ids:
                raw_items = executor.result(rid)
                results_raw = [
                    item.get("result", item)
                    for item in raw_items
                    if isinstance(item, dict)
                ]
                for m in extract_mentions_from_results(results_raw, cnpj_map={}):
                    if m["id"] not in seen_ids:
                        seen_ids.add(m["id"])
                        all_mentions.append(m)

            actual_set = {
                (m["cnpj_norm"], m["data"], m["link"])
                for m in all_mentions
            }
            actual_companies = {m["cnpj_norm"] for m in all_mentions}

            assert actual_set == expected_set, (
                f"Faltando: {expected_set - actual_set} | Extras: {actual_set - expected_set}"
            )
            assert len(all_mentions) == 26
            assert len(actual_companies) == 16

            # Verifica montagem do HTML de e-mail com as 26 menções
            html = build_mentions_email_html(
                all_mentions,
                template_name="Relatório Mensal Registrale",
                title="Relatório Consolidado de Menções (11/2026)",
                subtitle="Paridade novembro/2026",
            )
            assert "24.684.423" in html
            assert len(html) > 1000
    finally:
        executor.shutdown(wait=True)
