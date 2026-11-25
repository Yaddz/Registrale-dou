"""Acesso ao painel: login obrigatório ou abertura direta neste computador.

Com o login desligado, o painel entra direto como o usuário master, mas só para
pedidos feitos no próprio computador (127.0.0.1 / localhost). Pedidos que chegam
por outro endereço continuam pedindo usuário e senha, e pedidos de alteração
vindos de outros sites (cabeçalho Origin/Referer diferente) são recusados.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit

from ..models import Settings, User, db

AUTH_SETTINGS_KEY = "auth_settings"
AUTH_ONBOARDING_KEY = "auth_onboarding_done"

_LOOPBACK_ADDRS = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _get(key: str, default):
    rec = Settings.query.filter_by(key=key).first()
    if not rec:
        return default
    val = rec.get_value()
    return default if val is None else val


def _set(key: str, value) -> None:
    rec = Settings.query.filter_by(key=key).first()
    if not rec:
        rec = Settings(key=key)
        db.session.add(rec)
    rec.set_value(value)
    db.session.commit()


def is_login_required() -> bool:
    """Login exigido? Padrão: sim (instalações existentes não mudam)."""
    val = _get(AUTH_SETTINGS_KEY, {})
    if not isinstance(val, dict) or "require_login" not in val:
        return True
    return bool(val["require_login"])


def set_login_required(required: bool) -> None:
    val = _get(AUTH_SETTINGS_KEY, {})
    if not isinstance(val, dict):
        val = {}
    val["require_login"] = bool(required)
    _set(AUTH_SETTINGS_KEY, val)


def is_access_onboarding_done() -> bool:
    return bool(_get(AUTH_ONBOARDING_KEY, False))


def mark_access_onboarding_done() -> None:
    _set(AUTH_ONBOARDING_KEY, True)


def _hostname(value: str) -> str:
    """Extrai o nome do host de 'host:porta', '[::1]:porta' ou de uma URL."""
    if not value:
        return ""
    if "://" not in value:
        value = f"http://{value}"
    try:
        return (urlsplit(value).hostname or "").lower()
    except ValueError:
        return ""


def is_local_request(req) -> bool:
    """Pedido feito neste computador, pelo endereço local (bloqueia DNS rebinding)."""
    remote = (req.remote_addr or "").strip()
    if remote not in _LOOPBACK_ADDRS:
        return False
    return _hostname(req.host or "") in _LOOPBACK_HOSTS


def is_same_origin_write(req) -> bool:
    """Alterações (POST/PUT/DELETE…) só quando a origem é o próprio painel."""
    if req.method in _SAFE_METHODS:
        return True
    origin = req.headers.get("Origin")
    if origin is not None:
        if origin == "null":
            return False
        return urlsplit(origin).netloc.lower() == (req.host or "").lower()
    referer = req.headers.get("Referer")
    if referer:
        return urlsplit(referer).netloc.lower() == (req.host or "").lower()
    return True


def get_auto_login_user() -> Optional[dict]:
    """Usuário usado quando o login está desligado: `admin` ou o primeiro master."""
    user = User.query.filter_by(username="admin", role="master").first()
    if not user:
        user = User.query.filter_by(role="master").order_by(User.id).first()
    if not user:
        return None
    return {"username": user.username, "role": user.role}


def try_auto_login(session, req) -> bool:
    """Preenche a sessão quando o login está desligado e o pedido é local."""
    if is_login_required() or not is_local_request(req):
        return False
    user = get_auto_login_user()
    if not user:
        return False
    session["user"] = user
    session["auto_login"] = True
    session.pop("expires_at", None)
    return True
