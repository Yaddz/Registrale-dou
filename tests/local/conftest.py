"""Configuração comum das suítes do modo local."""

import pytest


@pytest.fixture(autouse=True)
def _isolate_local_dirs(tmp_path, monkeypatch):
    """Impede que testes de `tests/local/` gravem em `%LOCALAPPDATA%\\Registrale`."""
    data_dir = tmp_path / "registrale_data"
    logs_dir = tmp_path / "registrale_logs"
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("REGISTRALE_LOGS_DIR", str(logs_dir))


@pytest.fixture(autouse=True)
def _offline_inlabs_fallback(monkeypatch):
    """Sem INLABS, os testes offline usam a API do DOU (que eles simulam).

    A fonte de PDF integral baixaria arquivos reais; ``test_pdf_search.py``
    liga o modo ``pdf`` explicitamente com dados falsos.
    """
    monkeypatch.setenv("REGISTRALE_INLABS_FALLBACK", "api")
