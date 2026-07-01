# Quest — AI Support Agent: Architecture Design

> **System:** AI Support Agent for Dynamics 365 / ServiceNow — automated triage, diagnosis, recommendation, and guarded auto‑remediation of support cases.
> **Scope of this document:** the full technical architecture — system context, component design, data model, control/data flow, the dual reasoning engine, the MCP tool layer, the safety net, deployment topology, and the design decisions behind them.

---

## 1. Executive summary

When a support Case is created (or transferred / reactivated) in **Dynamics 365** or **ServiceNow**, Quest automatically:

1. **Routes** it to the right support team and picks an available, skill‑matched, on‑shift engineer.
2. **Diagnoses** the root cause, grounded in the closest *historically resolved* cases (semantic similarity, not generic text).
3. **Recommends** a **Hot Fix** (restore now) and an **Ultimate Fix** (permanent), with reference links restricted to a trusted‑domain allowlist.
4. Optionally, for **low‑risk, high‑confidence** cases, attempts **guarded auto‑remediation** with verify‑then‑revert and a kill switch.
5. Binds all of it into **one note** written back onto the Case, with 👍/👎 feedback that regenerates an improved answer.

Everything is logged to an **audit trail**, and **every external dependency is optional** — the pipeline degrades gracefully rather than failing the case.

**Tech stack:** FastAPI (Python) · PostgreSQL + pgvector · Redis (optional) · Azure OpenAI (`gpt‑4o` + embeddings) · Model Context Protocol (MCP) tool servers · Dataverse Web API · Microsoft Learn search.

---

## 2. System context

```mermaid
graph TB
    subgraph Users
        REQ[Requester / Customer]
        ENG[Support Engineer]
        MGR[Support Manager]
    end

    subgraph SoR["System of Record"]
        D365[Dynamics 365 / ServiceNow<br/>Cases · AI note · pop-up · 👍/👎]
    end

    subgraph Quest["Quest — Orchestrator Service (FastAPI)"]
        API[REST API + Webhooks]
    end

    subgraph External["External Services"]
        AOAI[Azure OpenAI<br/>gpt-4o + embeddings]
        LEARN[Microsoft Learn<br/>reference search]
        DV[Dataverse Web API]
    end

    subgraph Data["Persistence"]
        PG[(PostgreSQL + pgvector)]
        REDIS[(Redis — optional)]
    end

    REQ -->|files case| D365
    ENG -->|accept / reject / 👍👎| D365
    MGR -->|risk dashboard| API
    D365 <-->|webhook / note write-back| API
    API --> AOAI
    API --> LEARN
    API <--> DV
    API --> PG
    API --> REDIS
```

**Actors**

| Actor | Interaction |
|---|---|
| **Requester** | Files the case in D365/ServiceNow. |
| **Support Engineer** | Reads the AI note, clicks Accept/Reject and 👍/👎, sends customer emails. |
| **Support Manager** | Monitors the SLA‑risk dashboard; approves suggested workflows. |
| **D365 / ServiceNow** | System of record; source of webhook events and target of the AI note. |

---

## 3. High‑level architecture

```mermaid
graph TB
    subgraph SoR["Dynamics 365 / ServiceNow — system of record"]
        CASE[Cases · AI note on timeline · pop-up 👍/👎]
    end

    CASE -->|"webhook: created / transferred / reactivated"| WH
    NOTE -->|"note / pop-up write-back"| CASE

    subgraph ORCH["ORCHESTRATOR — FastAPI (backend/app)"]
        WH["/orchestrator/*webhook → Orchestrator.handle_event()"]
        DEDUP[Dedupe + event classify]
        SEL{"Engine selector<br/>ENGINE = legacy | mcp<br/>(safe fallback to legacy)"}
        PIPE["Pipeline:<br/>Routing → Diagnosis → Recommendation → Mitigation"]
        GATE["Safety gate → kill-switch →<br/>simulate → verify → revert-if-failed"]
        NOTE[Note composer + write-back + /feedback]
        AUDIT[Audit sink → ai_audit_log best-effort]
        WH --> DEDUP --> SEL --> PIPE --> GATE --> NOTE
        PIPE --> AUDIT
    end

    SEL -->|legacy: direct LLM| AOAI
    SEL -->|mcp: JSON-RPC tool calls| MCP

    subgraph MCP["MCP servers (in-process or standalone)"]
        RS[reasoning · 8104<br/>route/diagnose/recommend]
        KS[knowledge · 8102<br/>search_docs]
        DVS[dataverse · 8101<br/>list/get/find/write]
    end

    AOAI[Azure OpenAI<br/>gpt-4o + embeddings]
    MCP --> AOAI
    MCP --> PGV

    DEDUP -.state / dedupe / context cache.-> REDIS[(Redis — optional,<br/>in-memory fallback)]
    PIPE --> PGV[(PostgreSQL + pgvector<br/>tickets · resolutions ·<br/>feedback · kb · audit)]
```

