"""MS-09 (b): existing regression suite passes."""

from __future__ import annotations

from app.mitigation_safety.validation.checks.base import (
    Check,
    CheckContext,
    CheckResult,
)
from app.mitigation_safety.validation.ci.interface import CIRunner


class RegressionSuiteCheck(Check):
    name = "regression_suite"

    def __init__(self, *, ci: CIRunner) -> None:
        self._ci = ci

    def applies(self, ctx: CheckContext) -> bool:
        # MS-09(b) applies to both code and config types — config changes can
        # still break shared regressions (DB schema, contract tests, etc.).
        return True

    def run(self, ctx: CheckContext, deadline_s: int) -> CheckResult:
        try:
            run_id = self._ci.dispatch(
                suite=self.name,
                branch=ctx.target,
                artifacts_ref=ctx.artifacts_ref,
                action_id=ctx.action_id,
            )
            result = self._ci.poll(run_id, deadline_s=deadline_s)
        except Exception as exc:
            return CheckResult(
                name=self.name,
                status="FAIL",
                detail=f"CI dispatch/poll failed: {exc}",
                evaluated_at=CheckResult.now_iso(),
            )
        if result.status == "success":
            return CheckResult(
                name=self.name,
                status="PASS",
                detail=result.detail,
                evaluated_at=CheckResult.now_iso(),
            )
        return CheckResult(
            name=self.name,
            status="FAIL",
            detail=f"{result.status}: {result.detail}",
            evaluated_at=CheckResult.now_iso(),
        )
