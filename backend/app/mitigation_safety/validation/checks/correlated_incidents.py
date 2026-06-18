"""MS-09 (d): no new correlated incidents opened against the same component/
customer during the window.

`CorrelatedIncidentsSource` returns the count of new incidents opened in
the window for the action's component. A count > 0 FAILs the check.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.mitigation_safety.validation.checks.base import (
    Check,
    CheckContext,
    CheckResult,
)


@dataclass(frozen=True)
class CorrelatedIncidentsQuery:
    component: str
    ticket_id: str | None
    window_start: datetime
    window_end: datetime


class CorrelatedIncidentsSource(Protocol):
    def count(self, q: CorrelatedIncidentsQuery) -> int: ...


class StaticCorrelatedIncidentsSource:
    """Test/dev impl. `expect(component, count)` queues counts to return."""

    def __init__(self) -> None:
        self._queue: dict[str, list[int]] = {}

    def expect(self, component: str, count: int) -> "StaticCorrelatedIncidentsSource":
        self._queue.setdefault(component, []).append(int(count))
        return self

    def count(self, q: CorrelatedIncidentsQuery) -> int:
        queue = self._queue.get(q.component) or []
        if queue:
            return queue.pop(0)
        return 0


def _component_for(ctx: CheckContext) -> str:
    return (ctx.expected_outcome or {}).get("component") or ctx.target


class CorrelatedIncidentsCheck(Check):
    name = "correlated_incidents"

    def __init__(self, *, source: CorrelatedIncidentsSource) -> None:
        self._source = source

    def applies(self, ctx: CheckContext) -> bool:
        return True

    def run(self, ctx: CheckContext, deadline_s: int) -> CheckResult:
        try:
            n = self._source.count(
                CorrelatedIncidentsQuery(
                    component=_component_for(ctx),
                    ticket_id=ctx.ticket_id,
                    window_start=ctx.window_start,
                    window_end=ctx.window_end,
                )
            )
        except Exception as exc:
            return CheckResult(
                name=self.name,
                status="FAIL",
                detail=f"incident source error: {exc}",
                evaluated_at=CheckResult.now_iso(),
            )
        if n > 0:
            return CheckResult(
                name=self.name,
                status="FAIL",
                detail=f"{n} new correlated incident(s) opened during window",
                evaluated_at=CheckResult.now_iso(),
            )
        return CheckResult(
            name=self.name,
            status="PASS",
            detail="0 new correlated incidents",
            evaluated_at=CheckResult.now_iso(),
        )
