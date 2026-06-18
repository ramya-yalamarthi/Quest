"""RevertService — idempotent revert / rollback (MS-13, MS-17, invariant 8).

Handles two paths uniformly:
- Staged or Validating  -> Reverted   (staging discard)
- Promoted within window -> RolledBack (calls registered revert handle)

Re-issuing a revert that already terminated returns idempotent=True with
the existing terminal state — no exception, no second handle invocation.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.mitigation_safety.audit.service import MitigationAuditLogger
from app.mitigation_safety.db.models import (
    BotActionLog,
    StagingDeployment,
    ValidationResult,
)
from app.mitigation_safety.domain.errors import IllegalTransition
from app.mitigation_safety.domain.states import (
    MitigationState,
    is_terminal,
)
from app.mitigation_safety.domain.transitions import (
    assert_legal,
    record_transition,
)
from app.mitigation_safety.staging.revert_handles import RevertHandleRegistry
from app.mitigation_safety.staging.runners.base import StagingRunner

logger = logging.getLogger("mitigation_safety.staging.revert")


@dataclass(frozen=True)
class RevertResult:
    action_id: uuid.UUID
    state: str
    idempotent: bool


class RevertService:
    def __init__(
        self,
        db: Session,
        audit: MitigationAuditLogger,
        *,
        revert_registry: RevertHandleRegistry,
        runners: dict[str, StagingRunner],
    ) -> None:
        self.db = db
        self.audit = audit
        self.revert_registry = revert_registry
        self.runners = runners

    def revert(
        self,
        *,
        action_id: uuid.UUID | str,
        reason: str,
        actor: str,
    ) -> RevertResult:
        aid = action_id if isinstance(action_id, uuid.UUID) else uuid.UUID(str(action_id))
        action = self.db.get(BotActionLog, aid)
        if action is None:
            raise IllegalTransition("(no-action)", "revert")

        # Idempotent path: already terminal in a reverted state.
        if action.state in (
            MitigationState.REVERTED.value,
            MitigationState.ROLLEDBACK.value,
        ):
            return RevertResult(
                action_id=action.action_id,
                state=action.state,
                idempotent=True,
            )

        # Drafted / Approved have no deployment to revert — illegal.
        if action.state in (
            MitigationState.DRAFTED.value,
            MitigationState.APPROVED.value,
        ):
            raise IllegalTransition(action.state, MitigationState.REVERTED.value)

        # Rejected / Closed are terminals that don't admit revert.
        if is_terminal(MitigationState(action.state)):
            raise IllegalTransition(action.state, "revert")

        if action.state == MitigationState.PROMOTED.value:
            return self._rollback_promoted(action, reason=reason, actor=actor)

        # Staged / Validating / Failed / Expired -> Reverted via staging discard.
        return self._revert_staging(action, reason=reason, actor=actor)

    # ---- helpers -----------------------------------------------------------
    def _revert_staging(
        self, action: BotActionLog, *, reason: str, actor: str
    ) -> RevertResult:
        # Walk through Failed/Expired if needed (Validating -> Failed -> Reverted
        # path is the one ValidationService uses; callers reverting directly
        # from Staged or Validating need a single step).
        prev = action.state
        if prev == MitigationState.VALIDATING.value:
            # Failed is a permissible intermediate; the validation service may
            # have already set it. If still VALIDATING, allow a direct Revert.
            # The state machine permits Failed/Expired -> Reverted, NOT
            # Validating -> Reverted, so we synthesize a Failed step here.
            action.state = MitigationState.FAILED.value
            action.state_history = record_transition(
                action.state_history,
                frm=prev,
                to=action.state,
                actor=actor,
                detail=f"force-fail for revert: {reason}",
            )
            self.audit.record(
                action_id=action.action_id,
                ticket_id=action.ticket_id,
                actor=actor,
                transition_type="state",
                from_state=prev,
                to_state=action.state,
                detail={"reason": reason, "synthetic": True},
            )
            prev = action.state

        assert_legal(action.state, MitigationState.REVERTED.value)
        deployment = self._find_deployment(action.action_id)
        if deployment is not None:
            runner = self.runners.get(deployment.type)
            if runner is not None:
                try:
                    runner.discard(target=deployment.target)
                except Exception as exc:
                    logger.warning("runner.discard failed: %s", exc)
            deployment.status = "REVERTED"
            self.db.add(deployment)

        # Mark the validation result reverted if it was still pending.
        if action.validation_id is not None:
            vr = self.db.get(ValidationResult, action.validation_id)
            if vr is not None and vr.overall_status == "PENDING":
                vr.overall_status = "FAIL"
                vr.reverted_at = datetime.now(timezone.utc)
                self.db.add(vr)

        action.state = MitigationState.REVERTED.value
        action.state_history = record_transition(
            action.state_history,
            frm=prev,
            to=action.state,
            actor=actor,
            detail=reason,
        )
        self.db.add(action)
        self.db.flush()
        self.audit.record(
            action_id=action.action_id,
            ticket_id=action.ticket_id,
            actor=actor,
            transition_type="state",
            from_state=prev,
            to_state=action.state,
            detail={"reason": reason},
        )
        return RevertResult(
            action_id=action.action_id,
            state=action.state,
            idempotent=False,
        )

    def _rollback_promoted(
        self, action: BotActionLog, *, reason: str, actor: str
    ) -> RevertResult:
        # Promoted -> RolledBack: execute the registered revert handle.
        deployment = self._find_deployment(action.action_id)
        if deployment is None:
            raise IllegalTransition("(no-deployment)", "rollback")

        # #11: NULL rollback_window_end is treated as ELAPSED, not "infinite".
        # An action that got into PROMOTED without a window must not get an
        # unbounded rollback path; that would defeat MS-15.
        # #12: Auto-close the action (Promoted -> Closed) and RETURN that
        # state cleanly instead of raising mid-flush. The previous code
        # flushed CLOSED then raised IllegalTransition — on the caller's
        # rollback-on-exception, the CLOSED state write was discarded, so
        # the next call saw PROMOTED again and re-triggered the same logic.
        from app.mitigation_safety.domain.ids import aware_utc

        rw_end = aware_utc(action.rollback_window_end)
        window_elapsed = (
            rw_end is None or rw_end <= datetime.now(timezone.utc)
        )
        if window_elapsed:
            prev = action.state
            assert_legal(prev, MitigationState.CLOSED.value)
            action.state = MitigationState.CLOSED.value
            action.state_history = record_transition(
                action.state_history,
                frm=prev,
                to=action.state,
                actor=actor,
                detail=(
                    "rollback window elapsed"
                    if rw_end is not None
                    else "no rollback window set; auto-closed"
                ),
            )
            self.db.add(action)
            self.db.flush()
            self.audit.record(
                action_id=action.action_id,
                ticket_id=action.ticket_id,
                actor=actor,
                transition_type="state",
                from_state=prev,
                to_state=action.state,
                detail={
                    "reason": "rollback window elapsed",
                    "rw_end": rw_end.isoformat() if rw_end else None,
                },
            )
            # MS-26: notify the engineer/lead — they tried to roll back too
            # late; the action is now permanent.
            return RevertResult(
                action_id=action.action_id,
                state=action.state,  # CLOSED
                idempotent=False,
            )

        # Invoke the registered, tested revert handle.
        try:
            self.revert_registry.execute(
                deployment.revert_handle,
                payload={
                    "action_id": str(action.action_id),
                    "ticket_id": str(action.ticket_id) if action.ticket_id else None,
                    "deployment_id": str(deployment.deployment_id),
                    "target": deployment.target,
                    "reason": reason,
                },
            )
        except KeyError:
            # Handle missing — should not happen because the staging gate
            # required it, but fail toward audit + raise.
            raise

        prev = action.state
        assert_legal(prev, MitigationState.ROLLEDBACK.value)
        action.state = MitigationState.ROLLEDBACK.value
        action.state_history = record_transition(
            action.state_history,
            frm=prev,
            to=action.state,
            actor=actor,
            detail=reason,
        )
        deployment.status = "ROLLEDBACK"
        self.db.add(action)
        self.db.add(deployment)
        self.db.flush()
        self.audit.record(
            action_id=action.action_id,
            ticket_id=action.ticket_id,
            actor=actor,
            transition_type="state",
            from_state=prev,
            to_state=action.state,
            detail={"reason": reason, "revert_handle": deployment.revert_handle},
        )
        return RevertResult(
            action_id=action.action_id,
            state=action.state,
            idempotent=False,
        )

    def _find_deployment(self, action_id: uuid.UUID) -> StagingDeployment | None:
        return (
            self.db.query(StagingDeployment)
            .filter(StagingDeployment.action_id == action_id)
            .order_by(StagingDeployment.created_at.desc())
            .first()
        )
