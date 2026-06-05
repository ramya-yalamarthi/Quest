from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, cast, Text
from app.db.models.user import User
from app.db.models.ticket import Ticket
from app.db.models.email import Email
from app.config import SLA_UPDATE_HOURS
from app.utils.embeddings import get_embedding

ALLOWED_TICKET_STATUSES = {"NEW", "ASSIGNED", "RESOLVED"}

def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()

def ensure_user(db: Session, *, email: str, display_name: str, role: str) -> User:
    # role must match DB constraint: REQUESTER|SUPPORT :contentReference[oaicite:6]{index=6}
    u = get_user_by_email(db, email)
    if u:
        return u
    u = User(email=email, display_name=display_name, role=role)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u

def create_ticket(db: Session, *, title: str, description: str, created_by_user_id):
    text = f"Title: {title}\nDescription: {description}"
    embedding = get_embedding(text)
    # Generate AI summary
    from app.agents.summarization_agent import SummarizationAgent
    from app.utils.llm import LLMClient
    llm = LLMClient()
    summarizer = SummarizationAgent(title, description)
    summary_result = summarizer.run(llm)
    ticket_summary = summary_result.get("summary", "No summary available.")
    t = Ticket(
        title=title,
        description=description,
        status="NEW",
        created_by=created_by_user_id,
        embedding=embedding,
        ticket_summary=ticket_summary,
    )
    db.add(t)
    db.commit()
    db.refresh(t)

    # Call InsightsBuddy to get recommended steps and similar tickets
    from app.agents.insights import InsightsBuddy
    insights = InsightsBuddy(db)
    analysis = insights.analyse_ticket(t.ticket_id)

    # Store similar tickets as JSON in outcome column
    outcome_value = [
        {
            "ticket_id": sim_ticket["ticket_id"],
            "title": sim_ticket["title"],
            "similarity": sim_ticket["similarity"]
        }
        for sim_ticket in analysis["similar_tickets"]
    ]

    # Use actual recommended steps and reasoning from InsightsBuddy
    recommendedsteps_list = analysis.get("recommended_steps", [])
    reasoning = None
    if recommendedsteps_list and isinstance(recommendedsteps_list, list):
        reasoning = recommendedsteps_list[0].get("reasoning")
    resolution = Resolution(
        ticket_id=t.ticket_id,
        resolution_text=None,
        recommendedsteps=recommendedsteps_list,
        root_cause=None,
        outcome=outcome_value,
        confidence_score=None,
        reasoning=reasoning,
        embedding=None,
        created_by=created_by_user_id,
    )
    db.add(resolution)
    db.commit()

    # Mark ticket as having resolutions
    t.has_resolution = True
    db.commit()

    return t

def list_tickets(
    db: Session,
    *,
    role: str,
    user_id,
    status: str | None = None,
    query: str | None = None,
):
    q = db.query(Ticket)
    if role == "REQUESTER":
        q = q.filter(Ticket.created_by == user_id)
    if status:
        q = q.filter(Ticket.status == status)
    if query:
        pattern = f"%{query.strip()}%"
        q = q.filter(
            or_(
                cast(Ticket.ticket_id, Text).ilike(pattern),
                Ticket.title.ilike(pattern),
                Ticket.description.ilike(pattern),
            )
        )
    tickets = q.order_by(Ticket.created_at.desc()).all()

    if not tickets:
        return tickets

    ticket_ids = [t.ticket_id for t in tickets]
    last_email_rows = (
        db.query(Email.ticket_id, func.max(Email.created_at))
        .filter(Email.ticket_id.in_(ticket_ids))
        .filter(Email.type == "APPROVED")
        .group_by(Email.ticket_id)
        .all()
    )
    last_email_map = {ticket_id: created_at for ticket_id, created_at in last_email_rows}

    now = datetime.now(timezone.utc)
    support_managers = {
        row.user_id for row in db.query(User.user_id).filter(User.role == "SUPPORT_MANAGER").all()
    }
    managers_by_support = {
        row.user_id: row.manager_id
        for row in db.query(User.user_id, User.manager_id)
        .filter(User.role == "SUPPORT")
        .all()
    }
    needs_commit = False

    for t in tickets:
        last_email_at = last_email_map.get(t.ticket_id)
        setattr(t, "last_email_at", last_email_at)

        if t.status == "RESOLVED":
            setattr(t, "next_update_due_at", None)
            setattr(t, "sla_status", "resolved")
            continue

        base_time = last_email_at or t.assigned_at
        if not base_time:
            setattr(t, "next_update_due_at", None)
            setattr(t, "sla_status", "pending")
            continue

        next_due = base_time + timedelta(hours=SLA_UPDATE_HOURS)
        setattr(t, "next_update_due_at", next_due)

        overdue = now > next_due
        setattr(t, "sla_status", "overdue" if overdue else "on_time")

        manager_base_time = t.escalated_manager1_at or t.escalated_manager2_at
        if manager_base_time:
            manager_due = manager_base_time + timedelta(hours=SLA_UPDATE_HOURS)
            setattr(t, "manager_next_update_due_at", manager_due)
            setattr(t, "manager_sla_status", "overdue" if now > manager_due else "on_time")
        else:
            setattr(t, "manager_next_update_due_at", None)
            setattr(t, "manager_sla_status", None)

        if overdue:
            manager_id = managers_by_support.get(t.assigned_to)
            if manager_id and manager_id in support_managers and not t.escalated_manager_id1:
                t.escalated_manager_id1 = manager_id
                t.escalated_manager1_at = now
                needs_commit = True

    if needs_commit:
        db.commit()

    return tickets

