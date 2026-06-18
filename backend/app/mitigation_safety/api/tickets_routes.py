"""Per-ticket mitigation routes (5 of the 6 endpoints).

Status code matrix:
  POST   /tickets/{id}/mitigate/stage      201 / 409 / 423
  GET    /tickets/{id}/mitigate/validation 200 / 404
  POST   /tickets/{id}/mitigate/promote    200 / 409 / 423
  POST   /tickets/{id}/mitigate/revert     200 (idempotent)

All writes go through `require_human(scopes=...)` — the actor_id is always
"human:<id>" so the audit log can prove a human took the action.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.mitigation_safety.api.container import Services, services
from app.mitigation_safety.api.deps import HumanActor, get_db, require_human
from app.mitigation_safety.api.schemas import (
    CheckResultOut,
    PromoteRequest,
    PromoteResponse,
    RevertRequest,
    RevertResponse,
    StageRequest,
    StageResponse,
    ValidationOut,
)
from app.mitigation_safety.db.models import BotActionLog
from app.mitigation_safety.domain.errors import (
    ConfirmRequired,
    IllegalTransition,
    NotEligible,
    RevertHandleMissing,
    SafeModeHeld,
    ScopeIsolationViolation,
    ValidationNotPassed,
)


router = APIRouter(tags=["mitigation_safety"])


def _svc(db: Session = Depends(get_db)) -> Services:
    return services(db)


@router.post(
    "/tickets/{ticket_id}/mitigate/stage",
    response_model=StageResponse,
    status_code=201,
)
def stage(
    ticket_id: uuid.UUID,
    body: StageRequest,
    actor: HumanActor = Depends(require_human(scopes=["mitigation:write"])),
    svc: Services = Depends(_svc),
    db: Session = Depends(get_db),
):
    try:
        # MS-04: branch name auto-generated if not supplied.
        target = body.target or _default_target(body.action_id, ticket_id, body.type)
        result = svc.staging.stage(
            action_id=body.action_id,
            type=body.type,
            target=target,
            artifacts_ref=body.artifacts_ref,
            expected_outcome=body.expected_outcome,
            revert_handle_ref=body.revert_handle_ref,
            actor=actor.actor_id,
        )
        db.commit()
    except RevertHandleMissing as exc:
        db.rollback()
        raise HTTPException(409, detail={"error": "revert_handle_missing", "msg": str(exc)})
    except NotEligible as exc:
        db.rollback()
        raise HTTPException(409, detail={"error": "not_eligible", "msg": str(exc)})
    except ScopeIsolationViolation as exc:
        db.rollback()
        raise HTTPException(409, detail={"error": "scope_isolation", "msg": str(exc)})
    except IllegalTransition as exc:
        db.rollback()
        raise HTTPException(409, detail={"error": "illegal_transition", "msg": str(exc)})
    except SafeModeHeld as exc:
        db.rollback()
        raise HTTPException(423, detail={"error": "safe_mode_held", "msg": str(exc)})
    return StageResponse(
        deployment_id=result.deployment_id,
        validation_id=result.validation_id,
        window_start=result.window_start,
        window_end=result.window_end,
        status="PENDING",
    )


@router.get(
    "/tickets/{ticket_id}/mitigate/validation",
    response_model=ValidationOut,
)
def get_validation(
    ticket_id: uuid.UUID,
    actor: HumanActor = Depends(require_human(scopes=["mitigation:read"])),
    db: Session = Depends(get_db),
    svc: Services = Depends(_svc),
):
    action = (
        db.query(BotActionLog)
        .filter(BotActionLog.ticket_id == ticket_id)
        .order_by(BotActionLog.created_at.desc())
        .first()
    )
    if action is None or action.validation_id is None:
        raise HTTPException(404, detail="no validation for ticket")
    vr = svc.validation.get(action.validation_id)
    return ValidationOut(
        validation_id=vr.validation_id,
        overall_status=vr.overall_status,
        checks=[
            CheckResultOut(
                name=c.get("name"),
                status=c.get("status"),
                detail=c.get("detail"),
                evaluated_at=c.get("evaluated_at"),
            )
            for c in (vr.checks or [])
        ],
        elapsed_seconds=svc.validation.elapsed(vr),
        time_remaining_seconds=svc.validation.time_remaining(vr),
        window_start=vr.window_start,
        window_end=vr.window_end,
    )


@router.post(
    "/tickets/{ticket_id}/mitigate/promote",
    response_model=PromoteResponse,
)
def promote(
    ticket_id: uuid.UUID,
    body: PromoteRequest,
    actor: HumanActor = Depends(require_human(scopes=["mitigation:promote"])),
    svc: Services = Depends(_svc),
    db: Session = Depends(get_db),
):
    try:
        result = svc.promotion.promote(
            action_id=body.action_id,
            confirm=body.confirm,
            actor=actor.actor_id,
        )
        db.commit()
    except ValidationNotPassed as exc:
        db.rollback()
        raise HTTPException(
            409,
            detail={"error": "validation_not_passed", "msg": str(exc)},
        )
    except (ConfirmRequired, SafeModeHeld) as exc:
        db.rollback()
        raise HTTPException(
            423,
            detail={"error": "confirm_required", "msg": str(exc)},
        )
    except IllegalTransition as exc:
        db.rollback()
        raise HTTPException(409, detail={"error": "illegal_transition", "msg": str(exc)})
    return PromoteResponse(
        action_id=result.action_id,
        state="PROMOTED",
        rollback_window_end=result.rollback_window_end,
    )


@router.post(
    "/tickets/{ticket_id}/mitigate/revert",
    response_model=RevertResponse,
)
def revert(
    ticket_id: uuid.UUID,
    body: RevertRequest,
    actor: HumanActor = Depends(require_human(scopes=["mitigation:revert"])),
    svc: Services = Depends(_svc),
    db: Session = Depends(get_db),
):
    try:
        result = svc.revert.revert(
            action_id=body.action_id,
            reason=body.reason,
            actor=actor.actor_id,
        )
        db.commit()
    except IllegalTransition as exc:
        db.rollback()
        raise HTTPException(409, detail={"error": "illegal_transition", "msg": str(exc)})
    return RevertResponse(
        action_id=result.action_id,
        state=result.state,
        idempotent=result.idempotent,
    )


def _default_target(action_id: uuid.UUID, ticket_id: uuid.UUID, type_: str) -> str:
    if type_ == "code":
        from app.mitigation_safety.staging.runners.code_runner import branch_name
        return branch_name(ticket_id=str(ticket_id), action_id=str(action_id))
    return f"staging-{str(action_id).replace('-', '')[:12]}"
