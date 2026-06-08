# Orchestration Agent — API Contract

For the ServiceNow / D365 integration. This is the interface the Orchestration
(Supervisor) Agent exposes. Your integration only needs these endpoints.

- **Base URL (local/dev):** `http://localhost:8000`
- **Content type:** `application/json`
- **Auth:** none yet (dev). A bearer token will be added before UAT — see "Auth" below.
- **Interactive docs:** `http://localhost:8000/docs` (Swagger) · machine spec at `/openapi.json`

---

## The flow in one picture

```
ServiceNow ticket event (create / transfer / reactivate)
        │  POST /orchestrator/webhook
        ▼
  Orchestration Agent  ──► runs the right sub-agent(s)
        │  returns an "advisory" in the response
        ▼
ServiceNow posts the advisory as a ticket comment
        │  engineer clicks Accept / Reject
        ▼
        │  POST /orchestrator/decision
        ▼
  Orchestration Agent  ──► Accept = run next agent · Reject = stop + flag
```

Two calls drive everything: **`/webhook`** (an event happened) and
**`/decision`** (the engineer responded).

---

## 1. POST `/orchestrator/webhook`

Call this whenever a ticket is **created**, **transferred**, or **reactivated**.

### Request body
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `ticket_id` | string | ✅ | ServiceNow sys_id or ticket number |
| `event_id` | string | recommended | Unique id of THIS delivery. Used to ignore duplicate webhooks. Use the ServiceNow event/sys_audit id. |
| `event_type` | string | optional | `create` \| `transfer` \| `reactivate`. If omitted, it's inferred (see below). |
| `priority` | string | optional | e.g. `P1` |
| `assigned_team` | string | optional | currently assigned team |
| `previous_team` | string | optional | prior team — presence implies a transfer |
| `reactivation_count` | int | optional | times reopened — `>0` implies a reactivation |
| `title` | string | optional | ticket short description |
| `description` | string | optional | ticket full text |
| `severity` / `status` | string | optional | passed through to the agents |

> Any **extra** fields you send are accepted and forwarded to the agents as
> context — you won't get a validation error for sending more than this.

**If `event_type` is omitted, it's inferred:** `reactivation_count > 0` →
`reactivate`; else `previous_team` present → `transfer`; else `create`.

### Example
```bash
curl -X POST http://localhost:8000/orchestrator/webhook \
  -H "Content-Type: application/json" \
  -d '{
        "event_id": "evt-8842",
        "event_type": "transfer",
        "ticket_id": "INC0012345",
        "previous_team": "Networking",
        "assigned_team": "Storage",
        "priority": "P2",
        "title": "Latency spike in East-US"
      }'
```

### Response  (`200 OK`)
```json
{
  "ticket_id": "INC0012345",
  "event_type": "transfer",
  "pipeline": ["routing", "diagnosis"],
  "current_agent": "routing",
  "state": "ROUTING",
  "advisories": [
    {
      "agent": "routing",
      "output": {
        "title": "Team routing advisory",
        "recommended_team": "Storage",
        "mismatch": false,
        "confidence": 0.89,
        "evidence": "2 highly-similar past tickets resolved by Storage."
      }
    }
  ],
  "status_detail": ""
}
```
**What to do with it:** post the latest `advisories[-1].output` onto the ticket
as a comment, with Accept / Reject buttons.

### Duplicate delivery
If the same `event_id` is sent again, the response is:
```json
{ "status": "ignored", "detail": "duplicate or unknown event" }
```
Safe to ignore — the event was already processed (idempotent).

---

## 2. POST `/orchestrator/decision`

Call this when the engineer clicks **Accept** or **Reject** on an advisory.

### Request body
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `ticket_id` | string | ✅ | the ticket being responded to |
| `decision` | string | ✅ | `accept` or `reject` |

### Example
```bash
curl -X POST http://localhost:8000/orchestrator/decision \
  -H "Content-Type: application/json" \
  -d '{ "ticket_id": "INC0012345", "decision": "accept" }'
```

### Behaviour
- **accept** → the next agent in the pipeline runs; the response contains its new
  advisory (post it as the next comment). When the pipeline finishes, `state` is `DONE`.
- **reject** → the pipeline stops, `state` becomes `BLOCKED`, and the override is
  logged + flagged for model retraining.

### Errors
| Code | Meaning |
|------|---------|
| `404` | No orchestration state for that ticket (no prior webhook) |
| `400` | `decision` wasn't `accept` or `reject` |

---

## 3. GET `/orchestrator/state/{ticket_id}`

Inspect where a ticket currently is. Returns the same shape as the webhook
response. `404` if the ticket was never seen. Useful for debugging / a status panel.

---

## 4. GET `/orchestrator/health`

Liveness check. Returns `{ "status": "ok", "service": "orchestrator" }`.
Use it to confirm connectivity from ServiceNow.

---

## State values you'll see in `state`
`INIT` → `ROUTING` → `DIAGNOSIS` → `RECOMMENDATION` → `DONE`, or `BLOCKED`
(on reject / error). `current_agent` tells you which agent just posted.

## Which agents run per event (`pipeline`)
| event_type | pipeline |
|------------|----------|
| create | `["routing"]` |
| transfer | `["routing","diagnosis"]` |
| reactivate | `["routing","diagnosis","recommendation"]` |

---

## ServiceNow integration checklist (for you)
1. **Outbound (ServiceNow → us):** add a Business Rule / Flow that fires on
   incident create, team change (transfer), and reopen (reactivate), and does a
   REST POST to `/orchestrator/webhook` with the fields above. Send a stable
   `event_id` so retries don't double-process.
2. **Display:** write `advisories[-1].output` to the ticket as a work note /
   comment, with Accept and Reject actions.
3. **Inbound (engineer → us):** Accept/Reject calls `/orchestrator/decision`,
   then post the returned next advisory (if any).

## Auth (coming before UAT)
Endpoints are open in dev. The plan is a bearer token (`Authorization: Bearer <token>`)
matching the rest of the API. I'll share the token + header once it's enabled —
build your REST step so the header is easy to add.

## Notes
- **Idempotent:** resending the same `event_id` is safe (deduped).
- **Mocked internals:** today the agents and ticket-data lookups are stubs, so
  advisory *content* is placeholder — but the **API shape is final**. Build
  against it now; the responses get real as the sub-agents land.
