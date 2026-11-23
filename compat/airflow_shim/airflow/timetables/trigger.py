"""Stub de ``CronTriggerTimetable`` — não utilizado no modo local."""

from __future__ import annotations

from typing import Any


class CronTriggerTimetable:
    """Stub de ``airflow.timetables.trigger.CronTriggerTimetable``."""

    def __init__(self, *args: Any, **kwargs: Any):
        raise NotImplementedError(
            "CronTriggerTimetable não é suportado no modo local do Registrale-DOU; "
            "o agendamento usa APScheduler."
        )
