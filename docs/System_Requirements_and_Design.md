# AI Support Agent for Dynamics 365 Customer Service — System Requirements & Design

This supersedes the POC description in [`AI_Support_Agent_Architecture.md`](AI_Support_Agent_Architecture.md), which
described the no-database, poller-based MVP. The system has since grown a persistence layer, an MCP-based
reasoning engine, and a guarded auto-remediation path.

---

## 1. System Requirements

### 1.1 Purpose
Automatically triage Dynamics 365 / ServiceNow support cases (currently scoped to Kubernetes / Karpenter
infrastructure issues): assign the right team, diagnose root cause against historical precedent, recommend a
fix, and — for low-risk, high-confidence cases — safely auto-remediate.

### 1.2 Functional requirements

| ID | Requirement |
|----|---|
| FR-1 | Ingest case-lifecycle events (created / assigned / reactivated) from D365 or ServiceNow via webhook. |
| FR-2 | Deduplicate repeated/duplicate webhook deliveries for the same event. |
| FR-3 | Route each case to the correct support team, with a confidence score and rationale. |
| FR-4 | Diagnose root cause, grounded in similar historically-resolved cases (not generic/hallucinated text). |
| FR-5 | Recommend a hot fix (restore-now) and an ultimate fix (permanent), with verified reference links from a trusted-domain allowlist only. |
| FR-6 | Compose the above into a single note and write it back onto the case (or expose it via API for a pop-up UI). |
| FR-7 | Accept engineer feedback (👍/👎 + optional comment) and regenerate an improved answer on 👎. |
| FR-8 | For cases that clear a confidence + precedent-match safety gate, attempt automatic remediation via a runbook. |
| FR-9 | Verify the remediation outcome; on failure, automatically revert and escalate to a human — never leave a failed auto-fix silently applied. |
| FR-10 | Disable auto-remediation system-wide (kill switch) after repeated remediation failures within a rolling window, until manually reset. |
| FR-11 | Record every agent decision (input, output, confidence, supporting case IDs) to an audit log. |
| FR-12 | Support switching the reasoning engine (direct LLM-orchestrated vs. MCP tool-call-mediated) via configuration, with automatic fallback if the MCP path is unavailable. |
| FR-13 | Allow runbooks and trusted reference domains to be edited without a code change or redeploy. |

### 1.3 Non-functional requirements

| ID | Requirement |
|----|---|
| NFR-1 | **Resilience** — a failure in any one pipeline stage (similarity, routing, diagnosis, recommendation, DB, Redis) degrades that stage gracefully rather than aborting the case. |
| NFR-2 | **Latency** — case → recommendation within roughly 30–60s end to end. |
| NFR-3 | **Safety over automation** — when in doubt (low confidence, no precedent, irreversible action), the system must suggest rather than act. |
| NFR-4 | **Auditability** — every automated decision and every auto-remediation attempt must be traceable after the fact. |
| NFR-5 | **Deployability** — the orchestrator-only surface must be runnable without the heavier ML dependencies (torch, sentence-transformers) for low-cost hosting (Render). |
| NFR-6 | **Statelessness option** — the system must keep working (without persistence/dedupe) if Postgres/Redis are not provisioned, for low-friction environments. |
| NFR-7 | **Configurability without redeploy** — thresholds (confidence, kill-switch trip count/window) and content (runbooks, trusted domains) live in env vars / JSON config, not code. |

### 1.4 Constraints
- D365 case notes/descriptions are capped at 2000 characters; imported content must be truncated to ~1990 to leave room for formatting.
- Reference links must come from a trusted-domain allowlist (no arbitrary search results).
- Auto-remediation is currently limited to reversible, Tier-A runbooks (e.g., account lockout reset, hung-service restart) — not arbitrary infrastructure changes.

---

## 2. System Design

### 2.1 High-level architecture

