"""Avisos da Visão geral: só problemas reais, nunca integração desligada.

Substitui o antigo aviso permanente "Integrações pendentes". Um aviso aparece
quando algo que o usuário ligou deixou de funcionar:

- configuração ligada mas incompleta (SMTP sem servidor, rotina principal sem
  e-mail com o SMTP ligado, Google Sheets/GestãoClick com sincronização
  automática ligada e sem credenciais);
- erro recente de integração no histórico (últimas 24 h).

Cada aviso tem uma ``key`` estável: a Visão geral guarda as chaves
dispensadas e o aviso só volta quando surge uma chave nova (outro problema ou
um erro mais recente).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

BRASILIA_TZ = timezone(timedelta(hours=-3))
HISTORY_WINDOW = timedelta(hours=24)
HISTORY_DATE_FORMAT = "%d/%m/%Y %H:%M:%S"

# Evento do histórico → (id do aviso, título, aba de Configurações, âncora)
HISTORY_ERROR_EVENTS: dict[str, tuple[str, str, str, str]] = {
    "Erro Envio E-mail": ("email_send_error", "Falha recente no envio de e-mail", "integrations", "smtp-settings-card"),
    "SMTP ligado sem servidor configurado": ("smtp_not_ready_event", "E-mails não enviados: SMTP sem servidor", "integrations", "smtp-settings-card"),
    "Erro (Busca Mensal)": ("monthly_search_error", "Falha recente na busca mensal", "logs", ""),
    "Erro Sync GestãoClick": ("gestaoclick_sync_error", "Falha recente na sincronização do GestãoClick", "integrations", "gestaoclick-settings-card"),
    "Erro Sync Google Sheets": ("sheets_sync_error", "Falha recente na sincronização do Google Sheets", "google_sheets", ""),
    "Erro Agendamento": ("scheduler_error", "Falha recente no agendamento das buscas", "logs", ""),
}


EMAIL_ALERT_IDS = frozenset({"email_send_error", "smtp_not_ready_event"})


@dataclass(frozen=True)
class HealthAlert:
    """Um problema real, com destino direto na aba de Configurações."""

    id: str
    key: str
    title: str
    message: str
    settings_tab: str
    anchor: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class HistoryRow:
    data: str
    evento: str
    detalhes: str


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parse_history_date(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value, HISTORY_DATE_FORMAT).replace(tzinfo=BRASILIA_TZ)
    except (TypeError, ValueError):
        return None


def config_alerts(settings: Mapping[str, Any], main_dag: Mapping[str, Any]) -> list[HealthAlert]:
    """Problemas de configuração. Integração desligada nunca gera aviso."""
    alerts: list[HealthAlert] = []
    smtp = settings.get("smtp") or {}
    smtp_on = bool(smtp.get("enabled", False))

    if smtp_on and not _text(smtp.get("server")):
        alerts.append(HealthAlert(
            id="smtp_no_server", key="smtp_no_server",
            title="Envio de e-mail ligado sem servidor SMTP",
            message="Informe o servidor SMTP ou desligue o envio de e-mail.",
            settings_tab="integrations", anchor="smtp-settings-card",
        ))

    main_active = bool(main_dag.get("active", True))
    main_emails = [e for e in (main_dag.get("emails") or []) if _text(e)]
    if smtp_on and main_active and not main_emails:
        alerts.append(HealthAlert(
            id="main_dag_no_emails", key="main_dag_no_emails",
            title="Rotina principal sem e-mail de destino",
            message="O envio de e-mail está ligado, mas a rotina principal não tem destinatários.",
            settings_tab="routines", anchor="",
        ))

    sheets = settings.get("google_sheets") or {}
    if bool(sheets.get("auto_sync", False)):
        has_creds = bool(_text(sheets.get("credentials_json")))
        has_sheet = bool(_text(sheets.get("spreadsheet_url") or sheets.get("spreadsheet_id") or sheets.get("sheet_url")))
        if not (has_creds and has_sheet):
            alerts.append(HealthAlert(
                id="sheets_missing_credentials", key="sheets_missing_credentials",
                title="Google Sheets sem credenciais ou planilha",
                message="A sincronização automática está ligada, mas faltam as credenciais ou o endereço da planilha.",
                settings_tab="google_sheets", anchor="",
            ))

    api_keys = settings.get("api_keys") or {}
    if bool(api_keys.get("gestaoclick_auto_sync", False)):
        if not (_text(api_keys.get("gestaoclick_access_token")) and _text(api_keys.get("gestaoclick_secret_token"))):
            alerts.append(HealthAlert(
                id="gestaoclick_missing_tokens", key="gestaoclick_missing_tokens",
                title="GestãoClick sem tokens de acesso",
                message="A sincronização automática está ligada, mas faltam os tokens da API.",
                settings_tab="integrations", anchor="gestaoclick-settings-card",
            ))
    return alerts


def history_alerts(rows: Iterable[HistoryRow], now: datetime) -> list[HealthAlert]:
    """Um aviso por tipo de erro registrado nas últimas 24 h (o mais recente)."""
    latest: dict[str, tuple[datetime, HistoryRow]] = {}
    for row in rows:
        if row.evento not in HISTORY_ERROR_EVENTS:
            continue
        when = _parse_history_date(row.data)
        if when is None or now - when > HISTORY_WINDOW or when - now > timedelta(minutes=5):
            continue
        current = latest.get(row.evento)
        if current is None or when > current[0]:
            latest[row.evento] = (when, row)

    alerts: list[HealthAlert] = []
    for evento, (_, row) in sorted(latest.items(), key=lambda item: item[1][0], reverse=True):
        alert_id, title, tab, anchor = HISTORY_ERROR_EVENTS[evento]
        detail = _text(row.detalhes)
        if len(detail) > 180:
            detail = detail[:177].rstrip() + "…"
        alerts.append(HealthAlert(
            id=alert_id, key=f"{alert_id}@{row.data}", title=title,
            message=f"{row.data}: {detail}" if detail else row.data,
            settings_tab=tab, anchor=anchor,
        ))
    return alerts


def compute_health_alerts(
    settings: Mapping[str, Any],
    main_dag: Mapping[str, Any],
    history: Sequence[HistoryRow],
    now: Optional[datetime] = None,
) -> list[HealthAlert]:
    """Junta os avisos de configuração e os erros recentes do histórico."""
    current = now or datetime.now(BRASILIA_TZ)
    alerts = config_alerts(settings, main_dag)
    config_ids = {a.id for a in alerts}
    smtp_on = bool((settings.get("smtp") or {}).get("enabled", False))
    for alert in history_alerts(history, current):
        # Com o envio desligado, falhas de e-mail antigas deixaram de ser um problema.
        if alert.id in EMAIL_ALERT_IDS and not smtp_on:
            continue
        # "SMTP sem servidor" já aparece como problema de configuração.
        if alert.id == "smtp_not_ready_event" and "smtp_no_server" in config_ids:
            continue
        alerts.append(alert)
    return alerts
