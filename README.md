# Quest — AI-Powered IT Support Platform

Quest is an AI-powered IT support ticket management system. It connects ServiceNow with a PostgreSQL database, provides AI-assisted ticket analysis and resolution, and automates incident notifications — all through a FastAPI backend and React frontend.

---

## What's Inside

| Component | Description |
|---|---|
| **Backend (FastAPI)** | REST API with AI agents, JWT auth, ticket management |
| **Frontend (React/Vite)** | Web UI for requesters, support staff, and managers |
| **ServiceNow Sync** | Pulls all incidents into Postgres and keeps them live-synced |
| **Incident Notification Workflow** | Auto-emails the right person and binds proof back to the ticket |
| **AI Agents** | InsightsBuddy (root cause analysis), CommCoach (email drafting), Web Search |

---

## Architecture

```
ServiceNow (cloud)
    │  Business Rule fires on every create/update
    ▼
Cloudflare Tunnel (public URL → localhost)
    │
    ▼
Webhook Receiver (FastAPI :8800)
    │  re-fetches full record from ServiceNow REST API
    ▼
PostgreSQL — servicenow_tickets database
    │
    ▼
Quest Backend (FastAPI :8000)  ←→  React Frontend (:5173)
    │
    ▼
Azure OpenAI (GPT-4) — ticket analysis, email drafting, web search
```

---

## Prerequisites

- Python 3.10+
- Node.js 18+
- Docker (for the pgvector database)
- A ServiceNow developer instance
- Azure OpenAI resource with a deployed model

---

## 1. Database Setup (Docker)

```bash
docker-compose up -d
```

This starts a PostgreSQL + pgvector container. Verify it's running:

```bash
docker ps
docker exec -it pgvector psql -U postgres -c "\l"
```

Run the schema (see full SQL in `backend/README.md`) to create:
- `support_ai` database — tickets, users, resolutions, AI audit log
- `servicenow_tickets` database — ServiceNow incident mirror

---

## 2. Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `backend/.env`:

```env
# Main database
DATABASE_URL=postgresql://user:password@localhost:5432/support_ai

# JWT
JWT_SECRET=your-secret-key
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=480

# Azure OpenAI
OPENAI_ENDPOINT=https://your-resource.openai.azure.com
OPENAI_API_KEY=your-api-key
LLM_MODEL=gpt-4.1
LLM_API_VERSION=2024-12-01-preview

# Bing Search (optional — falls back to DuckDuckGo if omitted)
BING_SEARCH_API_KEY=your-bing-key
BING_SEARCH_ENDPOINT=https://api.bing.microsoft.com/v7.0/search
```

Start the backend:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 3. Frontend Setup

```bash
cd backend/frontend
npm install
npm run dev
```

| Service | URL |
|---|---|
| Backend API | http://localhost:8000 |
| Frontend | http://localhost:5173 |
| API Docs | http://localhost:8000/docs |

---

## 4. ServiceNow Integration

### 4a. Sync all existing tickets (one-time backfill)

Create `backend/servicenow_sync/.env` (copy from `.env.example` and fill in your values):

```env
SERVICENOW_INSTANCE_URL=https://your-instance.service-now.com
SERVICENOW_USERNAME=admin
SERVICENOW_PASSWORD=your-password
SERVICENOW_WEBHOOK_SECRET=any-random-string

SN_PG_HOST=localhost
SN_PG_PORT=5432
SN_PG_DB=servicenow_tickets
SN_PG_USER=your-pg-user
SN_PG_PASSWORD=your-pg-password
```

Run the backfill:

```bash
cd backend
python -m servicenow_sync.backfill
```

This pulls every incident from ServiceNow into `servicenow_tickets`. Safe to re-run — uses upsert on `sys_id`.

### 4b. Start the real-time webhook receiver

```bash
cd backend
uvicorn servicenow_sync.webhook:app --host 0.0.0.0 --port 8800
```

### 4c. Start the self-healing tunnel

