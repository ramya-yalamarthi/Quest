"""
Orchestrator API (WBS tasks O-07 webhook listener, O-09 accept/reject).

Follows the same APIRouter pattern as the other routers.  Register in main.py:
    from app.api.routers.orchestrator import router as orchestrator_router
    app.include_router(orchestrator_router)

The supervisor instance persists ticket state in Redis (or in-memory if
REDIS_URL is unset) and writes its audit trail to Postgres ai_audit_log.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.orchestrator import Orchestrator, OrchestrationRecord
from app.orchestrator.agents import default_agents
from app.orchestrator.audit import AuditLogger
from app.orchestrator.db_sink import postgres_audit_sink

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


def _live_prior_resolution_fetcher(ticket_id: str) -> Optional[dict]:
    """DB-backed fetcher for the Recommendation Agent (WBS R-03): the most recent
    resolution for this ticket. Fully optional -- any failure (no DB, non-UUID
    ticket id, no prior row) returns None so the pipeline degrades gracefully to
    'no prior resolution on record'.
    """
    try:
        tid = UUID(str(ticket_id))
    except (ValueError, TypeError, AttributeError):
        return None
    try:
        from app.db.session import SessionLocal
        from app.db.models.resolution import Resolution
    except Exception:
        return None
    db = None
    try:
        db = SessionLocal()
        row = (
            db.query(Resolution)
            .filter(Resolution.ticket_id == tid)
            .order_by(Resolution.created_at.desc())
            .first()
        )
        if row is None:
            return None
        return {
            "resolution_text": row.resolution_text,
            "root_cause": row.root_cause,
            "recommendedsteps": row.recommendedsteps,
        }
    except Exception:
        return None
    finally:
        if db is not None:
            db.close()


# One supervisor for the app: state store is shared (Redis/in-memory),
# audit goes to Postgres ai_audit_log via the existing SessionLocal pattern.
_orchestrator = Orchestrator(
    agents=default_agents(prior_resolution_fetcher=_live_prior_resolution_fetcher),
    audit=AuditLogger(db_sink=postgres_audit_sink),
)


class WebhookEvent(BaseModel):
    """Event ServiceNow/D365 sends when a ticket is created/transferred/reactivated.

    Only ticket_id is required. event_type is inferred if omitted. Any extra
    fields ServiceNow sends are accepted and forwarded to the agents as context.
    """
    model_config = ConfigDict(extra="allow")  # tolerate any extra ServiceNow fields

    ticket_id: str = Field(..., description="ServiceNow sys_id or ticket number")
    event_id: Optional[str] = Field(None, description="Unique id of THIS delivery; used for dedupe")
    event_type: Optional[str] = Field(None, description="create | transfer | reactivate (inferred if omitted)")
    priority: Optional[str] = Field(None, description="e.g. P1..P3")
    assigned_team: Optional[str] = Field(None, description="Currently assigned team")
    previous_team: Optional[str] = Field(None, description="Prior team (signals a transfer)")
    reactivation_count: Optional[int] = Field(None, description="Times reopened (>0 signals reactivation)")
    title: Optional[str] = Field(None, description="Ticket short description / title")
    description: Optional[str] = Field(None, description="Ticket full description")
    severity: Optional[str] = Field(None, description="Severity / impact")
    status: Optional[str] = Field(None, description="Ticket status")


class Decision(BaseModel):
    ticket_id: str = Field(..., description="The ticket the engineer is responding to")
    decision: str = Field(..., description="accept | reject")


def _summary(record: Optional[OrchestrationRecord]) -> dict:
    if record is None:
        return {"status": "ignored", "detail": "duplicate or unknown event"}
    return {
        "ticket_id": record.ticket_id,
        "event_type": record.event_type,
        "pipeline": record.pipeline,
        "current_agent": record.current_agent,
        "state": record.state,
        "advisories": record.advisories,
        "status_detail": record.status_detail,
    }


@router.post("/webhook")
def ingest_event(evt: WebhookEvent):
    """O-07: receive an ICM event and run the first agent in the pipeline."""
    record = _orchestrator.handle_event(evt.model_dump(exclude_none=True))
    return _summary(record)


@router.post("/decision")
def submit_decision(d: Decision):
    """O-09: engineer ACCEPT -> next agent; REJECT -> block + flag retraining."""
    try:
        record = _orchestrator.handle_decision(d.ticket_id, d.decision)
    except KeyError:
        raise HTTPException(status_code=404, detail="no orchestration state for ticket")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _summary(record)


@router.get("/state/{ticket_id}")
def get_state(ticket_id: str):
    """Inspect where a ticket currently sits in the pipeline."""
    record = _orchestrator.get_state(ticket_id)
    if record is None:
        raise HTTPException(status_code=404, detail="no orchestration state for ticket")
    return _summary(record)


@router.get("/health")
def health():
    """Liveness check for your teammate / ServiceNow connectivity test."""
    return {"status": "ok", "service": "orchestrator"}
