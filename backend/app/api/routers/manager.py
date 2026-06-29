from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.auth.deps import get_current_user
from app.db.models.ticket import Ticket
from app.db.models.user import User
from app.orchestrator.sla import sla_status, escalation_reminder
from app.agents.communication import flag_missing_updates, DEFAULT_COMMUNICATION_SLA_HOURS

router = APIRouter(prefix="/manager", tags=["manager"])


def manager_only(current: dict) -> None:
    if current.get("role") != "SUPPORT_MANAGER":
        raise HTTPException(status_code=403, detail="Only SUPPORT_MANAGER can view the risk view")


@router.get("/risk-view")
def risk_view(db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Manager/audit view: every open ticket at risk on SLA, stuck assignment,
    or missing customer communication -- the things a manager needs to catch
    BEFORE the customer escalates."""
    manager_only(current)

    comm_gaps = {g["ticket_id"]: g for g in flag_missing_updates(db, DEFAULT_COMMUNICATION_SLA_HOURS)}

    rows = []
    for t in db.query(Ticket).filter(Ticket.status.in_(["NEW", "ASSIGNED"])).all():
        sla = sla_status(t.priority, t.created_at, assigned_at=t.assigned_at)
        reminder = escalation_reminder(sla)
        comm_gap = comm_gaps.get(str(t.ticket_id))
        if not (sla["resolution_breached"] or sla["response_breached"] or reminder or comm_gap):
            continue  # only at-risk tickets show up here

        assignee = db.query(User).filter(User.user_id == t.assigned_to).first() if t.assigned_to else None
        rows.append({
            "ticket_id": str(t.ticket_id), "title": t.title, "status": t.status, "priority": t.priority,
            "assigned_to": assignee.display_name if assignee else None,
            "sla_tier": sla["tier"],
            "resolution_breached": sla["resolution_breached"],
            "response_breached": sla["response_breached"],
            "minutes_to_resolution_deadline": sla["minutes_to_resolution_deadline"],
            "escalation_reminder": reminder,
            "communication_gap_hours": comm_gap["hours_since_last_update"] if comm_gap else None,
        })

    rows.sort(key=lambda r: r["minutes_to_resolution_deadline"])
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "at_risk_count": len(rows), "tickets": rows}
