"""Safe Mode routes (2 endpoints).

GET  /mitigation/safe-mode         -> system + categories snapshot
POST /mitigation/safe-mode         -> enter/exit (exit requires human; MS-22)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.mitigation_safety.api.container import Services, services
from app.mitigation_safety.api.deps import HumanActor, get_db, require_human
from app.mitigation_safety.api.schemas import (
    SafeModeEntryOut,
    SafeModeMutateRequest,
    SafeModeView,
)
from app.mitigation_safety.config import default_store
from app.mitigation_safety.domain.errors import SafeModeHumanRequired
from app.mitigation_safety.safemode.controller import (
    SYSTEM_SCOPE,
    category_scope,
)


router = APIRouter(tags=["mitigation_safety"])


def _svc(db: Session = Depends(get_db)) -> Services:
    return services(db)


@router.get("/mitigation/safe-mode", response_model=SafeModeView)
def get_safe_mode(
    actor: HumanActor = Depends(require_human(scopes=["mitigation:read"])),
    svc: Services = Depends(_svc),
):
    cfg = default_store().get()
    snap = svc.safe_mode.snapshot(cfg.categories)
    system_entry = snap[SYSTEM_SCOPE]
    cats = {
        k: SafeModeEntryOut(
            scope=v.scope,
            active=v.active,
            entered_at=v.entered_at,
            entered_by=v.entered_by,
            exited_at=v.exited_at,
            exited_by=v.exited_by,
            reason=v.reason,
        )
        for k, v in snap.items()
        if k != SYSTEM_SCOPE
    }
    return SafeModeView(
        system=SafeModeEntryOut(
            scope=system_entry.scope,
            active=system_entry.active,
            entered_at=system_entry.entered_at,
            entered_by=system_entry.entered_by,
            exited_at=system_entry.exited_at,
            exited_by=system_entry.exited_by,
            reason=system_entry.reason,
        ),
        categories=cats,
    )


@router.post("/mitigation/safe-mode", response_model=SafeModeEntryOut)
def mutate_safe_mode(
    body: SafeModeMutateRequest,
    actor: HumanActor = Depends(
        require_human(scopes=["mitigation:safemode"])
    ),
    svc: Services = Depends(_svc),
    db: Session = Depends(get_db),
):
    # #27: only accept the system scope or a configured category scope.
    # An arbitrary scope string would otherwise create an orphan row that
    # the snapshot view never surfaces.
    cfg = default_store().get()
    allowed = {SYSTEM_SCOPE} | {category_scope(c) for c in cfg.categories}
    if body.scope not in allowed:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unknown_scope",
                "msg": f"scope must be one of {sorted(allowed)}",
            },
        )
    # MS-22: enforce the human-only exit at the route boundary too. The
    # controller raises SafeModeHumanRequired internally; this short-circuit
    # also rejects any "guard:" forgery via the body.
    try:
        if body.active:
            entry = svc.safe_mode.enter(
                scope=body.scope,
                entered_by=actor.actor_id,
                reason=body.reason,
            )
        else:
            entry = svc.safe_mode.exit(
                scope=body.scope,
                exited_by=actor.actor_id,
                reason=body.reason,
            )
        db.commit()
    except SafeModeHumanRequired as exc:
        db.rollback()
        raise HTTPException(403, detail={"error": "human_required", "msg": str(exc)})
    return SafeModeEntryOut(
        scope=entry.scope,
        active=entry.active,
        entered_at=entry.entered_at,
        entered_by=entry.entered_by,
        exited_at=entry.exited_at,
        exited_by=entry.exited_by,
        reason=entry.reason,
    )


# `category_scope` is re-exported so the frontend can compose scope names
# without duplicating the prefix logic.
__all__ = ["router", "category_scope"]
