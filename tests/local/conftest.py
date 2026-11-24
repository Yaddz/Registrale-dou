"""Configuração comum das suítes do modo local."""

import pytest


@pytest.fixture(autouse=True)
def _offline_inlabs_fallback(monkeypatch):
    """Sem INLABS, os testes offline usam a API do DOU (que eles simulam).

    A fonte de PDF integral baixaria arquivos reais; ``test_pdf_search.py``
    liga o modo ``pdf`` explicitamente com dados falsos.
    """
    monkeypatch.setenv("REGISTRALE_INLABS_FALLBACK", "api")
