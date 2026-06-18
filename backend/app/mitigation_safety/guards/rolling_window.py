"""Rolling-window counters backed by ms_guard_event (MS-20).

Signals tracked:
  attempt             — one row per validation OPENED
  validation_failed   — one row per Validating -> Failed
  rolled_back         — one row per Promoted -> RolledBack
  declined            — one row per human REJECT/decline

Rate helpers:
  rate(signal, category, window_s) -> ratio of `signal` events to `attempt`
  events in the window (0.0 if attempts < min_samples).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.mitigation_safety.db.models import GuardEvent


class RollingWindowStore:
    def __init__(self, db: Session, *, min_samples: int = 5) -> None:
        self.db = db
        self.min_samples = min_samples

    def record(
        self,
        *,
        signal: str,
        category: str,
        action_id: uuid.UUID | str | None = None,
        validation_id: uuid.UUID | str | None = None,
        value: float | None = None,
    ) -> GuardEvent:
        row = GuardEvent(
            category=category,
            signal=signal,
            action_id=_uuid(action_id) if action_id else None,
            validation_id=_uuid(validation_id) if validation_id else None,
            metric_value=value,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def count(self, *, signal: str, category: str, window_s: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_s)
        return (
            self.db.query(func.count(GuardEvent.event_id))
            .filter(
                GuardEvent.category == category,
                GuardEvent.signal == signal,
                GuardEvent.ts >= cutoff,
            )
            .scalar()
            or 0
        )

    def rate(
        self,
        *,
        signal: str,
        category: str,
        window_s: int,
        denom_signal: str = "attempt",
    ) -> float:
        attempts = self.count(signal=denom_signal, category=category, window_s=window_s)
        if attempts < self.min_samples:
            return 0.0
        events = self.count(signal=signal, category=category, window_s=window_s)
        return events / attempts


def _uuid(value) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))
