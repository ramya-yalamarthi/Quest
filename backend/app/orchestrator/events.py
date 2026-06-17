"""
Event classification (WBS task O-03).

Turns a raw ICM webhook payload into one of three known event types.  The
supervisor uses the result to decide which agent pipeline to run.
"""

from enum import Enum


class EventType(str, Enum):
    CREATE = "create"          # new ticket            -> UC1
    TRANSFER = "transfer"      # ticket reassigned     -> UC2
    REACTIVATE = "reactivate"  # closed ticket reopens -> UC3


def classify_event(payload: dict) -> EventType:
    """Derive the event type from an ICM webhook payload (O-03).

    Prefers an explicit ``event_type`` field.  If it's missing, falls back to
    inferring from the payload shape so the supervisor is resilient to
    different ICM sources.
    """
    explicit = str(payload.get("event_type", "")).strip().lower()
    valid = {e.value for e in EventType}
    if explicit in valid:
        return EventType(explicit)

    # --- inference fallback ---------------------------------------------
    try:
        reactivations = int(payload.get("reactivation_count", 0) or 0)
    except (TypeError, ValueError):
        reactivations = 0
    if reactivations > 0:
        return EventType.REACTIVATE

    if payload.get("transferred_from") or payload.get("previous_team"):
        return EventType.TRANSFER

    return EventType.CREATE
