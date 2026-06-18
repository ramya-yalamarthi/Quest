"""Small utilities (UUID + datetime) used across the module."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def as_uuid(value) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def aware_utc(dt: datetime | None) -> datetime | None:
    """Coerce a possibly-naive datetime to UTC-aware.

    SQLite returns naive timestamps for `DateTime(timezone=True)` columns;
    Postgres returns aware ones. Using this helper everywhere prevents the
    'naive vs aware' comparison errors that crept in during development.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
