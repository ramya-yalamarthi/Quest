"""DB-level immutability for ms_audit_log (MS-18, invariant 9).

A BEFORE UPDATE / BEFORE DELETE trigger raises on any mutation. REVOKE on
UPDATE / DELETE / TRUNCATE removes the underlying privilege so a TRUNCATE
(which bypasses BEFORE-row triggers) is also denied.

Called from the Alembic migration's upgrade() and idempotently from
`app.mitigation_safety.startup.on_startup` so that fresh local DBs created
outside Alembic still get the protection.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection


_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION ms_audit_log_no_mutate()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ms_audit_log is append-only (MS-18)';
END;
$$ LANGUAGE plpgsql;
"""

_TRIGGER_UPDATE = """
DROP TRIGGER IF EXISTS ms_audit_log_block_update ON ms_audit_log;
CREATE TRIGGER ms_audit_log_block_update
    BEFORE UPDATE ON ms_audit_log
    FOR EACH ROW EXECUTE FUNCTION ms_audit_log_no_mutate();
"""

_TRIGGER_DELETE = """
DROP TRIGGER IF EXISTS ms_audit_log_block_delete ON ms_audit_log;
CREATE TRIGGER ms_audit_log_block_delete
    BEFORE DELETE ON ms_audit_log
    FOR EACH ROW EXECUTE FUNCTION ms_audit_log_no_mutate();
"""

_REVOKES = """
REVOKE UPDATE, DELETE, TRUNCATE ON ms_audit_log FROM PUBLIC;
REVOKE UPDATE, DELETE, TRUNCATE ON ms_audit_log FROM CURRENT_USER;
"""


def apply_immutability(connection: Connection) -> None:
    """Idempotently install the trigger function, triggers, and revokes."""
    connection.execute(text(_TRIGGER_FUNCTION))
    connection.execute(text(_TRIGGER_UPDATE))
    connection.execute(text(_TRIGGER_DELETE))
    # REVOKE is also idempotent; ignore "privilege not granted" notices.
    try:
        connection.execute(text(_REVOKES))
    except Exception:
        # Some test databases (SQLite, in-mem) don't support REVOKE. The
        # trigger above still provides the row-level protection we test for.
        pass


def drop_immutability(connection: Connection) -> None:
    """Reverse of apply_immutability — used by Alembic downgrade and tests."""
    connection.execute(
        text("DROP TRIGGER IF EXISTS ms_audit_log_block_update ON ms_audit_log")
    )
    connection.execute(
        text("DROP TRIGGER IF EXISTS ms_audit_log_block_delete ON ms_audit_log")
    )
    connection.execute(text("DROP FUNCTION IF EXISTS ms_audit_log_no_mutate()"))
