"""Check protocol + result shapes (MS-09).

Each Check produces a CheckResult with `name`, `status`, `detail`, and
`evaluated_at`. Execution is time-bounded — the runner enforces a deadline
and FAILs any check that does not return in time (MS-13, invariant 6).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol


CheckStatus = Literal["PENDING", "PASS", "FAIL"]


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    detail: str | None
    evaluated_at: str  # ISO-8601 UTC

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "evaluated_at": self.evaluated_at,
        }


@dataclass(frozen=True)
class CheckContext:
    deployment_id: str
    action_id: str
    ticket_id: str | None
    category: str
    type: Literal["code", "config"]
    target: str           # branch name (code) or scope name (config)
    artifacts_ref: str
    expected_outcome: dict
    window_start: datetime
    window_end: datetime


class Check(Protocol):
    name: str

    def applies(self, ctx: CheckContext) -> bool: ...
    def run(self, ctx: CheckContext, deadline_s: int) -> CheckResult: ...
