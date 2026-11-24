"""Stub de ``SlackNotifier`` — não utilizado no modo local."""

from __future__ import annotations

from typing import Any


class SlackNotifier:
    """Stub de ``airflow.providers.slack.notifications.slack.SlackNotifier``."""

    def __init__(self, *args: Any, **kwargs: Any):
        raise NotImplementedError(
            "SlackNotifier não é suportado no modo local do Registrale-DOU."
        )