def get_ticket(db: Session, ticket_id):
    return db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()

def assign_ticket(db: Session, *, ticket_id, assigned_to_user_id):
    t = get_ticket(db, ticket_id)
    if not t:
        return None
    t.assigned_to = assigned_to_user_id
    t.assigned_at = datetime.now(timezone.utc)
    t.status = "ASSIGNED"
    db.commit()
    db.refresh(t)
    return t

def set_ticket_status(db: Session, *, ticket_id, status: str):
    if status not in ALLOWED_TICKET_STATUSES:
        raise ValueError(f"Invalid status. Allowed: {sorted(ALLOWED_TICKET_STATUSES)}")
    t = get_ticket(db, ticket_id)
    if not t:
        return None
    t.status = status
    db.commit()
    db.refresh(t)
    return t

# ---------------------------------------------------------------------------
# helpers for the resolutions table
def delete_resolution(db: Session, resolution_id):
    r = db.query(Resolution).filter(Resolution.resolution_id == resolution_id).first()
    if r:
        db.delete(r)
        db.commit()
        return True
    return False

def delete_all_resolutions(db: Session):
    db.query(Resolution).delete()
    db.commit()
    return True
from app.db.models.resolution import Resolution


def add_resolution(
    db: Session,
    ticket_id,
    resolution_text,
    created_by,
    root_cause=None,
    outcome=None,
    confidence_score=None,
    reasoning=None,
    total_similar_tickets_above70=None,
):
    # Generate embedding for new resolution
    from app.db.models.ticket import Ticket
    from app.utils.embeddings import get_embedding
    t = db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
    if t:
        text = f"Title: {t.title}\nDescription: {t.description}\nResolution: {resolution_text}"
    else:
        text = resolution_text
    embedding = get_embedding(text)
    # ENFORCE: If outcome is empty or has no similar_ticket_ids, do not store any recommended steps
    recommendedsteps = None
    if outcome and isinstance(outcome, list) and len(outcome) > 0:
        first = outcome[0]
        # Support both legacy and new keys
        similar_ids = first.get("similar_ticket_ids") or first.get("ids_above_70")
        if similar_ids and isinstance(similar_ids, list) and len(similar_ids) > 0:
            # Only allow recommendedsteps if there are similar tickets
            recommendedsteps = None  # Let caller set this if needed
        else:
            # No similar tickets, so no recommended steps
            recommendedsteps = []
    else:
        recommendedsteps = []
    r = Resolution(
        ticket_id=ticket_id,
        resolution_text=resolution_text,
        root_cause=root_cause,
        outcome=outcome,
        confidence_score=confidence_score,
        reasoning=reasoning,
        created_by=created_by,
        embedding=embedding,
        total_similar_tickets_above70=total_similar_tickets_above70,
        recommendedsteps=recommendedsteps,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def list_resolutions(db: Session, ticket_id=None):
    q = db.query(Resolution)
    if ticket_id:
        q = q.filter(Resolution.ticket_id == ticket_id)
    return q.order_by(Resolution.created_at.desc()).all()


def get_resolution(db: Session, resolution_id):
    return db.query(Resolution).filter(Resolution.resolution_id == resolution_id).first()