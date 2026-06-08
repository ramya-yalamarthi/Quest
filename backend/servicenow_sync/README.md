# ServiceNow → Postgres sync

Pulls tickets from the ServiceNow `incident` table into a standalone local
Postgres database (`servicenow_tickets`, owned by `yaswanthg`), and keeps it
updated automatically via a webhook that ServiceNow calls whenever a ticket is
created or changed.

## 1. One-time setup

```bash
cd backend
cp servicenow_sync/.env.example servicenow_sync/.env
# edit servicenow_sync/.env: fill in SERVICENOW_PASSWORD and pick a
# SERVICENOW_WEBHOOK_SECRET (any random string — it must match the Business
# Rule script in step 4)
pip install -r requirements.txt   # psycopg2, requests, fastapi, uvicorn already listed
```

The `servicenow_tickets` database and table are already created (see
`schema.sql` if you need to recreate them elsewhere):

```sql
CREATE TABLE servicenow_tickets (
    id SERIAL PRIMARY KEY,
    sys_id TEXT UNIQUE NOT NULL,
    number TEXT,
    short_description TEXT,
    description TEXT,
    state TEXT,
    priority TEXT,
    urgency TEXT,
    impact TEXT,
    category TEXT,
    assignment_group TEXT,
    assigned_to TEXT,
    opened_by TEXT,
    caller_id TEXT,
    opened_at TIMESTAMPTZ,
    sys_created_on TIMESTAMPTZ,
    sys_updated_on TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    raw JSONB,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## 2. Pull in everything that already exists

```bash
cd backend
python -m servicenow_sync.backfill
```

This pages through every record in the ServiceNow `incident` table and
upserts it (matched on `sys_id`, so re-running is safe / idempotent).

## 3. Run the webhook receiver

```bash
cd backend
uvicorn servicenow_sync.webhook:app --host 0.0.0.0 --port 8800
```

It exposes `POST /servicenow/webhook`. ServiceNow will call this with
`{"sys_id": "...", "table": "incident"}`; the receiver re-fetches the full
record from ServiceNow (so stored data is always complete and uses resolved
display values) and upserts it.

**ServiceNow's cloud instance cannot reach `localhost` on your machine.** To
let it call your webhook you need a public URL. Easiest option — a tunnel:

```bash
ngrok http 8800
# copy the https://xxxx.ngrok-free.app URL it prints
```

Use `https://xxxx.ngrok-free.app/servicenow/webhook` as the endpoint in the
Business Rule below. (For a permanent setup, deploy the webhook receiver
somewhere with a stable public URL instead of relying on a tunnel.)

## 4. Configure the ServiceNow Business Rule (push on every insert/update)

In ServiceNow: **System Definition → Business Rules → New**

| Field | Value |
|---|---|
| Name | `Sync incident to Postgres` |
| Table | `Incident [incident]` |
| When to run → When | `after` |
| When to run → Insert | ✅ |
| When to run → Update | ✅ |
| Advanced | ✅ |

Paste this into the **Script** field (replace the endpoint URL and secret with
your own values from `.env`):

```javascript
(function executeRule(current, previous /*null when async*/) {
    try {
        var r = new sn_ws.RESTMessageV2();
        r.setEndpoint('https://xxxx.ngrok-free.app/servicenow/webhook');
        r.setHttpMethod('POST');
        r.setRequestHeader('Content-Type', 'application/json');
        r.setRequestHeader('X-Webhook-Secret', 'change_me_too'); // must match SERVICENOW_WEBHOOK_SECRET
        r.setRequestBody(JSON.stringify({
            sys_id: current.sys_id.toString(),
            table: current.getTableName(),
            number: current.getValue('number')
        }));
        r.executeAsync(); // fire-and-forget so the user's save isn't slowed down
    } catch (ex) {
        gs.error('Postgres sync webhook failed: ' + ex.message);
    }
})(current, previous);
```

Save it. From now on, every time a ticket (incident) is created or updated in
ServiceNow, this rule fires, posts the `sys_id` to your webhook, and the
webhook fetches the latest version of that record and upserts it into
`servicenow_tickets` — no manual step required.

## Notes / things you may want to adjust later

- This syncs the `incident` table by default. If your tickets live in a
  different table (e.g. a custom table, or `sc_request`/`sc_task`), change
  `SERVICENOW_TABLE` in `.env` and update the Business Rule's **Table** field
  and `setEndpoint`/script accordingly.
- The webhook re-fetches the record rather than trusting the Business Rule's
  inline payload — this keeps stored data consistent with what backfill
  produces and avoids trusting client-supplied field values.
- `raw` stores the full ServiceNow JSON record (JSONB) in case you need fields
  beyond the ones broken out into columns.
- Re-running the backfill is always safe — it's an upsert keyed on `sys_id`.
