"""
Standalone Orchestration Agent server -- for the ServiceNow integration.

Runs ONLY the orchestrator endpoints, so it starts fast and needs no ML deps
and no live database (audit DB writes fail silently; state is in-memory unless
REDIS_URL is set). Perfect for your teammate to wire ServiceNow against.

Run it:
    cd backend
    uvicorn orchestrator_server:app --host 0.0.0.0 --port 8000

Then expose it so ServiceNow can reach it:
    ngrok http 8000      # gives a public https URL

Endpoints (see app/orchestrator/API.md):
    GET  /orchestrator/health
    POST /orchestrator/webhook
    POST /orchestrator/decision
    GET  /orchestrator/state/{ticket_id}
    GET  /docs            <- interactive Swagger UI
"""

import os

# The orchestrator router pulls in the DB layer for the audit sink. Provide a
# DATABASE_URL so imports succeed; if no Postgres is running, audit writes fail
# silently (by design) and the endpoints still work. Set a real one (and run
# the ai_audit_log ALTER) when you want the audit trail persisted.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/support_ai"
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.orchestrator import router as orchestrator_router

app = FastAPI(title="Orchestration Agent API", version="0.1.0")

# ServiceNow calls are server-to-server (CORS doesn't apply), but allow all so a
# browser-based tester / Swagger from any host also works.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(orchestrator_router)


@app.get("/")
def root():
    return {"service": "orchestration-agent", "docs": "/docs", "base": "/orchestrator"}
