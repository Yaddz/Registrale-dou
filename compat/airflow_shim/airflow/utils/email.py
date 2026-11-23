"""Stub de ``airflow.utils.email`` — não utilizado no modo local."""

from __future__ import annotations

from typing import Any


def send_email(*args: Any, **kwargs: Any) -> None:
    """Stub de ``airflow.utils.email.send_email``."""
    raise NotImplementedError(
        "airflow.utils.email.send_email não é usado no modo local do Registrale-DOU; "
        "o envio de e-mail é feito pelo email_service do painel."
    )
