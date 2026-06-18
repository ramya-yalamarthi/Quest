"""MS-09 (c): affected-component health/telemetry within configured bounds.

Bounds live in `MitigationConfig.guards.telemetry_bounds[<component>][<metric>]
= {"min": float|None, "max": float|None}`. The check FAILs if any tracked
metric is out of range OR if the source reports `insufficient=True` (fail
toward human — invariant 6).
"""

from __future__ import annotations

from app.mitigation_safety.config import MitigationConfig
from app.mitigation_safety.validation.checks.base import (
    Check,
    CheckContext,
    CheckResult,
)
from app.mitigation_safety.validation.telemetry.interface import (
    TelemetryQuery,
    TelemetrySource,
)


def _component_for(ctx: CheckContext) -> str:
    """The component the deployment touches.

    Pulled from `expected_outcome['component']` when set; otherwise the
    deployment target is used (branch name or config scope). Demos can pass
    `expected_outcome={"component": "payments-api"}` explicitly.
    """
    return (ctx.expected_outcome or {}).get("component") or ctx.target


class TelemetryBoundsCheck(Check):
    name = "telemetry_bounds"

    def __init__(self, *, telemetry: TelemetrySource) -> None:
        self._telemetry = telemetry

    def applies(self, ctx: CheckContext) -> bool:
        return True

    def run_with_config(
        self, ctx: CheckContext, deadline_s: int, cfg: MitigationConfig
    ) -> CheckResult:
        component = _component_for(ctx)
        result = self._telemetry.query(
            TelemetryQuery(
                component=component,
                window_start=ctx.window_start,
                window_end=ctx.window_end,
            )
        )
        if result.insufficient:
            return CheckResult(
                name=self.name,
                status="FAIL",
                detail=f"insufficient telemetry for {component}: {result.detail}",
                evaluated_at=CheckResult.now_iso(),
            )
        bounds = (cfg.guards.telemetry_bounds or {}).get(component, {})
        breaches = []
        for metric_name, metric_value in result.metrics.items():
            spec = bounds.get(metric_name) or {}
            mn = spec.get("min")
            mx = spec.get("max")
            if mn is not None and metric_value < float(mn):
                breaches.append(f"{metric_name}={metric_value} < min {mn}")
            if mx is not None and metric_value > float(mx):
                breaches.append(f"{metric_name}={metric_value} > max {mx}")
        if breaches:
            return CheckResult(
                name=self.name,
                status="FAIL",
                detail="; ".join(breaches),
                evaluated_at=CheckResult.now_iso(),
            )
        return CheckResult(
            name=self.name,
            status="PASS",
            detail=f"{len(result.metrics)} metric(s) within bounds",
            evaluated_at=CheckResult.now_iso(),
        )

    # Default `run` reads the process-wide config snapshot.
    def run(self, ctx: CheckContext, deadline_s: int) -> CheckResult:
        from app.mitigation_safety.config import default_store

        return self.run_with_config(ctx, deadline_s, default_store().get())