The orchestrator is a **stateless FastAPI service**. Two calls drive the ServiceNow flow — `/webhook` (an event happened) and `/decision` (the engineer responded) — while D365 uses `/d365-webhook` plus a background poller for hands‑off automation.

---

## 4. Component & layer architecture

```mermaid
graph TB
    subgraph L1["① API Layer — app/api/routers"]
        R1[auth.py]
        R2[tickets.py]
        R3[resolutions.py]
        R4[mcp.py]
        R5[orchestrator.py]
        R6[kb.py]
        R7[manager.py]
        R8[users.py / health.py]
    end

    subgraph L2["② Orchestration Layer — app/orchestrator"]
        O1[Orchestrator<br/>state machine]
        O2[engine selector]
        O3[d365_runner<br/>process_case]
        O4[roster · sla · handoff]
        O5[dedup · store · audit]
        O6[similarity · web_refs<br/>prevention · workflows]
        O7[d365_poller · dataverse]
    end

    subgraph L3["③ Agent Layer"]
        A1[RoutingAgent]
        A2[DiagnosisAgent]
        A3[RecommendationAgent]
        A4[InsightsBuddy]
        A5[CommCoach]
        A6[SummarizationAgent]
    end

    subgraph L4["④ MCP Layer — app/mcp_servers + app/mcp"]
        M1[reasoning_server]
        M2[knowledge_server]
        M3[dataverse_server]
        M4[MCPServer wrapper]
    end

    subgraph L5["⑤ Data Layer — app/db"]
        D1[SQLAlchemy models]
        D2[session / base]
        DB[(PostgreSQL + pgvector)]
    end

    L1 --> L2
    L1 --> L3
    L2 --> L3
    L2 --> L4
    L3 --> L4
    L2 --> L5
    L3 --> L5
    L4 --> L5
    D1 --> DB
```

| Layer | Responsibility | Key modules |
|---|---|---|
| **① API** | HTTP surface: auth, ticket CRUD, MCP analysis, webhooks, KB, manager dashboard | `app/api/routers/*` |
| **② Orchestration** | Event classification, dedupe, state machine, pipeline sequencing, engine selection, SLA/roster/handoff, note composition, safety net | `app/orchestrator/*` |
| **③ Agents** | The reasoning units: routing, diagnosis, recommendation, insights, email drafting, summarization | `app/agents/*`, `app/orchestrator/agents.py` |
| **④ MCP** | Every agent capability re‑exposed as a discoverable MCP tool for external agents (Copilot Studio / Azure AI Foundry) and for the `mcp` engine path | `app/mcp_servers/*`, `app/mcp/*` |
| **⑤ Data** | pgvector‑backed corpus of tickets, resolutions, KB, feedback, audit log | `app/db/*` |

---

## 5. Ticket lifecycle — state machine

```mermaid
stateDiagram-v2
    [*] --> INIT
    INIT --> ROUTING: event classified
    ROUTING --> DIAGNOSIS: accept
    DIAGNOSIS --> RECOMMENDATION: accept (reactivate)
    DIAGNOSIS --> DONE: accept (create/transfer)
    RECOMMENDATION --> DONE: accept
    ROUTING --> BLOCKED: reject / error / timeout
    DIAGNOSIS --> BLOCKED: reject / error / timeout
    RECOMMENDATION --> BLOCKED: reject / error / timeout
    DONE --> [*]
    BLOCKED --> [*]
```

**Pipeline by event type** (`states.py`):

| Event | Pipeline | Use case |
|---|---|---|
| `create` | `routing → diagnosis` | New ticket |
| `transfer` | `routing → diagnosis` | Reassignment |
| `reactivate` | `routing → diagnosis → recommendation` | Reopened ticket |

Each agent posts a JSON **advisory** back to the case; the engineer's **Accept** advances to the next agent, **Reject** drops to `BLOCKED` and flags the override for retraining. After an accepted recommendation, an optional **health‑check probe** re‑fires ~15 min later if symptoms persist (capped at 2 follow‑ups).

---

## 6. End‑to‑end data flow (case → outcome)