The webhook must be reachable from ServiceNow's cloud. This tunnel manager keeps a public URL alive and automatically updates the ServiceNow Business Rule if the URL changes:

```bash
cd backend
python -m servicenow_sync.tunnel_manager
```

### 4d. Run as persistent background services (macOS)

Both the webhook and tunnel manager are registered as launchd services that start on login and restart automatically if they crash:

```bash
launchctl load ~/Library/LaunchAgents/com.quest.servicenow-webhook.plist
launchctl load ~/Library/LaunchAgents/com.quest.servicenow-tunnel.plist
```

Check status:

```bash
launchctl list | grep quest
```

---

## 5. Incident Notification Workflow

A ServiceNow Business Rule ("Incident Notification Workflow") fires automatically on every incident create or update. It:

1. **Collects** the incident's number, description, priority, state, and category
2. **Decides** who to notify — the assigned person, or the caller if unassigned
3. **Queues an email** via ServiceNow's outbox (`sys_email`)
4. **Writes proof back** to the incident:
   - `Correlation ID` — sys_id of the queued email record
   - `Correlation display` — "Notified name@email.com @ timestamp"
   - `Work notes` — full audit entry in the ticket's activity log

No manual steps required — creating or updating a ticket triggers the entire chain automatically.

---

## 6. AI Agents

| Agent | What it does |
|---|---|
| **InsightsBuddy** | Analyzes a ticket, finds similar past resolutions using vector similarity, suggests root cause and fix steps |
| **CommCoach** | Drafts professional email responses to callers based on ticket context |
| **Web Search** | Searches the web for similar issues and extracts actionable resolution steps |
| **Summarization** | Summarizes long ticket threads and resolution histories |

All agents use Azure OpenAI (GPT-4) and log every call to the `ai_audit_log` table for traceability.

---

## Project Structure

```
Quest/
├── backend/
│   ├── app/
│   │   ├── agents/          # AI agent implementations
│   │   ├── api/             # FastAPI route handlers
│   │   ├── auth/            # JWT authentication
│   │   ├── db/              # Database models and connections
│   │   ├── schemas/         # Pydantic request/response models
│   │   ├── services/        # Business logic
│   │   └── main.py          # FastAPI app entrypoint
│   ├── servicenow_sync/     # ServiceNow → Postgres integration
│   │   ├── backfill.py      # Bulk import script
│   │   ├── client.py        # ServiceNow REST client
│   │   ├── config.py        # Config loader
│   │   ├── db.py            # Postgres upsert logic
│   │   ├── tunnel_manager.py# Self-healing Cloudflare tunnel
│   │   ├── webhook.py       # FastAPI webhook receiver
│   │   └── README.md        # Detailed setup guide
│   ├── frontend/            # React + Vite frontend
│   └── requirements.txt
├── Presenter_Script.md      # Speaker script for manager demo
├── Presenter_Script.docx    # Word version of the script
└── ServiceNow_Postgres_Sync_Presentation.pptx  # 17-slide deck
```

---

## Key SQL Queries

```sql
-- Count all synced tickets
SELECT COUNT(*) FROM servicenow_tickets;

-- Latest synced ticket
SELECT number, short_description, state, synced_at
FROM servicenow_tickets
ORDER BY synced_at DESC
LIMIT 1;

-- Tickets by priority
SELECT priority, COUNT(*) FROM servicenow_tickets GROUP BY priority ORDER BY priority;
```

---

## Troubleshooting

**Webhook not receiving events**
- Check the tunnel is running: `launchctl list | grep quest`
- Verify the Business Rule in ServiceNow points to the current tunnel URL
- Check logs: `tail -f backend/servicenow_sync/webhook.out.log`

**Tickets not appearing in the list after updating**
- The incident list may be filtered to "My Incidents" (caller = current user). Navigate to **Incident → All** in the ServiceNow left navigator to see all tickets.

**Business Rule disappeared after ServiceNow hibernation**
- Developer instances revert recent changes when they hibernate. Re-create the rule via the ServiceNow API — see `servicenow_sync/README.md` for the script.
