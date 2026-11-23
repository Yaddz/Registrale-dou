"""Testes da identificação de empresas pela raiz do CNPJ (matriz e filiais)."""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from utils.cnpj import (  # noqa: E402
    branch_regex,
    branch_sql_pattern,
    cnpj_root,
    find_branch_cnpjs,
    format_root,
    normalize_cnpj,
)


@pytest.mark.parametrize(
    "term,expected",
    [
        ("24684423000136", "24684423"),
        ("24.684.423/0001-36", "24684423"),
        ('"24.684.423/0001-36"', "24684423"),
        ("12ABC34501DE35", "12ABC345"),
        ("ANVISA", None),
        ("123", None),
        ("ADMINISTRATIVO", None),
        (None, None),
    ],
)
def test_cnpj_root(term, expected):
    assert cnpj_root(term) == expected


def test_normalize_and_format_root():
    assert normalize_cnpj("24.684.423/0001-36") == "24684423000136"
    assert format_root("24684423") == "24.684.423"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("CNPJ: 24.684.423/0001-36", ["24.684.423/0001-36"]),
        ("CNPJ: 24.684.423/0002-17 (filial)", ["24.684.423/0002-17"]),
        ("CNPJ 24684423000136", ["24.684.423/0001-36"]),
        ("CNPJ: <span class='highlight'>24.684.423</span>/0002-17", ["24.684.423/0002-17"]),
        ("matriz 24.684.423/0001-36 e filial 24.684.423/0002-17",
         ["24.684.423/0001-36", "24.684.423/0002-17"]),
        ("outra empresa 124.684.423/0001-36", []),
        ("só a raiz 24.684.423 sem estabelecimento", []),
        ("processo 24684423000136999", []),
    ],
)
def test_find_branch_cnpjs(text, expected):
    assert find_branch_cnpjs(text, "24684423") == expected


def test_sql_pattern_matches_same_as_python_for_formatted_cnpj():
    pattern = branch_sql_pattern("24684423")
    assert re.search(pattern, "x 24.684.423/0002-17 y", re.IGNORECASE)
    assert re.search(pattern, "24684423000136", re.IGNORECASE)
    assert branch_regex("24684423").search("24.684.423/0002-17")


@pytest.mark.parametrize(
    "text,expected",
    [
        # ANVISA publica só a raiz
        ("Surgitec Ltda / <span class='highlight' style='background:#FFA;'>24.684.423</span>, a sua",
         ["24.684.423"]),
        ("Empresa / 24.684.423, registro", ["24.684.423"]),
        # trecho da API truncado logo após a raiz destacada
        ("CNPJ/MF n.º <span class='highlight' style='background:#FFA;'>24.684.423</span>0, de 20",
         ["24.684.423"]),
        # CNPJ completo continua tendo prioridade
        ("CNPJ 24.684.423/0002-17", ["24.684.423/0002-17"]),
        # não casa raiz sem pontos nem número maior
        ("protocolo 24684423 registrado", []),
        ("valor 124.684.423,00", []),
        ("no valor de R$ 24.684.423,00 (vinte", []),
    ],
)
def test_find_company_mentions(text, expected):
    from utils.cnpj import find_company_mentions
    assert find_company_mentions(text, "24684423") == expected


def test_company_sql_pattern_root_only():
    from utils.cnpj import company_sql_pattern
    p = company_sql_pattern("24684423")
    assert re.search(p, "Ltda / 24.684.423, a sua", re.I)
    assert re.search(p, "CNPJ 24.684.423/0002-17", re.I)
    assert not re.search(p, "valor 124.684.423,00", re.I)
    assert not re.search(p, "protocolo 24684423 x", re.I)
    assert not re.search(p, "R$ 24.684.423,00", re.I)
    assert re.search(p, "Ltda / 24.684.423", re.I)
