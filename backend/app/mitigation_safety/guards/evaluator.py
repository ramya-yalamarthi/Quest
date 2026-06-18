"""GuardEvaluator (MS-14, MS-16, MS-20).

Two responsibilities:

1. `record_event(signal, category, ...)`: write a `ms_guard_event` row.
   Called by services on the events listed in `rolling_window.py`.

2. `evaluate(category)`:
   - compute the rolling-window rates against `MitigationConfig.guards`;
   - if any threshold is crossed, enter Safe Mode for the category with
     entered_by=`guard:<signal>` (MS-20), and fire auto-revert on every
     in-flight validation for that category (MS-16). Returns a
     `GuardVerdict` for visibility.

Telemetry-breach detection on PROMOTED actions during their rollback
window is handled inline by `evaluate_post_promotion(category)`.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from app.mitigation_safety.audit.service import MitigationAuditLogger
from app.mitigation_safety.config import GuardThresholds, MitigationConfig
from app.mitigation_safety.db.models import (
    BotActionLog,
    StagingDeployment,
    ValidationResult,
)
from app.mitigation_safety.domain.states import MitigationState
from app.mitigation_safety.guards.auto_revert import AutoRevertTrigger
from app.mitigation_safety.guards.rolling_window import RollingWindowStore
from app.mitigation_safety.notifications.sink import (
    Notification,
    NotificationSink,
)
from app.mitigation_safety.safemode.controller import (
    SafeModeController,
    category_scope,
)
from app.mitigation_safety.validation.telemetry.interface import (
    TelemetryQuery,
    TelemetrySource,
)

logger = logging.getLogger("mitigation_safety.guards.evaluator")


@dataclass
class GuardVerdict:
    category: str
    safe_mode_entered: bool = False
    triggering_signal: str | None = None
    triggering_value: float | None = None
    auto_reverted_action_ids: list[uuid.UUID] = field(default_factory=list)
    breaches: list[dict] = field(default_factory=list)


class GuardEvaluator:
    def __init__(
        self,
        db: Session,
        audit: MitigationAuditLogger,
        *,
        cfg: MitigationConfig,
        rolling: RollingWindowStore,
        safe_mode: SafeModeController,
        auto_revert: AutoRevertTrigger,
        telemetry: TelemetrySource,
        notifier: NotificationSink,
    ) -> None:
        self.db = db
        self.audit = audit
        self.cfg = cfg
        self.rolling = rolling
        self.safe_mode = safe_mode
        self.auto_revert = auto_revert
        self.telemetry = telemetry
        self.notifier = notifier

    def record_event(
        self,
        *,
        signal: str,
        category: str,
        action_id: uuid.UUID | str | None = None,
        validation_id: uuid.UUID | str | None = None,
        value: float | None = None,
    ) -> None:
        self.rolling.record(
            signal=signal,
            category=category,
            action_id=action_id,
            validation_id=validation_id,
            value=value,
        )

    # ---- rolling-rate evaluation (MS-20) -----------------------------------
    def evaluate(self, category: str) -> GuardVerdict:
        verdict = GuardVerdict(category=category)
        if self.safe_mode.is_active(category_scope(category)):
            # Already in Safe Mode — nothing to escalate.
            return verdict

        t: GuardThresholds = self.cfg.guards
        window = t.rolling_window_seconds
        signals = [
            ("validation_failed", t.validation_failure_rate),
            ("rolled_back", t.rollback_rate),
            ("declined", t.decline_rate),
        ]

        for signal, threshold in signals:
            # #14: a threshold <= 0 is treated as "disabled" (any rate >= 0
            # would otherwise auto-trip immediately). Negative thresholds
            # are explicitly disabled — log once and skip.
            if threshold is None or threshold <= 0:
                continue
            rate = self.rolling.rate(
                signal=signal, category=category, window_s=window
            )
            if rate >= threshold:
                verdict.breaches.append(
                    {"signal": signal, "rate": rate, "threshold": threshold}
                )
                self._enter_safe_mode_for_signal(category, signal, rate, verdict)
                self._auto_revert_in_flight(category, signal, rate, verdict)
                # First breach is sufficient to enter Safe Mode; record the
                # rest for visibility but don't double-act.
                break

        return verdict

    # ---- telemetry breach during rollback window (MS-16) -------------------
    def evaluate_post_promotion(self, category: str) -> GuardVerdict:
        verdict = GuardVerdict(category=category)
        bounds = (self.cfg.guards.telemetry_bounds or {})
        if not bounds:
            return verdict
        promoted = self._actions_in_rollback_window(category)
        for action, deployment in promoted:
            comp = (deployment.expected_outcome or {}).get("component") or deployment.target
            spec = bounds.get(comp) or {}
            if not spec:
                continue
            # #15: window the telemetry query by the action's promotion
            # timestamp (when the change actually hit prod), NOT the staging
            # deployment's created_at. Old behavior produced false-positive
            # breaches drawn from the staging window — irrelevant to the
            # post-promotion state.
            from app.mitigation_safety.domain.ids import aware_utc
            from app.mitigation_safety.db.models import ValidationResult

            vr = None
            if action.validation_id is not None:
                vr = self.db.get(ValidationResult, action.validation_id)
            window_start = aware_utc(
                (vr.promoted_at if vr is not None else None)
                or deployment.created_at
            )
            res = self.telemetry.query(
                TelemetryQuery(
                    component=comp,
                    window_start=window_start,
                    window_end=datetime.now(timezone.utc),
                )
            )
            for metric_name, metric_value in res.metrics.items():
                rule = spec.get(metric_name) or {}
                mn, mx = rule.get("min"), rule.get("max")
                breached = (
                    (mn is not None and metric_value < float(mn))
                    or (mx is not None and metric_value > float(mx))
                )
                if breached:
                    verdict.breaches.append(
                        {
                            "signal": "telemetry_breach",
                            "metric": metric_name,
                            "value": metric_value,
                            "component": comp,
                        }
                    )
                    self._auto_revert_action(
                        action,
                        signal=f"telemetry:{metric_name}",
                        reason=f"{metric_name}={metric_value} breach for {comp}",
                        value=metric_value,
                        verdict=verdict,
                    )
        return verdict

    # ---- helpers -----------------------------------------------------------
    def _enter_safe_mode_for_signal(
        self,
        category: str,
        signal: str,
        rate: float,
        verdict: GuardVerdict,
    ) -> None:
        scope = category_scope(category)
        self.safe_mode.enter(
            scope=scope,
            entered_by=f"guard:{signal}",
            reason=f"rolling rate {rate:.2f} crossed threshold",
        )
        verdict.safe_mode_entered = True
        verdict.triggering_signal = signal
        verdict.triggering_value = rate
        self.notifier.emit(
            Notification(
                kind="safe_mode_entered",
                action_id=None,
                ticket_id=None,
                triggering=f"{signal}@{rate:.2f}",
                resulting_state="SAFE_MODE_ON",
                detail={"scope": scope, "rate": rate},
            )
        )

    def _auto_revert_in_flight(
        self,
        category: str,
        signal: str,
        rate: float,
        verdict: GuardVerdict,
    ) -> None:
        actions = self._in_flight_validations_for_category(category)
        for action in actions:
            self._auto_revert_action(
                action,
                signal=signal,
                reason=f"guard breach: {signal}={rate:.2f}",
                value=rate,
                verdict=verdict,
            )

    def _auto_revert_action(
        self,
        action: BotActionLog,
        *,
        signal: str,
        reason: str,
        value: float | None,
        verdict: GuardVerdict,
    ) -> None:
        self.auto_revert.fire(action_id=action.action_id, reason=reason, signal=signal)
        verdict.auto_reverted_action_ids.append(action.action_id)
        self.audit.record(
            action_id=action.action_id,
            ticket_id=action.ticket_id,
            actor=f"guard:{signal}",
            transition_type="guard",
            from_state=action.state,
            to_state="REVERT_TRIGGERED",
            detail={"reason": reason, "value": value, "signal": signal},
        )
        self.notifier.emit(
            Notification(
                kind="guard_rollback",
                action_id=str(action.action_id),
                ticket_id=str(action.ticket_id) if action.ticket_id else None,
                triggering=f"{signal}@{value}",
                resulting_state="REVERT_TRIGGERED",
                detail={"reason": reason},
            )
        )

    def _in_flight_validations_for_category(
        self, category: str
    ) -> Iterable[BotActionLog]:
        return (
            self.db.query(BotActionLog)
            .filter(
                BotActionLog.category == category,
                BotActionLog.state == MitigationState.VALIDATING.value,
            )
            .all()
        )

    def _actions_in_rollback_window(
        self, category: str
    ) -> list[tuple[BotActionLog, StagingDeployment]]:
        rows = (
            self.db.query(BotActionLog, StagingDeployment)
            .filter(
                BotActionLog.category == category,
                BotActionLog.state == MitigationState.PROMOTED.value,
                BotActionLog.rollback_window_end > datetime.now(timezone.utc),
            )
            .join(
                StagingDeployment,
                StagingDeployment.action_id == BotActionLog.action_id,
            )
            .all()
        )
        return list(rows)
