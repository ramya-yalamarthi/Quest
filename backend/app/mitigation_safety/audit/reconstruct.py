"""Single-query reconstructors for the audit log (MS-21, MS-24).

Both helpers return rows sorted by ts ascending so the caller can replay
the lifecycle of an action or a ticket.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.mitigation_safety.db.models import MitigationAuditLog


def by_action_id(db: Session, action_id: uuid.UUID | str) -> list[MitigationAuditLog]:
    # The column type's bind processor handles both UUID and string forms,
    # so we just pass the value through after normalizing to UUID.
    return (
        db.query(MitigationAuditLog)
        .filter(MitigationAuditLog.action_id == _coerce(action_id))
        .order_by(MitigationAuditLog.ts.asc())
        .all()
    )


def by_ticket_id(db: Session, ticket_id: uuid.UUID | str) -> list[MitigationAuditLog]:
    return (
        db.query(MitigationAuditLog)
        .filter(MitigationAuditLog.ticket_id == _coerce(ticket_id))
        .order_by(MitigationAuditLog.ts.asc())
        .all()
    )


def _coerce(value):
    """Match whatever the column expects.

    On Postgres `MitigationAuditLog.action_id` is a UUID column — the bind
    processor accepts both `uuid.UUID(...)` and the canonical string form.
    On the test SQLite schema the column is `VARCHAR(36)` so we hand it the
    string form directly. The column's Python type advertises this.
    """
    try:
        u = value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return value
    col_type = MitigationAuditLog.action_id.type.python_type  # type: ignore[attr-defined]
    if col_type is str:
        return str(u)
    return u
