"""StagingRunner protocol — applies an action to its staging path.

`apply()` is called by StagingService AFTER the scope-isolation check and
AFTER the revert handle gate. A runner MAY make network calls (open a PR,
push a config to a non-prod scope) but MUST NOT touch production.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StagingRunnerResult:
    target: str            # branch name or scope name (echoed)
    external_ref: str | None  # PR url, change-id, etc.
    detail: str | None


class StagingRunner(Protocol):
    type: str  # 'code' | 'config'

    def apply(
        self,
        *,
        action_id: str,
        ticket_id: str | None,
        target: str,
        artifacts_ref: str,
        expected_outcome: dict,
    ) -> StagingRunnerResult: ...

    def discard(self, *, target: str) -> None:
        """Throw away the staging artifact (branch, config draft) after revert."""
        ...
