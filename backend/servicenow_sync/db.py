import json
import psycopg2
import psycopg2.extras

from . import config

# Maps our column names to ServiceNow field names. ServiceNow reference fields
# (assigned_to, opened_by, caller_id, assignment_group) come back as either a
# plain string or a {"display_value": ..., "value": ...} dict depending on the
# `sysparm_display_value` query option, so we normalize on read.
FIELD_MAP = {
    "sys_id": "sys_id",
    "number": "number",
    "short_description": "short_description",
    "description": "description",
    "state": "state",
    "priority": "priority",
    "urgency": "urgency",
    "impact": "impact",
    "category": "category",
    "assignment_group": "assignment_group",
    "assigned_to": "assigned_to",
    "opened_by": "opened_by",
    "caller_id": "caller_id",
    "opened_at": "opened_at",
    "sys_created_on": "sys_created_on",
    "sys_updated_on": "sys_updated_on",
    "closed_at": "closed_at",
}

UPSERT_SQL = """
INSERT INTO servicenow_tickets (
    sys_id, number, short_description, description, state, priority, urgency,
    impact, category, assignment_group, assigned_to, opened_by, caller_id,
    opened_at, sys_created_on, sys_updated_on, closed_at, raw, synced_at
) VALUES (
    %(sys_id)s, %(number)s, %(short_description)s, %(description)s, %(state)s,
    %(priority)s, %(urgency)s, %(impact)s, %(category)s, %(assignment_group)s,
    %(assigned_to)s, %(opened_by)s, %(caller_id)s, %(opened_at)s,
    %(sys_created_on)s, %(sys_updated_on)s, %(closed_at)s, %(raw)s, now()
)
ON CONFLICT (sys_id) DO UPDATE SET
    number = EXCLUDED.number,
    short_description = EXCLUDED.short_description,
    description = EXCLUDED.description,
    state = EXCLUDED.state,
    priority = EXCLUDED.priority,
    urgency = EXCLUDED.urgency,
    impact = EXCLUDED.impact,
    category = EXCLUDED.category,
    assignment_group = EXCLUDED.assignment_group,
    assigned_to = EXCLUDED.assigned_to,
    opened_by = EXCLUDED.opened_by,
    caller_id = EXCLUDED.caller_id,
    opened_at = EXCLUDED.opened_at,
    sys_created_on = EXCLUDED.sys_created_on,
    sys_updated_on = EXCLUDED.sys_updated_on,
    closed_at = EXCLUDED.closed_at,
    raw = EXCLUDED.raw,
    synced_at = now();
"""


def get_connection():
    return psycopg2.connect(
        host=config.SN_PG_HOST,
        port=config.SN_PG_PORT,
        dbname=config.SN_PG_DB,
        user=config.SN_PG_USER,
        password=config.SN_PG_PASSWORD,
    )


def _field_value(raw_record, field_name):
    """ServiceNow reference/choice fields may be a dict {value, display_value}."""
    value = raw_record.get(field_name)
    if isinstance(value, dict):
        return value.get("display_value") or value.get("value") or None
    return value or None


def normalize_record(raw_record):
    row = {our_col: _field_value(raw_record, sn_field) for our_col, sn_field in FIELD_MAP.items()}
    row["raw"] = json.dumps(raw_record)
    return row


def upsert_tickets(records):
    """records: iterable of raw ServiceNow incident dicts. Returns count upserted."""
    rows = [normalize_record(r) for r in records]
    if not rows:
        return 0

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(cur, UPSERT_SQL, rows)
        return len(rows)
    finally:
        conn.close()


def upsert_ticket(record):
    return upsert_tickets([record])
