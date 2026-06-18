"""MS-09 (e): human sign-off where the category requires it.

`HumanSignoffSource.has_signoff(action_id, category)` returns True iff a
human approver has signed off on the action. For categories that do NOT
require sign-off (configurable), the check is PASS without consulting the
source.
"""

from __future__ import annotations

from typing import Protocol

from app.mitigation_safety.validation.checks.base import (
    Check,
    CheckContext,
    CheckResult,
)


class HumanSignoffSource(Protocol):
    def has_signoff(self, *, action_id: str, category: str) -> bool: ...
    def required_for(self, category: str) -> bool: ...


class StaticHumanSignoffSource:
    def __init__(self) -> None:
        self._required: dict[str, bool] = {}
        self._signed: set[str] = set()

    def require(self, category: str, required: bool = True) -> "StaticHumanSignoffSource":
        self._required[category] = required
        return self

    def sign(self, action_id: str) -> "StaticHumanSignoffSource":
        self._signed.add(str(action_id))
        return self

    def has_signoff(self, *, action_id: str, category: str) -> bool:
        return str(action_id) in self._signed

    def required_for(self, category: str) -> bool:
        return bool(self._required.get(category, False))


class HumanSignoffCheck(Check):
    name = "human_signoff"

    def __init__(self, *, source: HumanSignoffSource) -> None:
        self._source = source

    def applies(self, ctx: CheckContext) -> bool:
        return self._source.required_for(ctx.category)

    def run(self, ctx: CheckContext, deadline_s: int) -> CheckResult:
        if not self._source.required_for(ctx.category):
            return CheckResult(
                name=self.name,
                status="PASS",
                detail="not required for category",
                evaluated_at=CheckResult.now_iso(),
            )
        signed = self._source.has_signoff(
            action_id=ctx.action_id, category=ctx.category
        )
        if signed:
            return CheckResult(
                name=self.name,
                status="PASS",
                detail="human signoff recorded",
                evaluated_at=CheckResult.now_iso(),
            )
        return CheckResult(
            name=self.name,
            status="FAIL",
            detail="human signoff required and not yet recorded",
            evaluated_at=CheckResult.now_iso(),
        )
