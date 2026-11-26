"""Siglas de órgãos (ANVISA, INPI…) viram o nome oficial do `hierarchyList` do DOU."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

import pytest
import yaml
from flask import Flask

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from rodou_dashboard.app import create_app
from rodou_dashboard.app.models import Company, Settings, db
from rodou_dashboard.app.services import dag_config_service
from rodou_dashboard.app.services.organ_aliases import expand_organ_filters

ANVISA = "Agência Nacional de Vigilância Sanitária"


@pytest.fixture
def app_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Flask]:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("REGISTRALE_DB_PATH", str(data_dir / "database.db"))
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("REGISTRALE_DISABLE_SCHEDULER", "1")
    monkeypatch.delenv("INLABS_DB_URL", raising=False)
    monkeypatch.delenv("REGISTRALE_ROUTINES_DIR", raising=False)
    monkeypatch.delenv("DAG_CONFS_DIR", raising=False)
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        yield app


def test_expand_acronym_returns_official_name() -> None:
    assert expand_organ_filters(["ANVISA"]) == [ANVISA]
    assert expand_organ_filters(["INPI"]) == ["Instituto Nacional da Propriedade Industrial"]
    assert expand_organ_filters(["MS"]) == ["Ministério da Saúde"]


def test_expand_acronym_is_case_insensitive_and_trims() -> None:
    assert expand_organ_filters(["  anvisa ", "Inpi"]) == [
        ANVISA,
        "Instituto Nacional da Propriedade Industrial",
    ]


def test_expand_unknown_name_is_preserved() -> None:
    assert expand_organ_filters(["Ministério da Fazenda"]) == ["Ministério da Fazenda"]


def test_expand_removes_empty_values() -> None:
    assert expand_organ_filters(["", "   ", None, "ANVISA"]) == [ANVISA]
    assert expand_organ_filters(None) == []
    assert expand_organ_filters([]) == []


def test_expand_removes_duplicates_preserving_order() -> None:
    assert expand_organ_filters(["ANVISA", "Ministério da Saúde", ANVISA, "ms"]) == [
        ANVISA,
        "Ministério da Saúde",
    ]


def test_expand_accepts_single_string() -> None:
    assert expand_organ_filters("ANVISA") == [ANVISA]


def test_rebuild_yaml_writes_expanded_department_and_keeps_raw_setting(app_ctx: Flask) -> None:
    db.session.add(Company(nome="Empresa A", cnpj="24.684.423/0001-00", cnpj_norm="24684423000100", origem="Manual", status=True))
    setting = Settings(key="main_dag_settings")
    setting.set_value({"organs": ["ANVISA"], "department": ["ANVISA"], "sections": ["SECAO_1"]})
    db.session.add(setting)
    db.session.commit()

    dag_config_service.rebuild_yaml_from_db()

    data = yaml.safe_load(Path(dag_config_service.get_base_yaml_path()).read_text(encoding="utf-8"))
    for block in data["dag"]["search"]:
        assert block["department"] == [ANVISA]
        assert block["dou_sections"] == ["SECAO_1"]
    stored = Settings.query.filter_by(key="main_dag_settings").first().get_value()
    assert stored["organs"] == ["ANVISA"]


def test_rebuild_yaml_clears_previous_organ_filter_when_setting_is_empty(app_ctx: Flask) -> None:
    db.session.add(Company(nome="Empresa A", cnpj="24.684.423/0001-00", cnpj_norm="24684423000100", origem="Manual", status=True))
    setting = Settings(key="main_dag_settings")
    setting.set_value({"organs": ["ANVISA"], "department": ["ANVISA"], "sections": ["SECAO_1"]})
    db.session.add(setting)
    db.session.commit()
    dag_config_service.rebuild_yaml_from_db()

    sections = ["SECAO_1", "SECAO_2", "SECAO_3", "EDICAO_EXTRA"]
    setting.set_value({"organs": [], "department": [], "sections": sections})
    db.session.commit()
    dag_config_service.rebuild_yaml_from_db()

    data = yaml.safe_load(Path(dag_config_service.get_base_yaml_path()).read_text(encoding="utf-8"))
    for block in data["dag"]["search"]:
        assert block["department"] == []
        assert "organs" not in block
        assert block["dou_sections"] == sections


def test_runner_load_specs_expands_organ_acronyms_in_memory(tmp_path: Path) -> None:
    from rodou_dashboard.app.runtime.runner import load_specs

    custom_yaml = tmp_path / "rotina_anvisa.yaml"
    original_text = (
        "dag:\n"
        "  id: rotina_anvisa\n"
        "  description: Rotina personalizada ANVISA\n"
        "  search:\n"
        "    - header: ANVISA\n"
        "      terms:\n"
        "        - '24.684.423'\n"
        "      department:\n"
        "        - ANVISA\n"
    )
    custom_yaml.write_text(original_text, encoding="utf-8")

    dag_cfg = load_specs(custom_yaml)
    assert dag_cfg.search[0].department == [ANVISA]
    assert custom_yaml.read_text(encoding="utf-8") == original_text
