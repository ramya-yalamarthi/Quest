"""Validation window engine (MS-08, MS-09, MS-10, MS-13).

Responsibilities:
- `open_window(deployment, category)` — creates the ValidationResult row in
  PENDING state, computes window_end from config.
- `evaluate_now(validation_id)` — runs every applicable Check (time-bounded by
  `check_deadline_seconds`), updates the JSONB `checks` list, and transitions
  the overall status to PASS / FAIL when complete. FAIL fires an auto-revert
  (invariant 3) via the supplied callback.
- `mark_expired(validation_id)` — called by the worker when window_end passes
  without an overall PASS; transitions to EXPIRED and fires auto-revert
  (invariant 2).
- Idempotent across all entry points.
"""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.mitigation_safety.audit.service import MitigationAuditLogger
from app.mitigation_safety.config import MitigationConfig
from app.mitigation_safety.db.models import (
    BotActionLog,
    StagingDeployment,
    ValidationResult,
)
from app.mitigation_safety.domain.errors import IllegalTransition
from app.mitigation_safety.domain.states import MitigationState
from app.mitigation_safety.domain.transitions import (
    assert_legal,
    record_transition,
)
from app.mitigation_safety.validation.checks.base import (
    Check,
    CheckContext,
    CheckResult,
)

from app.mitigation_safety.domain.ids import aware_utc as _aware  # shared helper

logger = logging.getLogger("mitigation_safety.validation")


