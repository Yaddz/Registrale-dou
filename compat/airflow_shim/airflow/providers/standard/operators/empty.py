"""Stub de ``EmptyOperator`` — não utilizado no modo local."""

from __future__ import annotations

from typing import Any


class EmptyOperator:
    """Stub de ``airflow.providers.standard.operators.empty.EmptyOperator``."""

    def __init__(self, *args: Any, **kwargs: Any):
        raise NotImplementedError(
            "EmptyOperator não é suportado no modo local do Registrale-DOU."
        )
