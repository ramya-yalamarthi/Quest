"""Scripted TelemetrySource for tests."""

from __future__ import annotations

from app.mitigation_safety.validation.telemetry.interface import (
    TelemetryQuery,
    TelemetryResult,
    TelemetrySource,
)


class MockTelemetrySource:
    """Scripted source. Each `script(component, metrics={...})` queues one
    response for the next query against `component`. After the queue is
    drained, the most recent script repeats. `insufficient()` returns
    insufficient=True until reset."""

    def __init__(self) -> None:
        self._scripts: dict[str, list[TelemetryResult]] = {}
        self._last: dict[str, TelemetryResult] = {}
        self._queries: list[TelemetryQuery] = []

    def script(
        self,
        component: str,
        *,
        metrics: dict[str, float] | None = None,
        insufficient: bool = False,
        detail: str | None = None,
    ) -> "MockTelemetrySource":
        res = TelemetryResult(
            component=component,
            metrics=dict(metrics or {}),
            insufficient=insufficient,
            detail=detail,
        )
        self._scripts.setdefault(component, []).append(res)
        return self

    def insufficient(self, component: str, detail: str = "no data") -> "MockTelemetrySource":
        return self.script(component, insufficient=True, detail=detail)

    # --- protocol -----------------------------------------------------------
    def query(self, q: TelemetryQuery) -> TelemetryResult:
        self._queries.append(q)
        queue = self._scripts.get(q.component) or []
        if queue:
            res = queue.pop(0)
            self._last[q.component] = res
            return res
        if q.component in self._last:
            return self._last[q.component]
        # Default benign response: empty metrics, NOT insufficient.
        return TelemetryResult(component=q.component, metrics={}, insufficient=False)

    @property
    def queries(self) -> list[TelemetryQuery]:
        return list(self._queries)
