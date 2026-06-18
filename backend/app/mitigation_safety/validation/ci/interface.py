"""CIRunner protocol: dispatch a workflow + poll until terminal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


CIStatus = Literal["queued", "in_progress", "success", "failure", "timeout"]


@dataclass(frozen=True)
class CIRunResult:
    run_id: str
    status: CIStatus
    suite: str          # 'generated_tests' | 'regression'
    detail: str | None  # short human-readable summary
    url: str | None     # link to the CI run (if available)


class CIRunner(Protocol):
    def dispatch(
        self,
        *,
        suite: str,
        branch: str,
        artifacts_ref: str,
        action_id: str,
    ) -> str:
        """Kick off a run and return a run_id."""
        ...

    def poll(self, run_id: str, *, deadline_s: int) -> CIRunResult:
        """Block (with timeout) until the run reaches a terminal status."""
        ...

    def cancel(self, run_id: str) -> None:
        """Best-effort cancel; safe to no-op."""
        ...