```mermaid
sequenceDiagram
    participant D365 as D365 / ServiceNow
    participant API as Orchestrator API
    participant ORC as Orchestrator
    participant CTX as Context (MCP/DB/embeddings)
    participant AG as Agents (Route/Diag/Recommend)
    participant MIT as Mitigation safety net
    participant AUD as ai_audit_log

    D365->>API: webhook {ticket_id, event_type, ...}
    API->>ORC: handle_event(payload)
    ORC->>ORC: dedupe (Redis SET NX) + classify
    ORC->>CTX: fetch ticket + history + similar cases
    CTX-->>ORC: context (cached 5 min)
    ORC->>AG: run pipeline stage
    AG-->>ORC: advisory JSON (confidence, evidence)
    ORC->>AUD: log input/output/confidence (best-effort)
    ORC-->>API: advisory
    API-->>D365: post note / pop-up
    D365->>API: /decision {accept}
    API->>ORC: handle_decision
    ORC->>AG: next stage (or DONE)
    Note over MIT: if gate passes & kill-switch off
    MIT->>MIT: simulate → verify → revert-if-failed
    D365->>API: /feedback 👎 + comment
    API->>AG: regenerate with feedback context
```

**Sequence highlights**

1. **Dedupe first** — webhook + Power Automate retries + poller can all fire the same case within ~20s; Redis `SET NX` (10‑min TTL) guarantees one note.
2. **Context is cached** — ticket + history cached 5 min per `ticket_id`; the event is always rebuilt fresh.
3. **Diagnosis is grounded** — similarity search over the `resolutions` corpus (cosine over pgvector), not free‑form generation.
4. **References are allowlisted** — recommendation links validated against `trusted_domains.json` / Microsoft Learn only.
5. **Feedback loops back** — 👎 re‑runs the relevant agent with the engineer's comment injected as extra context.

---

## 7. Dual reasoning engine (the fallback flag)

```mermaid
graph LR
    WH[webhook] --> SEL{ENGINE env}
    SEL -->|legacy default| LEG["d365_runner.process_case<br/>agents call LLM in-process"]
    SEL -->|mcp| MCPE["mcp_engine.process_case_mcp<br/>reasoning via MCP tool boundary"]
    MCPE -.import fails.-> LEG
    LEG --> OUT["(advisory, note)"]
    MCPE --> OUT
```

Both engines funnel through the **same** `d365_runner.process_case`, so orchestration, confidence blend, grounding cap, and note formatting **never diverge** — only *how each agent's answer is produced* differs. `ENGINE=mcp` routes reasoning through the MCP tool servers (the governed surface reused by Copilot Studio); if the MCP layer can't be imported (e.g. a slim deploy), it **fails safe to legacy**. This lets MCP be adopted incrementally and rolled back instantly via one env flag, with zero behavioral drift.

---

## 8. Agents

| Agent | Module | Responsibility | Output shape |
|---|---|---|---|
| **RoutingAgent** | `orchestrator/agents.py` | Classify into a K8s/Karpenter support team (10 categories) + pick an on‑shift, skill‑matched engineer | `recommended_team`, `assigned_engineer{}`, `confidence`, `reason` |
| **DiagnosisAgent** | `orchestrator/agents.py` | Root cause grounded in nearest historical cases | `root_cause`, `grounded`, `confidence` |
| **RecommendationAgent** | `orchestrator/agents.py` | Hot Fix + Ultimate Fix + allowlisted reference links | `hot_fix{}`, `ultimate_fix{}`, `trusted_links[]`, `confidence` |
| **InsightsBuddy** | `agents/insights.py` | In‑app analysis: similarity search, KB match, recommended steps, root cause + recommendation | `similar_tickets`, `recommended_steps`, `kb_recommendations`, `root_cause` |
| **CommCoach** | `agents/communication.py` | Draft → edit → approve → send customer emails; log resolutions; flag stale comms | `Email` (DRAFT/APPROVED), `Resolution` |
| **SummarizationAgent** | `agents/summarization_agent.py` | 1–3 sentence ticket summary + error‑code extraction | `summary`, `error_codes[]` |

**Roster & SLA** — `roster.py` picks engineers in tiers (on‑shift+specialty → on‑call+specialty → any on‑shift → any on‑call → least‑loaded with SLA‑risk flag), respecting each engineer's own timezone/shift. `sla.py` maps priority to Tier 1/2/3 (15 min/4 h · 60 min/8 h · 240 min/24 h), failing open to Tier 3 for unparsed priorities. `handoff.py` reassigns and posts a conversation digest when an assignee's shift ends mid‑ticket.

---

## 9. MCP (Model Context Protocol) layer

