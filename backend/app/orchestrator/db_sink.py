"""
Postgres audit sink (WBS task O-06) -- follows the existing DB pattern.

Uses the same SessionLocal / ORM-model approach every other part of the app
uses (see app/db/session.py).  Plug it into the AuditLogger:

    from app.orchestrator import Orchestrator
    from app.orchestrator.audit import AuditLogger
    from app.orchestrator.db_sink import postgres_audit_sink

    orch = Orchestrator(audit=AuditLogger(db_sink=postgres_audit_sink))

The orchestrator's AuditLogger swallows sink errors, so a DB hiccup (or the
pending agent_name CHECK-constraint widening) never breaks the pipeline.
"""

from __future__ import annotations

import uuid
from typing import Optional

from app.db.session import SessionLocal
from app.db.models.ai_audit_log import AiAuditLog


def _as_uuid(value) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def postgres_audit_sink(entry: dict) -> None:
    """Write one audit entry to the ai_audit_log table."""
    db = SessionLocal()
    try:
        row = AiAuditLog(
            ticket_id=_as_uuid(entry.get("ticket_id")),
            agent_name=entry.get("agent_name") or "supervisor",
            model_name=entry.get("model_name") or "orchestrator",
            input_json=entry.get("input_json") or {},
            output_json=entry.get("output_json") or {"note": entry.get("note")},
            confidence_json=entry.get("confidence_json"),
            was_used=bool(entry.get("was_used")) if entry.get("was_used") is not None else False,
        )
        db.add(row)
        db.commit()
    finally:
        db.close()
