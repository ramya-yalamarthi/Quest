"""PromotionService — the single transition that produces a production effect.

Invariants enforced here (and only here):
- 1: production effect reachable only via Promote, only on PASS, only after
     Staged -> Validating.
- 2 / 10: never auto-promote on timeout (caller never invokes this on
     timeout; the worker only fires expiry).
- safe-mode hold: if Safe Mode is active for the action's category OR
     `confirm_to_promote[category]` is True, `confirm=true` is required
     from an authorized human (MS-21).
- 16: opens a rollback window via `BotActionLog.rollback_window_end`.

`apply_to_production` is the only call site that touches production. It is
deliberately small and resolves through the staging runner so the same
runbook owners control the production effect.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.mitigation_safety.audit.service import MitigationAuditLogger
from app.mitigation_safety.config import MitigationConfig
from app.mitigation_safety.db.models import (
    BotActionLog,
    StagingDeployment,
    ValidationResult,
)
from app.mitigation_safety.domain.errors import (
    IllegalTransition,
)
from app.mitigation_safety.domain.states import MitigationState
from app.mitigation_safety.domain.transitions import (
    assert_can_promote,
    assert_legal,
    record_transition,
)
from app.mitigation_safety.notifications.sink import Notification, NotificationSink
from app.mitigation_safety.safemode.controller import (
    SafeModeController,
    category_scope,
)

logger = logging.getLogger("mitigation_safety.staging.promotion")


@dataclass(frozen=True)
class PromotionResult:
    action_id: uuid.UUID
    state: str
    rollback_window_end: datetime


class PromotionService:
    def __init__(
        self,
        db: Session,
        audit: MitigationAuditLogger,
        *,
        cfg: MitigationConfig,
        safe_mode: SafeModeController,
        notifier: NotificationSink,
        apply_to_production,
    ) -> None:
        """
        apply_to_production: callable(action, deployment, validation) -> None
            The single production-write code path. Provided by the boot wiring
            so it can be a noop in tests; the real wiring closes the PR /
            promotes the config scope.
        """
        self.db = db
        self.audit = audit
        self.cfg = cfg
        self.safe_mode = safe_mode
        self.notifier = notifier
        self._apply = apply_to_production

    def promote(
        self,
        *,
        action_id: uuid.UUID,
        confirm: bool,
        actor: str,
    ) -> PromotionResult:
        # #10: lock the action row for the duration of the promotion. Two
        # concurrent promote() calls for the same action_id will queue.
        action = (
            self.db.query(BotActionLog)
            .filter(BotActionLog.action_id == action_id)
            .with_for_update(read=False)
            .one_or_none()
        )
        if action is None:
            raise IllegalTransition("(no-action)", "promote")
        if action.state != MitigationState.VALIDATING.value:
            raise IllegalTransition(action.state, MitigationState.PROMOTED.value)
        if action.validation_id is None:
            raise IllegalTransition("(no-validation)", "promote")
        vr = self.db.get(ValidationResult, action.validation_id)
        if vr is None:
            raise IllegalTransition("(no-validation)", "promote")

        confirm_required = self.cfg.confirm_required_for(action.category)
        safe_mode_active = self.safe_mode.is_held(action.category)

        # #40: pass the actual validation_id so the raised exception carries
        # enough identity for the API layer to log it.
        try:
            assert_can_promote(
                overall_status=vr.overall_status,
                safe_mode_active=safe_mode_active,
                confirm_to_promote=confirm_required,
                confirm=confirm,
            )
        except Exception as exc:
            # Attach validation_id to ValidationNotPassed if applicable.
            from app.mitigation_safety.domain.errors import ValidationNotPassed
            if isinstance(exc, ValidationNotPassed):
                exc.validation_id = vr.validation_id
            raise

        # #13: resolve the deployment via `vr.deployment_id` so we promote the
        # exact deployment whose validation passed — NOT just the newest
        # deployment for this action. (Old code re-staged would have leaked
        # the wrong row into production.)
        deployment = self.db.get(StagingDeployment, vr.deployment_id)
        if deployment is None:
            raise IllegalTransition("(no-deployment)", "promote")

        # === The single production-effect call site (invariant 1) ===========
        try:
            self._apply(action, deployment, vr)
        except Exception as exc:
            # MS-23: persist Safe Mode in an isolated session so it survives
            # the outer rollback this raise will trigger. See the same
            # pattern in staging/service.py (#8 / #23).
            from app.mitigation_safety.staging.service import (
                _persist_safe_mode_in_isolation,
            )
            _persist_safe_mode_in_isolation(category=action.category, exc=exc)
            raise

        # Validating -> Promoted
        assert_legal(action.state, MitigationState.PROMOTED.value)
        prev = action.state
        now = datetime.now(timezone.utc)
        rollback_end = now + timedelta(
            seconds=self.cfg.rollback_window_for(action.category)
        )
        action.state = MitigationState.PROMOTED.value
        action.rollback_window_end = rollback_end
        action.state_history = record_transition(
            action.state_history,
            frm=prev,
            to=action.state,
            actor=actor,
            detail=f"rollback_window_end={rollback_end.isoformat()}",
        )
        vr.promoted_at = now
        deployment.status = "PROMOTED"

        self.db.add(action)
        self.db.add(vr)
        self.db.add(deployment)
        self.db.flush()
        self.audit.record(
            action_id=action.action_id,
            ticket_id=action.ticket_id,
            actor=actor,
            transition_type="state",
            from_state=prev,
            to_state=action.state,
            detail={
                "validation_id": str(vr.validation_id),
                "rollback_window_end": rollback_end.isoformat(),
                "safe_mode_active": safe_mode_active,
                "confirm_required": confirm_required,
            },
        )
        return PromotionResult(
            action_id=action.action_id,
            state=action.state,
            rollback_window_end=rollback_end,
        )


def noop_apply_to_production(action, deployment, validation) -> None:
    """Default for dev/test: log the would-be production write."""
    logger.info(
        "apply_to_production action=%s deployment=%s validation=%s",
        action.action_id,
        deployment.deployment_id,
        validation.validation_id,
    )
