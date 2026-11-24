"""Stubs de ``PythonOperator`` e ``BranchPythonOperator`` — não utilizados no modo local."""

from __future__ import annotations

from typing import Any


class PythonOperator:
    """Stub de ``airflow.providers.standard.operators.python.PythonOperator``."""

    def __init__(self, *args: Any, **kwargs: Any):
        raise NotImplementedError(
            "PythonOperator não é suportado no modo local do Registrale-DOU."
        )


class BranchPythonOperator:
    """Stub de ``airflow.providers.standard.operators.python.BranchPythonOperator``."""

    def __init__(self, *args: Any, **kwargs: Any):
        raise NotImplementedError(
            "BranchPythonOperator não é suportado no modo local do Registrale-DOU."
        )
