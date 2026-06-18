"""MS-18, invariant 9: ms_audit_log is append-only.

In production this is enforced by a Postgres BEFORE UPDATE/DELETE trigger.
In these unit tests we use SQLite, where the same protection is provided by
a SQLAlchemy `before_flush` listener installed in conftest.
"""

import uuid

import pytest
import sqlalchemy as sa

from app.mitigation_safety.audit.service import MitigationAuditLogger
from app.mitigation_safety.audit.reconstruct import by_action_id, by_ticket_id


def _record_one(db, action_id=None, ticket_id=None, transition_type="state"):
    audit = MitigationAuditLogger(db)
    return audit.record(
        action_id=action_id or uuid.uuid4(),
        ticket_id=ticket_id,
        actor="human:42",
        transition_type=transition_type,
        from_state="DRAFTED",
        to_state="APPROVED",
        detail={"note": "test"},
    )


def test_insert_works(db):
    row = _record_one(db)
    db.commit()
    assert row.audit_id is not None


def test_update_rejected(db):
    row = _record_one(db)
    db.commit()
    # Try to mutate.
    row.actor = "human:99"
    db.add(row)
    with pytest.raises(sa.exc.IntegrityError):
        db.flush()
    db.rollback()


def test_delete_rejected(db):
    row = _record_one(db)
    db.commit()
    db.delete(row)
    with pytest.raises(sa.exc.IntegrityError):
        db.flush()
    db.rollback()


def test_reconstruct_by_action_returns_in_time_order(db):
    aid = uuid.uuid4()
    _record_one(db, action_id=aid, transition_type="state")
    _record_one(db, action_id=aid, transition_type="safe_mode")
    db.commit()
    rows = by_action_id(db, aid)
    assert len(rows) == 2
    assert rows[0].ts <= rows[1].ts


def test_reconstruct_by_ticket(db):
    tid = uuid.uuid4()
    _record_one(db, ticket_id=tid)
    _record_one(db, ticket_id=tid)
    db.commit()
    rows = by_ticket_id(db, tid)
    assert len(rows) == 2