```mermaid
graph TB
    subgraph Consumers
        ENGINE[mcp_engine.py<br/>in-process]
        EXT[Copilot Studio /<br/>Azure AI Foundry]
    end

    subgraph Servers["MCP servers — app/mcp_servers"]
        RS["reasoning_server :8104<br/>route_case · diagnose_case · recommend_case"]
        KS["knowledge_server :8102<br/>search_docs"]
        DVS["dataverse_server :8101<br/>list_cases · get_case · find_similar_cases · write_note"]
    end

    subgraph Backing
        AGENTS[Routing/Diagnosis/Recommendation agents]
        REFS[web_refs — Microsoft Learn + allowlist]
        DVC[DataverseClient]
    end

    ENGINE --> RS
    ENGINE --> KS
    EXT -.stdio / HTTP.-> RS
    EXT -.stdio / HTTP.-> KS
    EXT -.stdio / HTTP.-> DVS
    RS --> AGENTS
    KS --> REFS
    DVS --> DVC
```

Each server runs **in‑process by default** (imported callables) or as a **standalone process** over stdio/HTTP (`_runtime.py` reads `MCP_TRANSPORT` / `MCP_HOST` / `MCP_PORT`) for out‑of‑process tool isolation. The `MCPServer` wrapper (`app/mcp/server.py`) composes InsightsBuddy + CommCoach for the in‑app analysis/email workflow. Exposing every capability as a discoverable tool means the same governed surface serves both the live `mcp` engine and external LLM agents.

---

## 10. Data model

```mermaid
erDiagram
    users ||--o{ tickets : "created_by / assigned_to"
    users ||--o{ users : "manager_id"
    tickets ||--o{ resolutions : has
    tickets ||--o{ emails : has
    tickets ||--o{ ai_audit_log : logs
    kb_articles ||--o{ ticket_kb_mapping : mapped
    kb_articles ||--o{ kb_feedback : rated
    ai_audit_log ||--o{ recommendation_feedback : rated

    users {
        uuid user_id PK
        text email UK
        text role "REQUESTER|SUPPORT|SUPPORT_MANAGER"
        uuid manager_id FK
    }
    tickets {
        uuid ticket_id PK
        text title
        text description
        text status "NEW|ASSIGNED|RESOLVED"
        uuid created_by FK
        uuid assigned_to FK
        vector embedding "1536"
        text priority
        text ticket_summary
    }
    resolutions {
        uuid resolution_id PK
        uuid ticket_id FK
        text resolution_text
        text root_cause
        json recommendedsteps
        numeric confidence_score
        vector embedding "1536"
    }
    emails {
        uuid email_id PK
        uuid ticket_id FK
        text type "DRAFT|APPROVED"
        text subject
        text body
    }
    kb_articles {
        uuid kb_id PK
        text title
        text url
        vector embedding "1536"
        int times_recommended
        int times_resolved
    }
    ticket_kb_mapping {
        uuid mapping_id PK
        uuid kb_id FK
        numeric similarity
    }
    kb_feedback {
        uuid kb_feedback_id PK
        uuid kb_id FK
        string verdict "like|dislike"
    }
    recommendation_feedback {
        uuid feedback_id PK
        uuid ai_event_id
        string verdict "like|dislike"
    }
    ai_audit_log {
        uuid ai_event_id PK
        uuid ticket_id FK
        text agent_name
        jsonb input_json
        jsonb output_json
        jsonb confidence_json
        bool was_used
    }
```

**Notable design points**

- **pgvector everywhere it matters** — `tickets`, `resolutions`, `kb_articles` carry `vector(1536)` embeddings; an HNSW cosine index accelerates similarity search over KB resolutions.
- **Outcome‑based KB ranking** — `kb_articles.times_recommended` / `times_resolved` / `total_resolution_hours` yield computed `success_rate` and `avg_resolution_hours`, so KB re‑ranks by *proven* value, not static metadata.
- **Feedback tables** — `kb_feedback` and `recommendation_feedback` capture 👍/👎 (+ comment) and drive regeneration and re‑ranking.
- **Best‑effort audit** — `ai_audit_log` records every decision (input/output/confidence/supporting incident IDs/`was_used`); a write failure never breaks the case.

---

## 11. External integrations & graceful degradation

| Dependency | Used for | If unavailable |
|---|---|---|
| **Azure OpenAI (gpt‑4o)** | Agent reasoning (`llm.chat_json`) | Deterministic fallback responses |
| **Azure OpenAI embeddings** | Similarity search (`embeddings.embed_*`) | Falls back to a small set of reference tickets |
| **Dataverse Web API** | Read cases / write notes (`DataverseClient`, OAuth2 client‑creds) | `available()` → False; in‑memory demo path |
| **Microsoft Learn** | Reference links (`web_refs.search_refs`) | Links omitted; recommendation still produced |
| **PostgreSQL + pgvector** | Persistence + vector search | Works without persistence/audit (NFR‑6) |
| **Redis** | Event dedupe + state + context cache | In‑memory dict fallback (state lost on restart) |

