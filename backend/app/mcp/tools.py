from sqlalchemy.orm import Session
from app.db.models.user import User
from app.db.models.ticket import Ticket

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
    t = Ticket(title=title, description=description, status="NEW", created_by=created_by_user_id)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t

def list_tickets(db: Session, *, role: str, user_id, status: str | None = None):
    q = db.query(Ticket)
    if role == "REQUESTER":
        q = q.filter(Ticket.created_by == user_id)
    if status:
        q = q.filter(Ticket.status == status)
    return q.order_by(Ticket.created_at.desc()).all()

def get_ticket(db: Session, ticket_id):
    return db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()

def assign_ticket(db: Session, *, ticket_id, assigned_to_user_id):
    t = get_ticket(db, ticket_id)
    if not t:
        return None
    t.assigned_to = assigned_to_user_id
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