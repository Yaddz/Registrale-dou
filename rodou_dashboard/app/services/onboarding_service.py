"""Gerenciamento de estado do assistente de configuração inicial (Sprint 14)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import Company, Mention, Settings, db

ONBOARDING_TOTAL_STEPS = 9
ONBOARDING_SETTINGS_KEY = "onboarding_state"
VALID_COMPANY_SOURCES = {"google_sheets", "gestaoclick", "manual"}


def _clamp_step(step: Any, default: int = 1) -> int:
    try:
        val = int(step)
    except (TypeError, ValueError):
        return default
    return max(1, min(ONBOARDING_TOTAL_STEPS, val))


def _normalize_skipped(raw: Any) -> List[int]:
    if not isinstance(raw, list):
        return []
    out: List[int] = []
    for item in raw:
        try:
            s = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= s <= ONBOARDING_TOTAL_STEPS and s not in out:
            out.append(s)
    return sorted(out)


def get_onboarding_state() -> Dict[str, Any]:
    """Retorna o estado persistido do assistente de onboarding."""
    from .access_service import is_access_onboarding_done

    rec = Settings.query.filter_by(key=ONBOARDING_SETTINGS_KEY).first()
    if rec and isinstance(rec.get_value(), dict):
        raw = rec.get_value()
        completed = bool(raw.get("completed", False))
        current_step = _clamp_step(raw.get("current_step"), default=1)
        skipped = _normalize_skipped(raw.get("skipped_steps"))
        src = raw.get("company_source")
        company_source = src if src in VALID_COMPANY_SOURCES else None
        return {
            "reopened": bool(raw.get("reopened", False)) and not completed,
            "completed": completed,
            "current_step": current_step,
            "skipped_steps": skipped,
            "company_source": company_source,
            "should_open": not completed,
            "total_steps": ONBOARDING_TOTAL_STEPS,
        }

    # Compatibilidade com instalações anteriores ao Sprint 14:
    # se PDF e acesso já foram concluídos antes, não reabrir o assistente automaticamente.
    pdf_rec = Settings.query.filter_by(key="pdf_onboarding_done").first()
    pdf_done = bool(pdf_rec and pdf_rec.get_value())
    access_done = is_access_onboarding_done()

    if pdf_done and access_done:
        return {
            "reopened": False,
            "completed": True,
            "current_step": ONBOARDING_TOTAL_STEPS,
            "skipped_steps": [],
            "company_source": None,
            "should_open": False,
            "total_steps": ONBOARDING_TOTAL_STEPS,
        }

    initial_step = 3 if pdf_done else 1
    return {
        "reopened": False,
        "completed": False,
        "current_step": initial_step,
        "skipped_steps": [],
        "company_source": None,
        "should_open": True,
        "total_steps": ONBOARDING_TOTAL_STEPS,
    }


def _save_state(state: Dict[str, Any]) -> Dict[str, Any]:
    rec = Settings.query.filter_by(key=ONBOARDING_SETTINGS_KEY).first()
    if not rec:
        rec = Settings(key=ONBOARDING_SETTINGS_KEY)
        db.session.add(rec)
    payload = {
        "completed": bool(state.get("completed", False)),
        "reopened": bool(state.get("reopened", False)) and not bool(state.get("completed", False)),
        "current_step": _clamp_step(state.get("current_step"), default=1),
        "skipped_steps": _normalize_skipped(state.get("skipped_steps")),
        "company_source": state.get("company_source") if state.get("company_source") in VALID_COMPANY_SOURCES else None,
    }
    rec.set_value(payload)
    db.session.commit()
    return {
        **payload,
        "should_open": not payload["completed"],
        "total_steps": ONBOARDING_TOTAL_STEPS,
    }


def _get_or_create_global_settings() -> tuple[Settings, Dict[str, Any]]:
    rec = Settings.query.filter_by(key="global_settings").first()
    val = rec.get_value() if rec else {}
    if not isinstance(val, dict):
        val = {}
    if not rec:
        rec = Settings(key="global_settings")
        db.session.add(rec)
    return rec, dict(val)


def _is_step_integration_active(step: int) -> bool:
    """True quando a integração do passo já está configurada e ligada."""
    _, gs = _get_or_create_global_settings()
    if step == 2:
        return bool((gs.get("pdf_archive") or {}).get("enabled"))
    if step == 5:
        return bool((gs.get("google_sheets") or {}).get("auto_sync"))
    if step == 6:
        return bool((gs.get("api_keys") or {}).get("gestaoclick_auto_sync"))
    if step == 7:
        return bool((gs.get("smtp") or {}).get("enabled"))
    if step == 8:
        return bool((gs.get("inlabs") or {}).get("enabled"))
    return False


def _deactivate_step_integration(step: int) -> None:
    """Ao pular um passo, deixa a respectiva integração desativada (não pendente)."""
    if step == 2:
        from ..runtime.paths import get_default_pdf_dir
        from ..runtime.pdf_archiver import DEFAULT_LAYOUT, DEFAULT_SECTIONS

        rec, gs = _get_or_create_global_settings()
        pa = dict(gs.get("pdf_archive") or {})
        pa.setdefault("folder", str(get_default_pdf_dir(create=False)))
        pa.setdefault("layout", DEFAULT_LAYOUT)
        pa.setdefault("sections", list(DEFAULT_SECTIONS))
        pa["enabled"] = False
        gs["pdf_archive"] = pa
        rec.set_value(gs)

        done_rec = Settings.query.filter_by(key="pdf_onboarding_done").first()
        if not done_rec:
            done_rec = Settings(key="pdf_onboarding_done")
            db.session.add(done_rec)
        done_rec.set_value(True)
        db.session.commit()
        return

    if step == 3:
        from .access_service import mark_access_onboarding_done

        mark_access_onboarding_done()
        return

    if step == 5:
        rec, gs = _get_or_create_global_settings()
        sheets = dict(gs.get("google_sheets") or {})
        sheets["auto_sync"] = False
        gs["google_sheets"] = sheets
        rec.set_value(gs)
        db.session.commit()
        return

    if step == 6:
        rec, gs = _get_or_create_global_settings()
        ak = dict(gs.get("api_keys") or {})
        ak["gestaoclick_auto_sync"] = False
        gs["api_keys"] = ak
        rec.set_value(gs)
        db.session.commit()
        try:
            from ..runtime.scheduler import reload_scheduler_if_running

            reload_scheduler_if_running()
        except Exception:
            pass
        return

    if step == 7:
        rec, gs = _get_or_create_global_settings()
        smtp = dict(gs.get("smtp") or {})
        smtp["enabled"] = False
        gs["smtp"] = smtp
        rec.set_value(gs)
        db.session.commit()
        return

    if step == 8:
        rec, gs = _get_or_create_global_settings()
        if not gs.get("inlabs_fallback"):
            gs["inlabs_fallback"] = "pdf"
        inlabs = dict(gs.get("inlabs") or {})
        inlabs["enabled"] = False
        gs["inlabs"] = inlabs
        rec.set_value(gs)
        db.session.commit()
        return


def update_onboarding_state(
    action: str,
    step: Optional[int] = None,
    company_source: Optional[str] = None,
) -> Dict[str, Any]:
    """Atualiza e persiste o estado do assistente conforme a ação solicitada."""
    state = get_onboarding_state()
    act = str(action or "").strip().lower()

    if company_source in VALID_COMPANY_SOURCES:
        state["company_source"] = company_source

    if act == "reopen":
        state["completed"] = False
        state["reopened"] = True
        state["current_step"] = _clamp_step(step, default=1)
        return _save_state(state)

    if act == "complete":
        state["completed"] = True
        state["reopened"] = False
        state["current_step"] = ONBOARDING_TOTAL_STEPS
        return _save_state(state)

    if act == "goto":
        state["current_step"] = _clamp_step(step, default=state["current_step"])
        return _save_state(state)

    if act == "set_source":
        return _save_state(state)

    if act == "advance":
        target = _clamp_step(step, default=state["current_step"])
        skipped = [s for s in state["skipped_steps"] if s != target]
        state["skipped_steps"] = skipped
        if target >= ONBOARDING_TOTAL_STEPS:
            state["completed"] = True
            state["reopened"] = False
            state["current_step"] = ONBOARDING_TOTAL_STEPS
        else:
            state["current_step"] = target + 1
        return _save_state(state)

    if act == "skip":
        target = _clamp_step(step, default=state["current_step"])
        # Passo 4: pular mantém a rotina padrão semeada ativa (só avança).
        # Reabertura: não desliga integração que já estava configurada e ativa.
        keep = target == 4 or (state.get("reopened") and _is_step_integration_active(target))
        deactivated = False
        if not keep:
            _deactivate_step_integration(target)
            deactivated = True
            skipped = list(state["skipped_steps"])
            if target not in skipped:
                skipped.append(target)
            state["skipped_steps"] = sorted(skipped)
        if target >= ONBOARDING_TOTAL_STEPS:
            state["completed"] = True
            state["reopened"] = False
            state["current_step"] = ONBOARDING_TOTAL_STEPS
        else:
            state["current_step"] = target + 1
        saved = _save_state(state)
        saved["deactivated"] = deactivated
        return saved

    raise ValueError(f"Ação inválida para onboarding: {action!r}")
