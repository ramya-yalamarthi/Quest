"""Append-only audit logger for state, safe_mode, guard, and config events.

This logger exposes ONLY an insert API — there is no update/delete method.
Combined with the DB-level triggers + REVOKE grants (see
`app.mitigation_safety.db.grants`), it satisfies MS-18 / invariant 9.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.mitigation_safety.db.models import MitigationAuditLog

logger = logging.getLogger("mitigation_safety.audit")

TransitionType = Literal["state", "safe_mode", "guard", "config", "system"]


class MitigationAuditLogger:
    """Insert-only sink. Caller controls the transaction (commit/rollback).

    Pattern:
        with SessionLocal() as db:
            audit = MitigationAuditLogger(db)
            audit.record(
                action_id=...,
                ticket_id=...,
                actor="human:42",
                transition_type="state",
                from_state="VALIDATING",
                to_state="PROMOTED",
                detail={"reason": "engineer confirm"},
            )
            db.commit()
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        *,
        action_id: uuid.UUID | str,
        ticket_id: uuid.UUID | str | None,
        actor: str,
        transition_type: TransitionType,
        from_state: str | None = None,
        to_state: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> MitigationAuditLog:
        row = MitigationAuditLog(
            action_id=_uuid(action_id),
            ticket_id=_uuid(ticket_id) if ticket_id is not None else None,
            actor=actor,
            transition_type=transition_type,
            from_state=from_state,
            to_state=to_state,
            detail=detail or {},
        )
        self.db.add(row)
        # Force flush so audit_id is populated and any DB-level enforcement
        # (e.g. the immutability trigger if misused) surfaces immediately.
        self.db.flush()
        logger.info(
            "audit %s -> %s | actor=%s | type=%s | action=%s",
            from_state or "?",
            to_state or "?",
            actor,
            transition_type,
            action_id,
        )
        return row

    def record_many(self, entries: list[dict[str, Any]]) -> list[MitigationAuditLog]:
        return [self.record(**e) for e in entries]


def _uuid(value) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))
