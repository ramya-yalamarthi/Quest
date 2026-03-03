from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, cast, Text
from app.db.models.user import User
from app.db.models.ticket import Ticket
from app.db.models.email import Email
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
    t = Ticket(
        title=title,
        description=description,
        status="NEW",
        created_by=created_by_user_id,
        embedding=embedding,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
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
    manager_ids = [
        row[0]
        for row in (
            db.query(User.user_id)
            .filter(User.role == "MANAGER")
            .order_by(User.created_at.asc())
            .limit(2)
            .all()
        )
    ]
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

        next_due = base_time + timedelta(hours=2)
        setattr(t, "next_update_due_at", next_due)

        overdue = now > next_due
        setattr(t, "sla_status", "overdue" if overdue else "on_time")

        if overdue and manager_ids:
            if len(manager_ids) >= 1 and not t.escalated_manager_id1:
                t.escalated_manager_id1 = manager_ids[0]
                t.escalated_manager1_at = now
                needs_commit = True
            if len(manager_ids) >= 2 and not t.escalated_manager_id2:
                t.escalated_manager_id2 = manager_ids[1]
                t.escalated_manager2_at = now
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
    is_final=True,
    is_kb=False,
):
    r = Resolution(
        ticket_id=ticket_id,
        resolution_text=resolution_text,
        root_cause=root_cause,
        outcome=outcome,
        confidence_score=confidence_score,
        reasoning=reasoning,
        is_final=is_final,
        is_kb=is_kb,
        created_by=created_by,
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