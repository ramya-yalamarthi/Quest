# ServiceNow ↔ Orchestration Agent — Integration Guide

This guide is for the ServiceNow developer wiring the platform to the
Orchestration (Supervisor) Agent. Pair it with **`API.md`** (the endpoint
contract). You build three things: an **outbound trigger**, an **advisory
display**, and an **inbound decision** action.

---

## 0. Prerequisites

- The orchestrator is running and reachable from ServiceNow at a base URL, e.g.
  `http://<host>:8000` (locally `http://localhost:8000`; use a tunnel/deployed
  URL so ServiceNow can reach it — `localhost` on your laptop is not reachable
  from a ServiceNow instance).
- No auth in dev (a bearer token comes before UAT — build your REST step so a
  header is easy to add later).
- **Smoke test first:** from ServiceNow REST API Explorer (or curl), call
  `GET {base}/orchestrator/health` → expect `{"status":"ok"}`.

### Field mapping (ServiceNow incident → webhook body)
| ServiceNow field | API field | Notes |
|------------------|-----------|-------|
| `sys_id` | `ticket_id` | **use sys_id everywhere** (webhook, decision, state) |
| `sys_audit` id / generated GUID | `event_id` | unique per delivery — enables dedupe |
| (rule that fired) | `event_type` | `create` \| `transfer` \| `reactivate` |
| `priority` | `priority` | optional |
| `assignment_group` | `assigned_team` | optional |
| previous `assignment_group` | `previous_team` | on transfer |
| `reopen_count` | `reactivation_count` | on reactivation |
| `short_description` | `title` | optional |
| `description` | `description` | optional |

---

## 1. Outbound trigger — ServiceNow → `POST /orchestrator/webhook`

Create an **Outbound REST Message** and call it from **Business Rules** (or Flow
Designer) on the `incident` table.

### 1a. Outbound REST Message
- **System Web Services → Outbound → REST Message → New**
- Name: `OrchestratorWebhook`
- Endpoint: `{base}/orchestrator/webhook`
- HTTP Method `POST`, HTTP Header `Content-Type: application/json`

### 1b. Business Rules (three triggers)

| Rule | When | event_type |
|------|------|-----------|
| Create | `after insert` on incident | `create` |
| Transfer | `after update`, condition: `assignment_group` **changes** | `transfer` |
| Reactivate | `after update`, condition: state changes from Resolved/Closed → active (or `reopen_count` increases) | `reactivate` |

Recommended: run these **async** so ticket save isn't blocked.

### 1c. Example Business Rule script (transfer)
```javascript
(function executeRule(current, previous) {
  try {
    var body = {
      event_id: gs.generateGUID(),               // unique -> dedupe
      event_type: "transfer",
      ticket_id: current.getUniqueValue(),       // sys_id
      previous_team: previous.assignment_group.getDisplayValue(),
      assigned_team: current.assignment_group.getDisplayValue(),
      priority: current.priority.getDisplayValue(),
      title: current.short_description.toString(),
      description: current.description.toString()
    };

    var r = new sn_ws.RESTMessageV2('OrchestratorWebhook', 'post');
    r.setRequestBody(JSON.stringify(body));
    var resp = r.execute();
    var status = resp.getStatusCode();
    var out = JSON.parse(resp.getBody());

    if (status == 200 && out.advisories) {
      postAdvisory(current, out);                // see section 2
    } else {
      gs.warn('Orchestrator webhook non-200: ' + status + ' ' + resp.getBody());
    }
  } catch (e) {
    gs.error('Orchestrator webhook failed: ' + e);
  }
})(current, previous);
```
For the **create** and **reactivate** rules, copy this and change `event_type`
(and send `reactivation_count: current.reopen_count` for reactivate).

---

## 2. Display the advisory on the ticket

The webhook (and each decision) response contains:
```json
{ "state": "ROUTING", "current_agent": "routing",
  "advisories": [ { "agent": "...", "output": { "title": "...", ... } } ] }
```
Take the **last** advisory's `output` and write it as a **work note**, then show
**Accept / Reject** buttons (section 3).

### Example helper
```javascript
function postAdvisory(gr, out) {
  var adv = out.advisories[out.advisories.length - 1].output;
  var lines = [];
  lines.push('🤖 ' + (adv.title || 'AI advisory') + ' (agent: ' + out.current_agent + ')');
  for (var k in adv) {
    if (k === 'title') continue;
    lines.push('• ' + k + ': ' + adv[k]);
  }
  if (out.state === 'DONE') lines.push('✅ Pipeline complete.');
  gr.work_notes = lines.join('\n');
  gr.update();
}
```
Display whatever fields the agent returns (e.g. `recommended_team`,
`confidence`, `root_cause`, `immediate_action`). The shape is in `API.md`.

---

## 3. Inbound decision — `POST /orchestrator/decision`

Add two **UI Actions** (buttons) on the incident form: **Accept advisory** and
**Reject advisory**. Each calls `/decision`, then posts the next advisory.

### 3a. Outbound REST Message
- Name: `OrchestratorDecision`, endpoint `{base}/orchestrator/decision`, `POST`,
  `Content-Type: application/json`.

### 3b. UI Action script (Accept)
```javascript
(function () {
  var body = { ticket_id: current.getUniqueValue(), decision: "accept" };
  var r = new sn_ws.RESTMessageV2('OrchestratorDecision', 'post');
  r.setRequestBody(JSON.stringify(body));
  var resp = r.execute();
  if (resp.getStatusCode() == 200) {
    var out = JSON.parse(resp.getBody());
    postAdvisory(current, out);                  // posts next advisory or "DONE"
  } else {
    gs.addErrorMessage('Decision failed: ' + resp.getStatusCode());
  }
  action.setRedirectURL(current);
})();
```
For **Reject**, change `decision` to `"reject"` (the response will show
`state: "BLOCKED"`).

> Keep calling **Accept** to walk the pipeline: each accept returns the next
> agent's advisory until `state` is `DONE`.

---

## 4. The full loop

```
incident event ─► Business Rule ─► POST /webhook ─► advisory in work notes + [Accept][Reject]
                                                              │
                                                  engineer clicks Accept
                                                              ▼
                                          UI Action ─► POST /decision ─► next advisory
                                                              │
                                                        ... repeat ...
                                                              ▼
                                                     state = DONE  (or BLOCKED on Reject)
```

---

## 5. Testing checklist
1. `GET /orchestrator/health` returns ok (connectivity).
2. Create a test incident → confirm a work note advisory appears, `state=ROUTING`.
3. Click **Accept** → next advisory appears (or `DONE` for a create).
4. Reassign an incident → transfer advisory appears.
5. Reopen a resolved incident → reactivation pipeline (3 advisories).
6. Click **Reject** → note says blocked; no further advisories.
7. Fire the same event twice (same `event_id`) → second is ignored (no dupe).
8. `GET /orchestrator/state/{sys_id}` → matches what's on the ticket.

---

## 6. Gotchas
- **Reachability:** ServiceNow must be able to reach the base URL. `localhost`
  won't work from a hosted instance — use a deployed or tunneled URL.
- **Same id everywhere:** always use the incident `sys_id` as `ticket_id`.
- **Send `event_id`:** without it, retried deliveries can be mis-deduped.
- **Placeholder content:** advisory *values* are stubbed today; the request /
  response *shape* is final — build against it now.
- **Auth:** none yet; a `Authorization: Bearer <token>` header will be added
  before UAT — leave a spot for it in both REST Messages.
- **CORS:** these are server-to-server REST calls (no browser), so CORS doesn't
  apply to this integration.