```
 ┌───────────────────────────────────────────────────────────────────────────┐
 │                  DYNAMICS 365 / ServiceNow — system of record              │
 │        Cases  •  AI note on timeline  •  pop-up (👍/👎)                   │
 └──────────────▲───────────────────────────────────────────────▲────────────┘
                │ webhook: case created/assigned/reactivated     │ note / pop-up
                │                                                │
 ┌──────────────┴────────────────────────────────────────────────┴────────────┐
 │                     ORCHESTRATOR  (FastAPI, backend/app)                   │
 │                                                                            │
 │  /orchestrator/d365-webhook → Orchestrator.handle_event()                 │
 │        │                                                                  │
 │        ▼                                                                  │
 │  Engine selector (ENGINE env: legacy | mcp) ── safe fallback to legacy    │
 │        │                                                                  │
 │        ▼                                                                  │
 │  Pipeline: Routing → Diagnosis → Recommendation → Mitigation              │
 │        │                              │                                  │
 │        │                              ▼                                  │
 │        │                    Safety gate → kill-switch check →            │
 │        │                    simulate fix → verify → revert-if-failed     │
 │        ▼                                                                  │
 │  Note composer → write-back + /feedback (👍/👎 → regenerate)             │
 │                                                                            │
 │  Audit sink → ai_audit_log (Postgres, best-effort)                       │
 └───┬─────────────────────────┬─────────────────────────────┬──────────────┘
     │ legacy path:            │ mcp path: JSON-RPC           │ state / dedupe
     │ direct LLM calls        │ tool calls over stdio/HTTP    │ / context cache
     ▼                         ▼                               ▼
 ┌─────────────┐      ┌─────────────────────────┐      ┌────────────────┐
 │ Azure OpenAI │      │ MCP servers:             │      │ Redis (optional)│
 │ gpt-4o +     │      │  reasoning (8104)        │      │ in-memory       │
 │ embeddings   │      │  knowledge (8102)        │      │ fallback        │
 └─────────────┘      │  remediation (8103)      │      └────────────────┘
                       │  dataverse (placeholder) │
                       └─────────────────────────┘
                                  │
                                  ▼
                       ┌─────────────────────────┐
                       │ Postgres + pgvector       │
                       │ tickets / resolutions /   │
                       │ feedback / audit log       │
                       └─────────────────────────┘
```

### 2.2 Component design

**Engine selector** (`backend/app/orchestrator/engine.py`)
Reads `ENGINE` (default `legacy`). `mcp` routes reasoning calls through the MCP client/server boundary;
`legacy` calls the agents in-process. Both paths funnel through the *same* `d365_runner.process_case`, so
output shape, gating, and note formatting never diverge between engines — only how each agent's answer is
produced differs.

**Agents** (`backend/app/agents/`)
- *Routing* (`communication.py`) — team assignment + reassignment detection.
- *Diagnosis* (`insights.py`) — root cause, grounded in nearest historical cases via similarity search.
- *Recommendation* (`web_solutions_agent.py`) — hot fix / ultimate fix + reference links filtered against `trusted_domains.json`.
- *Summarization* (`summarization_agent.py`) — note formatting helpers.

**MCP layer** (`backend/app/mcp_servers/`, `backend/app/mcp_client/`)
Each agent capability is also exposed as an MCP tool (`route_case`, `diagnose_case`, `recommend_case`,
`search_docs`, `list_runbooks`, `match_runbook`, `assess_remediation`, `run_runbook`). The MCP client wraps
these as drop-in agent replacements (`_MCPToolAgent`), so the orchestrator code is agent-shape-agnostic.

**Mitigation / safety net** (`backend/app/orchestrator/mitigation.py`, `auto_safety.py`)
1. **Safety gate**: blended confidence ≥ `MITIGATION_CONF_MIN` (default 0.85) AND precedent match ≥
   `MITIGATION_MATCH_MIN` (default 0.80) AND runbook tier A AND reversible.
