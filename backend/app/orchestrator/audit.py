"""
Audit logger (WBS task O-06).

Records every supervisor decision and agent call.  In this no-Fabric build the
audit trail targets the existing Postgres ``ai_audit_log`` table.  By default it
logs in-memory + to stdout so the demo runs without a database; pass a SQLAlchemy
session-backed sink to persist.

ai_audit_log columns (for reference):
  ai_event_id, ticket_id, agent_name, model_name, input_json, output_json,
  confidence_json, supporting_incident_ids, was_used, created_at
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("orchestrator.audit")


class AuditLogger:
    def __init__(self, db_sink=None) -> None:
        # db_sink: optional callable(entry: dict) -> None that writes to Postgres.
        self.db_sink = db_sink
        self.events: list[dict] = []

    def log(
        self,
        ticket_id: str,
        agent_name: str,
        *,
        input_data: Optional[dict] = None,
        output_data: Optional[dict] = None,
        confidence: Optional[float] = None,
        was_used: Optional[bool] = None,
        model_name: Optional[str] = None,
        note: Optional[str] = None,
    ) -> dict:
        entry = {
            "ticket_id": ticket_id,
            "agent_name": agent_name,
            "model_name": model_name,
            "input_json": input_data,
            "output_json": output_data,
            "confidence_json": {"confidence": confidence} if confidence is not None else None,
            "was_used": was_used,
            "note": note,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.events.append(entry)
        logger.info("[audit] %s | %s | %s", ticket_id, agent_name, note or "")
        if self.db_sink is not None:
            try:
                self.db_sink(entry)
            except Exception as exc:  # never let audit persistence break the pipeline
                logger.warning("audit db_sink failed: %s", exc)
        return entry
