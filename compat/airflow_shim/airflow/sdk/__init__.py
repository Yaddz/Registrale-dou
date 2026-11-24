"""Shim de ``airflow.sdk`` (``Variable`` e ``TaskGroup``)."""

from __future__ import annotations

import json
from typing import Any

from airflow._provider import resolve_variable

_UNSET = object()


class Variable:
    """Implementação local de ``airflow.sdk.Variable``."""

    @classmethod
    def get(
        cls,
        key: str,
        default: Any = _UNSET,
        deserialize_json: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Obtém variável do provedor local do Registrale."""
        found, value = resolve_variable(key)
        if found:
            if deserialize_json and isinstance(value, str):
                return json.loads(value)
            return value
        if default is not _UNSET:
            return default
        if "default_var" in kwargs:
            return kwargs["default_var"]
        raise KeyError(f"Variable '{key}' not found")


class TaskGroup:
    """Stub de ``airflow.sdk.TaskGroup`` — não utilizado no modo local."""

    def __init__(self, *args: Any, **kwargs: Any):
        raise NotImplementedError(
            "airflow.sdk.TaskGroup não é suportado no modo local do Registrale-DOU."
        )