2. **Kill-switch check**: `auto_safety.is_enabled()` — disabled after `AUTO_KILL_THRESHOLD` reverts
   (default 3) within `AUTO_KILL_WINDOW_SEC` (default 3600s).
3. **Execute** (simulated today) → **verify** → on failure, **revert** via the runbook's undo steps and
   escalate; on success, mark `auto_resolved`.
4. Outcomes: `suggest_only`, `auto_off`, `auto_resolved`, `reverted_escalated` — always one of these, never silent.

**Config** (`backend/config/runbooks.json`, `backend/config/trusted_domains.json`, `appconfig.py`)
Runbooks and the reference-link allowlist are data, not code, with hardcoded fallbacks if the files are
missing. Numeric thresholds stay in env vars (`appconfig.py` reads with defaults).

**Persistence** (`backend/app/db/`)
Postgres (pgvector extension) holds `tickets`, `resolutions`, `recommendation_feedback`, `users`, `email`,
and `ai_audit_log`. All writes are best-effort — a DB outage degrades the system to "works, but no
audit/persistence" rather than failing the case.

**State store**
Redis backs event dedupe and the orchestrator's per-case state machine when `REDIS_URL` is set; an in-memory
dict is the fallback (state lost on restart, no cross-instance dedupe).

**API surface** (`backend/app/api/routers/`)
`orchestrator.py` (`/d365-webhook`, `/feedback`, `/health`, state/decision lookups), `mcp.py` (tool registry
for external callers), `tickets.py` / `resolutions.py` / `users.py` (corpus CRUD), `auth.py` (JWT).

**Deployment shapes**
- Full app (`backend/app/main.py`) — all routers, ML deps (`requirements.txt`).
- Orchestrator-only (`backend/orchestrator_server.py`, `requirements-orchestrator.txt`) — slim deploy
  (no torch/sentence-transformers) for low-cost hosting; same orchestrator router, optional DB.
- MCP servers can run in-process (default) or as standalone processes (`mcp-service/main.py`, ports
  8102–8104) for out-of-process tool isolation.

### 2.3 Data flow (case → outcome)
1. D365/ServiceNow webhook → `/orchestrator/d365-webhook`.
2. Dedupe (Redis or in-memory) → event classified (created/assigned/reactivated).
3. Engine selected → Routing → Diagnosis (similarity search against `resolutions`) → Recommendation
   (reference links checked against allowlist).
4. Mitigation evaluates the safety gate; if it passes and the kill switch is off, simulate-execute → verify
   → revert-if-failed.
5. Note composed from all four agent outputs → written back to the case / served to the pop-up.
6. Every step's input/output/confidence persisted to `ai_audit_log` (best-effort).
7. Engineer feedback (👍/👎) → `/feedback`; 👎 triggers regeneration with the engineer's comment as added context.

### 2.4 Key design decisions and why
- **Dual engine with identical downstream logic** — lets MCP be adopted incrementally and rolled back
  instantly (env flag) without risking behavioral drift between the two paths.
- **Config externalized, thresholds in env** — runbooks/domains change often (ops content); thresholds are
  safety-critical and should be visible in deploy config, not buried in JSON.
- **Verify-then-revert rather than verify-then-trust** — auto-remediation is judged by its own kill switch,
  not by the confidence score that admitted it, since a confident wrong fix is exactly the failure mode the
  net exists to catch.
- **Best-effort persistence** — the case pipeline is the product; the audit trail is valuable but must never
  be a single point of failure for case handling.

### 2.5 Known gaps / not yet implemented
- `dataverse_server.py` and `connectors.py` are Phase-3 placeholders — real Dataverse/Graph/Defender API
  calls are not wired up yet; remediation execution is simulated.
- `backend/app/services/` is empty — no custom services beyond agents/orchestrator yet.
- `tests/test_basic.py` is a placeholder; real coverage lives in `backend/app/orchestrator/test_orchestrator.py`.
