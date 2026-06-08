"""
Lightweight webhook receiver for ServiceNow.

Configure a Business Rule in ServiceNow (see backend/servicenow_sync/README.md)
to POST the new/updated incident's sys_id to this endpoint whenever a ticket is
inserted or updated. We then re-fetch the full record from ServiceNow (so we
always store complete, display-resolved data) and upsert it into Postgres.

Run with:
    uvicorn servicenow_sync.webhook:app --host 0.0.0.0 --port 8800
"""
import logging

from fastapi import FastAPI, Header, HTTPException, Request

from . import client, config, db

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("servicenow_webhook")

app = FastAPI(title="ServiceNow -> Postgres Webhook")


def _check_secret(x_webhook_secret):
    if not config.SERVICENOW_WEBHOOK_SECRET:
        return
    if x_webhook_secret != config.SERVICENOW_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/servicenow/webhook")
async def servicenow_webhook(request: Request, x_webhook_secret: str | None = Header(default=None)):
    _check_secret(x_webhook_secret)

    payload = await request.json()

    # Accept either {"sys_id": "..."} (preferred — we re-fetch the full record)
    # or a full record body {"sys_id": "...", "number": "...", ...}.
    sys_id = payload.get("sys_id")
    table = payload.get("table") or config.SERVICENOW_TABLE
    if not sys_id:
        raise HTTPException(status_code=400, detail="Missing sys_id in payload")

    record = client.fetch_record(table, sys_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Record {sys_id} not found in ServiceNow")

    db.upsert_ticket(record)
    logger.info("Upserted ticket %s (%s)", record.get("number"), sys_id)

    return {"status": "ok", "sys_id": sys_id, "number": record.get("number")}
