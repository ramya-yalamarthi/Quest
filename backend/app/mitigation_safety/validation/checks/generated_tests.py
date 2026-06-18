"""MS-09 (a): generated tests pass in CI [code-type only]."""

from __future__ import annotations

from app.mitigation_safety.validation.checks.base import (
    Check,
    CheckContext,
    CheckResult,
)
from app.mitigation_safety.validation.ci.interface import CIRunner


class GeneratedTestsCheck(Check):
    name = "generated_tests"

    def __init__(self, *, ci: CIRunner) -> None:
        self._ci = ci

    def applies(self, ctx: CheckContext) -> bool:
        # MS-09(a) is code-only.
        return ctx.type == "code"

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
        # Anything other than success — including timeout and in_progress past
        # the deadline — fails (invariant 6: fail toward human/revert).
        return CheckResult(
            name=self.name,
            status="FAIL",
            detail=f"{result.status}: {result.detail}",
            evaluated_at=CheckResult.now_iso(),
        )