> **Design principle (NFR‑1/3):** a failure in any one stage degrades *that* stage rather than aborting the case; when in doubt (low confidence, no precedent, irreversible action) the system **suggests rather than acts**.

---

## 12. Safety net — guarded auto‑remediation

```mermaid
graph TB
    REC[Recommendation ready] --> GATE{"Safety gate<br/>conf ≥ 0.85 AND<br/>match ≥ 0.80 AND<br/>runbook Tier-A AND reversible"}
    GATE -->|no| SUG[suggest_only]
    GATE -->|yes| KS{"Kill switch on?<br/>≥3 reverts / 3600s"}
    KS -->|disabled| OFF[auto_off]
    KS -->|enabled| EXEC[simulate execute]
    EXEC --> VER{Verify outcome}
    VER -->|success| RES[auto_resolved]
    VER -->|failure| REV[revert via undo steps<br/>+ escalate → reverted_escalated]
```

The mitigation path always ends in **exactly one** of `suggest_only`, `auto_off`, `auto_resolved`, `reverted_escalated` — never a silent applied fix. It is judged by its **own kill switch** (trips after repeated reverts), not by the confidence score that admitted it, because "a confident wrong fix" is exactly the failure mode the net exists to catch. Runbooks and the trusted‑domain allowlist are **data** (`config/*.json`), editable without a redeploy.

---

## 13. Deployment topology

```mermaid
graph TB
    subgraph Full["Full app — backend/app/main.py"]
        MAIN[All routers + ML deps<br/>requirements.txt]
    end
    subgraph Slim["Orchestrator-only — orchestrator_server.py"]
        SLIM[No torch/sentence-transformers<br/>requirements-orchestrator.txt<br/>low-cost hosting Render]
    end
    subgraph Tools["MCP servers"]
        INPROC[In-process default]
        STANDALONE[Standalone processes<br/>mcp-service/main.py :8101-8104]
    end
    MAIN --> PG[(Postgres+pgvector)]
    MAIN --> REDIS[(Redis)]
    SLIM -.optional.-> PG
    MAIN --> INPROC
    SLIM --> INPROC
```

- **Full app** — every router + ML dependencies; the complete in‑app experience.
- **Orchestrator‑only** — slim deploy without heavy ML libs for cheap always‑on hosting (NFR‑5); same orchestrator router, optional DB.
- **MCP** — in‑process by default; standalone processes (`mcp-service/`, ports 8101–8104) when tool isolation is wanted. Local dev via `docker-compose.yml` (pgvector + redis).

---

## 14. Key design decisions

| Decision | Rationale |
|---|---|
| **Dual engine, identical downstream logic** | Adopt MCP incrementally, roll back instantly (env flag), zero behavioral drift. |
| **Config externalized, thresholds in env** | Runbooks/domains change often (ops content); safety thresholds stay visible in deploy config. |
| **Verify‑then‑revert, not verify‑then‑trust** | Auto‑remediation is policed by its own kill switch, catching confident‑but‑wrong fixes. |
| **Best‑effort persistence** | The case pipeline is the product; the audit trail must never be a single point of failure. |
| **Grounded reasoning only** | Diagnosis cites the team's real past cases; references come from an allowlist — no hallucinated fixes/links. |
| **Shift‑aware assignment** | The SLA clock cares whether the assignee is *awake now*, not what timezone the customer filed from. |
| **Stateless + optional stores** | Runs with or without Postgres/Redis for low‑friction environments (NFR‑6). |

---

## 15. Known gaps / roadmap

- `dataverse_server.py` remediation execution is **simulated** — real Dataverse/Graph/Defender API calls are Phase‑3 placeholders.
- `app/services/` is empty — no custom services beyond agents/orchestrator yet.
- `tests/test_basic.py` is a placeholder; real coverage lives in `backend/app/orchestrator/test_orchestrator.py`.
- Bearer‑token auth on the orchestrator webhooks is planned before UAT (open in dev today).
- Next milestone: a real Power Automate "approve‑and‑execute" flow so managers approve suggested workflows — the orchestrator only ever *proposes*, never executes unattended.

---

*Generated from source at `backend/app/` — orchestrator, agents, MCP servers, and data models. Diagrams render on GitHub (Mermaid). A print‑ready PDF version accompanies this document.*