class ValidationService:
    def __init__(
        self,
        db: Session,
        audit: MitigationAuditLogger,
        *,
        checks: list[Check],
        cfg: MitigationConfig,
        on_failed: Callable[[uuid.UUID, str], None] | None = None,
        on_expired: Callable[[uuid.UUID], None] | None = None,
        on_attempt: Callable[[uuid.UUID, str], None] | None = None,
    ) -> None:
        self.db = db
        self.audit = audit
        self.checks = list(checks)
        self.cfg = cfg
        self._on_failed = on_failed
        self._on_expired = on_expired
        # MS-20 (#2): caller registers a hook that emits signal='attempt'
        # against the rolling-window store. Without this, guard `rate()` has
        # a zero denominator forever and never trips.
        self._on_attempt = on_attempt

    # ---- open ---------------------------------------------------------------
    def open_window(
        self,
        *,
        deployment: StagingDeployment,
        action: BotActionLog,
        actor: str,
    ) -> ValidationResult:
        # State: Staged -> Validating (caller has already moved Approved->Staged)
        assert_legal(action.state, MitigationState.VALIDATING.value)

        now = datetime.now(timezone.utc)
        window_s = self.cfg.validation_window_for(action.category)
        window_end = now + timedelta(seconds=window_s)

        vr = ValidationResult(
            deployment_id=deployment.deployment_id,
            window_start=now,
            window_end=window_end,
            checks=[],
            overall_status="PENDING",
        )
        self.db.add(vr)
        self.db.flush()

        prev_state = action.state
        action.state = MitigationState.VALIDATING.value
        action.validation_id = vr.validation_id
        action.state_history = record_transition(
            action.state_history,
            frm=prev_state,
            to=action.state,
            actor=actor,
            detail=f"validation_id={vr.validation_id}",
        )
        self.db.add(action)
        self.db.flush()

        self.audit.record(
            action_id=action.action_id,
            ticket_id=action.ticket_id,
            actor=actor,
            transition_type="state",
            from_state=prev_state,
            to_state=action.state,
            detail={
                "validation_id": str(vr.validation_id),
                # Always emit *aware* ISO timestamps so the audit payload
                # doesn't drift between SQLite (naive) and Postgres (aware).
                "window_start": _aware(vr.window_start).isoformat(),
                "window_end": _aware(vr.window_end).isoformat(),
            },
        )

        # MS-20 attempt signal — feeds the rolling-window denominator so the
        # guard evaluator can compute meaningful failure/rollback/decline rates.
        if self._on_attempt is not None:
            try:
                self._on_attempt(vr.validation_id, action.category)
            except Exception as exc:
                logger.warning("on_attempt callback failed: %s", exc)
        return vr

    # ---- run checks ---------------------------------------------------------
    def evaluate_now(self, validation_id: uuid.UUID | str) -> ValidationResult:
        vr = self._load(validation_id)
        if vr.overall_status in ("PASS", "FAIL", "EXPIRED"):
            return vr  # already terminal; idempotent

        deployment = self.db.get(StagingDeployment, vr.deployment_id)
        if deployment is None:
            raise IllegalTransition("(no-deployment)", "evaluate")
        action = self._find_action_for_deployment(deployment)
        if action is None:
            raise IllegalTransition("(no-action)", "evaluate")

        ctx = CheckContext(
            deployment_id=str(deployment.deployment_id),
            action_id=str(action.action_id),
            ticket_id=str(action.ticket_id) if action.ticket_id else None,
            category=action.category,
            type=deployment.type,
            target=deployment.target,
            artifacts_ref=deployment.artifacts_ref,
            expected_outcome=deployment.expected_outcome or {},
            window_start=vr.window_start,
            window_end=vr.window_end,
        )
        results: list[CheckResult] = []
        any_fail = False
        any_pending = False

        deadline = self.cfg.check_deadline_seconds
        # Run sequentially but with a hard timeout per check so a slow Check
        # cannot delay the window past `window_end` (MS-13, invariant 6).
        for check in self.checks:
            if not check.applies(ctx):
                continue
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(check.run, ctx, deadline)
                    result = fut.result(timeout=deadline)
            except FuturesTimeout:
                result = CheckResult(
                    name=getattr(check, "name", "unknown"),
                    status="FAIL",
                    detail=f"check exceeded {deadline}s deadline",
                    evaluated_at=CheckResult.now_iso(),
                )
            except Exception as exc:
                result = CheckResult(
                    name=getattr(check, "name", "unknown"),
                    status="FAIL",
                    detail=f"check raised: {exc}",
                    evaluated_at=CheckResult.now_iso(),
                )
            results.append(result)
            if result.status == "FAIL":
                any_fail = True
            elif result.status == "PENDING":
                any_pending = True

        vr.checks = [r.to_dict() for r in results]

        if any_fail:
            self._mark_failed(vr, action, results)
        elif any_pending or not results:
            vr.overall_status = "PENDING"
            self.db.add(vr)
            self.db.flush()
        else:
            vr.overall_status = "PASS"
            self.db.add(vr)
            self.db.flush()
            self.audit.record(
                action_id=action.action_id,
                ticket_id=action.ticket_id,
                actor="system",
                transition_type="state",
                from_state="VALIDATING",
                to_state="VALIDATING",  # action state unchanged; PASS is on the result
                detail={
                    "overall_status": "PASS",
                    "checks": vr.checks,
                },
            )
        return vr

    # ---- expire -------------------------------------------------------------
    def mark_expired(self, validation_id: uuid.UUID | str) -> ValidationResult:
        vr = self._load(validation_id)
        if vr.overall_status in ("PASS", "FAIL", "EXPIRED"):
            return vr
        now = datetime.now(timezone.utc)
        if _aware(vr.window_end) > now:
            # Called too early. Leave PENDING.
            return vr

        action = self._find_action_for_deployment_id(vr.deployment_id)
        if action is None:
            # Shouldn't happen, but don't promote / leak.
            vr.overall_status = "EXPIRED"
            vr.reverted_at = now
            self.db.add(vr)
            self.db.flush()
            return vr

        # Validating -> Expired -> Reverted (invariant 2)
        assert_legal(action.state, MitigationState.EXPIRED.value)
        prev = action.state
        action.state = MitigationState.EXPIRED.value
        action.state_history = record_transition(
            action.state_history,
            frm=prev,
            to=action.state,
            actor="system",
            detail="window expired with no PASS",
        )
        vr.overall_status = "EXPIRED"
        vr.reverted_at = now
        self.db.add(action)
        self.db.add(vr)
        self.db.flush()
        self.audit.record(
            action_id=action.action_id,
            ticket_id=action.ticket_id,
            actor="system",
            transition_type="state",
            from_state=prev,
            to_state=action.state,
            detail={"validation_id": str(vr.validation_id)},
        )

        if self._on_expired:
            try:
                self._on_expired(vr.validation_id)
            except Exception as exc:
                logger.exception("on_expired callback failed: %s", exc)
        return vr

    # ---- helpers ------------------------------------------------------------
    def get(self, validation_id: uuid.UUID | str) -> ValidationResult:
        return self._load(validation_id)

    def time_remaining(self, vr: ValidationResult) -> int:
        delta = _aware(vr.window_end) - datetime.now(timezone.utc)
        return max(0, int(delta.total_seconds()))

    def elapsed(self, vr: ValidationResult) -> int:
        delta = datetime.now(timezone.utc) - _aware(vr.window_start)
        return max(0, int(delta.total_seconds()))

    # ---- internals ----------------------------------------------------------
    def _load(self, validation_id) -> ValidationResult:
        vid = (
            validation_id
            if isinstance(validation_id, uuid.UUID)
            else uuid.UUID(str(validation_id))
        )
        vr = self.db.get(ValidationResult, vid)
        if vr is None:
            raise IllegalTransition("(no-validation)", str(vid))
        return vr

    def _find_action_for_deployment(
        self, deployment: StagingDeployment
    ) -> Optional[BotActionLog]:
        return (
            self.db.query(BotActionLog)
            .filter(BotActionLog.action_id == deployment.action_id)
            .one_or_none()
        )

    def _find_action_for_deployment_id(
        self, deployment_id: uuid.UUID
    ) -> Optional[BotActionLog]:
        deployment = self.db.get(StagingDeployment, deployment_id)
        if deployment is None:
            return None
        return self._find_action_for_deployment(deployment)

    def _mark_failed(
        self,
        vr: ValidationResult,
        action: BotActionLog,
        results: list[CheckResult],
    ) -> None:
        # State: Validating -> Failed -> Reverted (invariant 3)
        assert_legal(action.state, MitigationState.FAILED.value)
        prev = action.state
        action.state = MitigationState.FAILED.value
        failing = [r.name for r in results if r.status == "FAIL"]
        action.state_history = record_transition(
            action.state_history,
            frm=prev,
            to=action.state,
            actor="system",
            detail=f"failed checks: {','.join(failing)}",
        )
        vr.overall_status = "FAIL"
        vr.reverted_at = datetime.now(timezone.utc)
        self.db.add(action)
        self.db.add(vr)
        self.db.flush()
        self.audit.record(
            action_id=action.action_id,
            ticket_id=action.ticket_id,
            actor="system",
            transition_type="state",
            from_state=prev,
            to_state=action.state,
            detail={
                "validation_id": str(vr.validation_id),
                "failing_checks": failing,
            },
        )
        if self._on_failed:
            try:
                self._on_failed(vr.validation_id, "; ".join(failing) or "fail")
            except Exception as exc:
                logger.exception("on_failed callback failed: %s", exc)
