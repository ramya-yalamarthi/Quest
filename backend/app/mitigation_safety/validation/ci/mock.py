"""Scripted CIRunner used by tests and dev mode.

Test pattern:
    ci = MockCIRunner()
    ci.script("generated_tests", "success")
    ci.script("regression", "success")
"""

from __future__ import annotations

import itertools
import uuid
from typing import Iterable, Iterator

from app.mitigation_safety.validation.ci.interface import CIRunResult, CIStatus


class MockCIRunner:
    def __init__(self) -> None:
        self._scripts: dict[str, list[CIStatus]] = {}
        self._iters: dict[str, Iterator[CIStatus]] = {}
        self._dispatches: list[dict] = []
        self._cancels: list[str] = []
        self._runs: dict[str, str] = {}  # run_id -> suite

    def script(self, suite: str, *statuses: CIStatus) -> "MockCIRunner":
        self._scripts.setdefault(suite, []).extend(statuses)
        # Reset iterator if statuses changed.
        self._iters[suite] = itertools.chain(self._scripts[suite])
        return self

    def set_default(self, status: CIStatus = "success") -> "MockCIRunner":
        """Lazy default if no .script() was given for a suite."""
        self._default = status
        return self

    # --- protocol -----------------------------------------------------------
    def dispatch(
        self,
        *,
        suite: str,
        branch: str,
        artifacts_ref: str,
        action_id: str,
    ) -> str:
        run_id = f"mock-{suite}-{uuid.uuid4().hex[:8]}"
        self._dispatches.append(
            {
                "run_id": run_id,
                "suite": suite,
                "branch": branch,
                "artifacts_ref": artifacts_ref,
                "action_id": action_id,
            }
        )
        self._runs[run_id] = suite
        return run_id

    def poll(self, run_id: str, *, deadline_s: int) -> CIRunResult:
        suite = self._runs.get(run_id, "unknown")
        it = self._iters.get(suite)
        status: CIStatus
        if it is None:
            status = getattr(self, "_default", "success")
        else:
            try:
                status = next(it)
            except StopIteration:
                status = getattr(self, "_default", "success")
        detail = {
            "success": "all jobs green",
            "failure": "1 generated test failed",
            "timeout": "exceeded CI deadline",
            "queued": "queued",
            "in_progress": "running",
        }.get(status, "")
        return CIRunResult(
            run_id=run_id,
            status=status,
            suite=suite,
            detail=detail,
            url=None,
        )

    def cancel(self, run_id: str) -> None:
        self._cancels.append(run_id)

    # --- test introspection -------------------------------------------------
    @property
    def dispatches(self) -> list[dict]:
        return list(self._dispatches)

    @property
    def cancels(self) -> list[str]:
        return list(self._cancels)
