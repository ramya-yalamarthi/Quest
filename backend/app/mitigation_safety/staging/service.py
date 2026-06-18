"""StagingService — the single entry point for Approved -> Staged -> Validating.

Enforces:
- domain.assert_can_stage (revert handle + eligibility + state)         (MS-08)
- scope_isolation                                                       (MS-11, inv. 7)
- writes staging_deployment with revert_handle NOT NULL                 (MS-06, MS-07)
- transitions action state Approved -> Staged -> Validating             (MS-01)
- opens the validation window                                           (MS-08)
- emits audit rows for every transition                                 (MS-24, MS-18)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

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
    SafeModeHeld,
)
from app.mitigation_safety.domain.states import MitigationState
from app.mitigation_safety.domain.transitions import (
    assert_can_stage,
    assert_legal,
    record_transition,
)
from app.mitigation_safety.safemode.controller import SafeModeController
from app.mitigation_safety.staging.revert_handles import RevertHandleRegistry
from app.mitigation_safety.staging.runners.base import StagingRunner
from app.mitigation_safety.staging.scope_isolation import ScopeIsolationVerifier
from app.mitigation_safety.validation.service import ValidationService

logger = logging.getLogger("mitigation_safety.staging.service")


@dataclass(frozen=True)
class StagingResult:
    deployment_id: uuid.UUID
    validation_id: uuid.UUID
    window_start: datetime
    window_end: datetime
    status: str


class StagingService:
    def __init__(
        self,
        db: Session,
        audit: MitigationAuditLogger,
        *,
        cfg: MitigationConfig,
        runners: dict[str, StagingRunner],
        scope_verifier: ScopeIsolationVerifier,
        revert_registry: RevertHandleRegistry,
        safe_mode: SafeModeController,
        validation_svc: ValidationService,
    ) -> None:
        self.db = db
        self.audit = audit
        self.cfg = cfg
        self.runners = runners
        self.scope_verifier = scope_verifier
        self.revert_registry = revert_registry
        self.safe_mode = safe_mode
        self.validation_svc = validation_svc

    # -- entry point ----------------------------------------------------------
    def stage(
        self,
        *,
        action_id: uuid.UUID,
        type: str,
        target: str,
        artifacts_ref: str,
        expected_outcome: dict,
        revert_handle_ref: str,
        actor: str,
    ) -> StagingResult:
        # #10: lock the action row for the duration of this service call so
        # two concurrent stage() requests on the same action_id can't both
        # pass `assert_can_stage`. The lock is taken inside the caller's
        # transaction and released on commit/rollback.
        action = self._load_action_for_update(action_id)

        # Block writes while system Safe Mode is active. Per-category Safe
        # Mode does NOT block staging — MS-21 says in-flight validations
        # continue but require manual promote. We mirror that here: new
        # staging is allowed under category Safe Mode (promote is the gate).
        if self.safe_mode.is_active("system"):
            raise SafeModeHeld("system Safe Mode active; staging blocked")

        # MS-08 + invariant 4: state, eligibility, tested revert handle.
        # #9: VALIDATE before mutating. Previously we wrote the handle ref onto
        # the action and *then* checked it, which let an in-memory mutation
        # leak into a row that subsequently failed validation. Now we run
        # the guard against the requested ref directly and only persist if
        # it passes.
        candidate_ref = action.revert_handle_ref or revert_handle_ref
        action_view = _ActionView(
            action_id=action.action_id,
            state=action.state,
            eligible=action.eligible,
            revert_handle_ref=candidate_ref,
            category=action.category,
        )
        assert_can_stage(action_view, self.revert_registry)
        # Validated — safe to persist on the row.
        if action.revert_handle_ref is None:
            action.revert_handle_ref = revert_handle_ref

        # Invariant 7: staging cannot touch production.
        self.scope_verifier.assert_isolated(target, artifacts_ref)

        runner = self.runners.get(type)
        if runner is None:
            raise IllegalTransition("(no-runner)", type)

        try:
            runner_result = runner.apply(
                action_id=str(action.action_id),
                ticket_id=str(action.ticket_id) if action.ticket_id else None,
                target=target,
                artifacts_ref=artifacts_ref,
                expected_outcome=expected_outcome,
            )
        except Exception as exc:
            # MS-23: unhandled execution error -> Safe Mode for the category.
            # The outer transaction will roll back on the re-raise, which
            # would otherwise lose the Safe Mode write (invariant 5). We
            # persist Safe Mode in a SEPARATE session so it survives the
            # rollback, instead of committing the caller's transaction
            # (which would silently apply any partial writes the caller made
            # before calling stage — #8 / #23).
            _persist_safe_mode_in_isolation(
                category=action.category,
                exc=exc,
            )
            raise

        # MS-06, MS-07: record the staging deployment with the mandatory
        # revert_handle (NOT NULL) — the assert_can_stage gate above already
        # verified the handle is registered.
        deployment = StagingDeployment(
            action_id=action.action_id,
            ticket_id=action.ticket_id,
            type=type,
            target=runner_result.target,
            artifacts_ref=artifacts_ref,
            expected_outcome=expected_outcome or {},
            revert_handle=revert_handle_ref,
            status="OPEN",
        )
        self.db.add(deployment)
        self.db.flush()

        # Approved -> Staged
        assert_legal(action.state, MitigationState.STAGED.value)
        prev = action.state
        action.state = MitigationState.STAGED.value
        action.type = type
        action.state_history = record_transition(
            action.state_history,
            frm=prev,
            to=action.state,
            actor=actor,
            detail=f"deployment_id={deployment.deployment_id}, target={runner_result.target}",
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
                "deployment_id": str(deployment.deployment_id),
                "target": runner_result.target,
                "type": type,
            },
        )

        # Staged -> Validating + create the ValidationResult window.
        vr: ValidationResult = self.validation_svc.open_window(
            deployment=deployment, action=action, actor=actor
        )

        return StagingResult(
            deployment_id=deployment.deployment_id,
            validation_id=vr.validation_id,
            window_start=vr.window_start,
            window_end=vr.window_end,
            status="PENDING",
        )

    # -- helpers --------------------------------------------------------------
    def _load_action_for_update(self, action_id: uuid.UUID) -> BotActionLog:
        """Load + row-lock the action (#10).

        Postgres enforces the FOR UPDATE lock; SQLite (used in tests) silently
        treats `with_for_update()` as a no-op. The behavior we care about
        (concurrent stage races) is therefore exercised in real deployments
        but not in unit tests — an integration test against Postgres is the
        right place to assert it.
        """
        action = (
            self.db.query(BotActionLog)
            .filter(BotActionLog.action_id == action_id)
            .with_for_update(read=False)
            .one_or_none()
        )
        if action is None:
            raise IllegalTransition("(no-action)", "stage")
        return action


@dataclass(frozen=True)
class _ActionView:
    """Read-only snapshot used by `assert_can_stage` (#9: validate before
    mutating the persisted row)."""
    action_id: object
    state: str
    eligible: bool
    revert_handle_ref: str | None
    category: str


_isolation_session_factory = None


def set_isolation_session_factory(factory) -> None:
    """Test seam: install a sessionmaker used by `_persist_safe_mode_in_isolation`
    instead of importing the production SessionLocal. Pass None to reset."""
    global _isolation_session_factory
    _isolation_session_factory = factory


def _persist_safe_mode_in_isolation(*, category: str, exc: BaseException) -> None:
    """Open a fresh session, enter Safe Mode for the category, commit, close.

    The MS-23 contract is "after any unhandled mitigation-execution error,
    Safe Mode for the affected category is ON". The caller of `stage()` is
    about to receive a raised exception; their transaction will be rolled
    back. The Safe Mode entry MUST persist regardless, so we record it on a
    new session whose commit is independent of the caller's. Failures here
    are logged but never propagated — Safe Mode in the audit log is the
    durable record either way.
    """
    try:
        from app.mitigation_safety.audit.service import (
            MitigationAuditLogger as _Audit,
        )
        from app.mitigation_safety.safemode.controller import (
            SafeModeController as _Ctrl,
        )

        if _isolation_session_factory is not None:
            iso = _isolation_session_factory()
        else:
            from app.db.session import SessionLocal
            iso = SessionLocal()
        try:
            ctrl = _Ctrl(iso, _Audit(iso))
            ctrl.on_unhandled_execution_error(category, exc)
            iso.commit()
        finally:
            iso.close()
    except Exception as inner:
        logger.exception(
            "safe-mode-on-error isolation write failed: %s", inner
        )
