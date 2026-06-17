# Orchestration / Supervisor Agent (Day 4)

The supervisor sits between the ICM ticket system and the specialist agents. It
classifies each event, decides **which agents run and in what order**, tracks
each ticket through a state machine, handles the engineer's accept/reject, and
writes an audit trail. It does **not** route-to-team, diagnose, or recommend —
those are the sub-agents (Days 5–8).

## Quick start (no setup needed)

```powershell
cd backend
python -m app.orchestrator.demo            # watch the full flow end-to-end
python -m app.orchestrator.test_orchestrator   # run the tests
```

Both run with **no Postgres and no Redis** — they use an in-memory store, a mock
MCP client, and stub agents.

## Routing rules (which agents run)

| Event        | Pipeline                                   | Use case |
|--------------|--------------------------------------------|----------|
| `create`     | routing                                    | UC1      |
| `transfer`   | routing → diagnosis                        | UC2      |
| `reactivate` | routing → diagnosis → recommendation       | UC3      |

## State machine

```
INIT → ROUTING → DIAGNOSIS → RECOMMENDATION → DONE
                  (any) ------------------------> BLOCKED   (reject / error / timeout)
```

## Files → WBS tasks

| File | Task | Role |
|------|------|------|
| `events.py` | O-03 | classify the event (create/transfer/reactivate) |
| `states.py` | O-01, O-04 | pipelines + state definitions |
| `orchestrator.py` | O-04, O-09 | the supervisor: dispatch, state machine, accept/reject |
| `store.py` | O-04, O-05, O-11 | state + dedupe + context cache (in-memory or Redis) |
| `mcp_client.py` | O-05, O-08 | calls the MCP service (mocked for now) |
| `agents.py` | — | stub Routing/Diagnosis/Recommendation agents |
| `audit.py` | O-06 | audit logger (in-memory + optional DB sink) |
| `db_sink.py` | O-06 | writes audit to Postgres `ai_audit_log` |
| `../api/routers/orchestrator.py` | O-07, O-09 | FastAPI webhook + decision endpoints |
| `demo.py` / `test_orchestrator.py` | O-10, O-11 | end-to-end run + tests |

## Going from demo → production (config switches, no logic changes)

1. **Redis** — add to `backend/.env`:
   ```
   REDIS_URL=redis://localhost:6379/0
   ```
   (`docker-compose up` already starts a `redis` service.) The supervisor now
   persists state, dedupes events atomically, and caches context in Redis.

2. **Postgres audit** — already wired in the API router via `postgres_audit_sink`.
   ⚠️ The existing `ai_audit_log` table has a CHECK constraint limiting
   `agent_name` to `InsightsBuddy`/`CommCoach`. Widen it once:
   ```sql
   ALTER TABLE ai_audit_log DROP CONSTRAINT IF EXISTS ai_audit_log_agent_name_check;
   ALTER TABLE ai_audit_log ADD CONSTRAINT ai_audit_log_agent_name_check
     CHECK (agent_name IN ('InsightsBuddy','CommCoach',
                           'supervisor','routing','diagnosis','recommendation'));
   ```
   (Until then, audit writes fail silently — the pipeline keeps working.)

3. **Real agents** — replace the stubs in `agents.py` with the real Routing /
   Diagnosis / Recommendation agents. Each only needs `run(context) -> dict`.

4. **Real MCP service** — swap `MockMCPClient` for an HTTP client with the same
   method names once Day-3 lands.

## API endpoints

| Method | Path | Task | Purpose |
|--------|------|------|---------|
| POST | `/orchestrator/webhook` | O-07 | receive an ICM event, run the first agent |
| POST | `/orchestrator/decision` | O-09 | `{ticket_id, decision: accept\|reject}` |
| GET  | `/orchestrator/state/{ticket_id}` | — | inspect a ticket's pipeline state |
