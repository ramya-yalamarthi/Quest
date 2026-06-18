"""Service container — builds the same service graph for every request.

A single `services(db)` factory is the only place that composes the layer.
Both the API routes AND the worker jobs go through it (the worker's
`_build_runtime` is the worker-side counterpart; future refactor could
merge them).

Backends (CIRunner, TelemetrySource) are selected from env:
    MITIGATION_SAFETY_CI_BACKEND      = github | mock   (default: mock)
    MITIGATION_SAFETY_TELEMETRY_BACKEND = azure | mock  (default: mock)

If a real backend is selected but its env vars are missing, we log and
fall back to mocks — Safe Mode stays ON (invariant 5).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.mitigation_safety.audit.service import MitigationAuditLogger
from app.mitigation_safety.config import default_store
from app.mitigation_safety.guards.auto_revert import AutoRevertTrigger
from app.mitigation_safety.guards.evaluator import GuardEvaluator
from app.mitigation_safety.guards.rolling_window import RollingWindowStore
from app.mitigation_safety.notifications.sink import default_sink
from app.mitigation_safety.safemode.controller import SafeModeController
from app.mitigation_safety.staging.promotion import (
    PromotionService,
    noop_apply_to_production,
)
from app.mitigation_safety.staging.revert import RevertService
from app.mitigation_safety.staging.revert_handles import default_registry
from app.mitigation_safety.staging.runners import (
    CodeStagingRunner,
    ConfigStagingRunner,
)
from app.mitigation_safety.staging.scope_isolation import ScopeIsolationVerifier
from app.mitigation_safety.staging.service import StagingService
from app.mitigation_safety.validation.checks import default_checks
from app.mitigation_safety.validation.checks.correlated_incidents import (
    StaticCorrelatedIncidentsSource,
)
from app.mitigation_safety.validation.checks.human_signoff import (
    StaticHumanSignoffSource,
)
from app.mitigation_safety.validation.ci.interface import CIRunner
from app.mitigation_safety.validation.ci.mock import MockCIRunner
from app.mitigation_safety.validation.service import ValidationService
from app.mitigation_safety.validation.telemetry.interface import TelemetrySource
from app.mitigation_safety.validation.telemetry.mock import MockTelemetrySource

logger = logging.getLogger("mitigation_safety.api.container")


# Process-wide singletons for stateful sources (incidents/signoff) so a test
# that primes them via the registry observes those values in the API too.
_INCIDENTS = StaticCorrelatedIncidentsSource()
_SIGNOFF = StaticHumanSignoffSource()


def get_incidents_source() -> StaticCorrelatedIncidentsSource:
    return _INCIDENTS


def get_signoff_source() -> StaticHumanSignoffSource:
    return _SIGNOFF


def _pick_ci() -> CIRunner:
    backend = (os.getenv("MITIGATION_SAFETY_CI_BACKEND") or "mock").lower()
    if backend == "github":
        if not (os.getenv("GITHUB_TOKEN") and os.getenv("GITHUB_REPO")):
            logger.warning(
                "MITIGATION_SAFETY_CI_BACKEND=github but env incomplete; "
                "falling back to MockCIRunner (Safe Mode stays ON)"
            )
            return MockCIRunner().set_default("success")
        from app.mitigation_safety.validation.ci.github_actions import (
            GitHubActionsCIRunner,
        )
        return GitHubActionsCIRunner()
    return MockCIRunner().set_default("success")


def _pick_telemetry() -> TelemetrySource:
    backend = (os.getenv("MITIGATION_SAFETY_TELEMETRY_BACKEND") or "mock").lower()
    if backend == "azure":
        if not (
            os.getenv("AZURE_TENANT_ID")
            and os.getenv("AZURE_CLIENT_ID")
            and os.getenv("AZURE_CLIENT_SECRET")
            and os.getenv("AZURE_MONITOR_WORKSPACE_ID")
        ):
            logger.warning(
                "MITIGATION_SAFETY_TELEMETRY_BACKEND=azure but env incomplete; "
                "falling back to MockTelemetrySource"
            )
            return MockTelemetrySource()
        from app.mitigation_safety.validation.telemetry.azure_monitor import (
            AzureMonitorTelemetrySource,
        )
        return AzureMonitorTelemetrySource()
    return MockTelemetrySource()


_CI: CIRunner | None = None
_TELEMETRY: TelemetrySource | None = None


def get_ci() -> CIRunner:
    global _CI
    if _CI is None:
        _CI = _pick_ci()
    return _CI


def get_telemetry() -> TelemetrySource:
    global _TELEMETRY
    if _TELEMETRY is None:
        _TELEMETRY = _pick_telemetry()
    return _TELEMETRY


# Tests override these singletons:
def set_ci_runner(ci: CIRunner) -> None:
    global _CI
    _CI = ci


def set_telemetry(t: TelemetrySource) -> None:
    global _TELEMETRY
    _TELEMETRY = t


@dataclass
class Services:
    audit: MitigationAuditLogger
    safe_mode: SafeModeController
    staging: StagingService
    validation: ValidationService
    promotion: PromotionService
    revert: RevertService
    guard: GuardEvaluator


def services(db: Session) -> Services:
    cfg = default_store().get()
    audit = MitigationAuditLogger(db)
    safe_mode = SafeModeController(db, audit)
    notifier = default_sink()

    ci = get_ci()
    telemetry = get_telemetry()
    incidents = get_incidents_source()
    signoff = get_signoff_source()

    checks = default_checks(
        ci=ci, telemetry=telemetry, incidents=incidents, signoff=signoff
    )
    runners = {"code": CodeStagingRunner(), "config": ConfigStagingRunner()}
    revert_service = RevertService(
        db, audit, revert_registry=default_registry(), runners=runners
    )

    def _revert_callable(action_id, reason, actor):
        revert_service.revert(action_id=action_id, reason=reason, actor=actor)
        # The caller commits its own transaction; we leave the db state alone.

    auto_revert = AutoRevertTrigger(revert_callable=_revert_callable)
    rolling = RollingWindowStore(db, min_samples=cfg.guards.min_samples)

    validation_svc = ValidationService(
        db, audit,
        checks=checks,
        cfg=cfg,
        on_failed=lambda vid, reason: _on_failed(db, vid, reason, auto_revert, rolling),
        on_expired=lambda vid: _on_expired(db, vid, auto_revert, rolling),
        on_attempt=lambda vid, category: rolling.record(
            signal="attempt", category=category, validation_id=vid
        ),
    )

    staging_svc = StagingService(
        db, audit,
        cfg=cfg,
        runners=runners,
        scope_verifier=ScopeIsolationVerifier(),
        revert_registry=default_registry(),
        safe_mode=safe_mode,
        validation_svc=validation_svc,
    )

    promotion_svc = PromotionService(
        db, audit,
        cfg=cfg,
        safe_mode=safe_mode,
        notifier=notifier,
        apply_to_production=noop_apply_to_production,
    )

    guard_eval = GuardEvaluator(
        db, audit,
        cfg=cfg,
        rolling=rolling,
        safe_mode=safe_mode,
        auto_revert=auto_revert,
        telemetry=telemetry,
        notifier=notifier,
    )
    return Services(
        audit=audit,
        safe_mode=safe_mode,
        staging=staging_svc,
        validation=validation_svc,
        promotion=promotion_svc,
        revert=revert_service,
        guard=guard_eval,
    )


def _on_failed(db, validation_id, reason, auto_revert, rolling) -> None:
    from app.mitigation_safety.db.models import (
        BotActionLog,
        StagingDeployment,
        ValidationResult,
    )

    vr = db.get(ValidationResult, validation_id)
    if vr is None:
        return
    deployment = db.get(StagingDeployment, vr.deployment_id)
    if deployment is None:
        return
    action = (
        db.query(BotActionLog)
        .filter(BotActionLog.action_id == deployment.action_id)
        .one_or_none()
    )
    if action is None:
        return
    # MS-20: feed the rolling-window so the guard evaluator can trip Safe Mode.
    rolling.record(
        signal="validation_failed",
        category=action.category,
        action_id=action.action_id,
        validation_id=vr.validation_id,
    )
    auto_revert.fire(
        action_id=action.action_id, reason=reason, signal="validation_failed"
    )


def _on_expired(db, validation_id, auto_revert, rolling) -> None:
    from app.mitigation_safety.db.models import (
        BotActionLog,
        StagingDeployment,
        ValidationResult,
    )

    vr = db.get(ValidationResult, validation_id)
    if vr is None:
        return
    deployment = db.get(StagingDeployment, vr.deployment_id)
    if deployment is None:
        return
    action = (
        db.query(BotActionLog)
        .filter(BotActionLog.action_id == deployment.action_id)
        .one_or_none()
    )
    if action is None:
        return
    rolling.record(
        signal="validation_failed",  # expiry counts as a failure for the rate
        category=action.category,
        action_id=action.action_id,
        validation_id=vr.validation_id,
    )
    auto_revert.fire(
        action_id=action.action_id,
        reason="window expired",
        signal="window_expired",
    )
