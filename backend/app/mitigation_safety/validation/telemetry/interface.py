"""TelemetrySource protocol — queries component health/metrics.

Returns a TelemetryResult mapping metric_name -> latest value. A SOURCE that
cannot answer (e.g. workspace unreachable, insufficient data) must return
`insufficient=True` so the check distinguishes "I checked and it's fine"
from "I could not check" (the latter blocks promotion — fail-safe).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class TelemetryQuery:
    component: str
    window_start: datetime
    window_end: datetime


@dataclass(frozen=True)
class TelemetryMetric:
    name: str
    value: float
    unit: str | None = None


@dataclass(frozen=True)
class TelemetryResult:
    component: str
    metrics: dict[str, float] = field(default_factory=dict)
    insufficient: bool = False
    detail: str | None = None


class TelemetrySource(Protocol):
    def query(self, q: TelemetryQuery) -> TelemetryResult: ...
