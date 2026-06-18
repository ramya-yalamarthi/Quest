# Sentinel — AI Support Agent with Mitigation Safety

> **Sentinel keeps a human in the loop. We close the loop only after the change has proven itself safe.**

Sentinel is an AI Support Agent for Microsoft Dynamics 365 / ServiceNow tickets,
plus a **Mitigation Safety & Staged Rollout** safety layer that ensures no
AI-driven mitigation reaches production without staging, validation, and
explicit human approval.

This repository contains:

- A **FastAPI backend** that ingests tickets, runs a multi-agent orchestrator
  (routing → diagnosis → recommendation), and exposes the Mitigation Safety
  pipeline (`stage → validate → promote / revert`).
- A **Next.js operator dashboard** that surfaces every safety guarantee in
  the SRS to an on-call engineer.
- An **immutable, DB-enforced audit log** of every mitigation transition.
- A **durable APScheduler worker** that survives restart and re-evaluates
  in-flight 24-hour validation windows.
- A **Mock adapter** so the dashboard runs end-to-end with no backend.

The single source of truth for the safety guarantees is
[`SRS.md`](./SRS.md) at the repo root. Every backend module and UI surface
maps back to a numbered requirement (`MS-01..MS-26`) and acceptance
scenario (`S1..S4`) defined there.

---

## Table of contents

1. [What this project does](#1-what-this-project-does)
2. [System architecture](#2-system-architecture)
3. [Repository layout](#3-repository-layout)
4. [Run it locally](#4-run-it-locally)
5. [Run the dashboard against a mock (no backend)](#5-run-the-dashboard-against-a-mock-no-backend)
6. [Run it in Docker](#6-run-it-in-docker)
7. [Tests](#7-tests)
8. [How to develop in this repo](#8-how-to-develop-in-this-repo)
9. [Reference: SRS guarantees → backend code → UI surface](#9-reference-srs-guarantees--backend-code--ui-surface)
10. [Environment variables](#10-environment-variables)
11. [API surface](#11-api-surface)
12. [History & change log](#12-history--change-log)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. What this project does

Two cooperating products live in this repo:

### 1.1 AI Support Agent (the orchestrator)
*See [`docs/AI_Support_Agent_Architecture.md`](./docs/AI_Support_Agent_Architecture.md).*

When a support case is created in Dynamics 365 (or ServiceNow), the
orchestrator:

1. **Routes** the case to the right team.
2. **Diagnoses** the root cause using similarity search across closed cases
   (pgvector embeddings) and Azure OpenAI gpt-4o.
3. **Recommends** a fix (or auto-remediates with a registered runbook), with
   confidence and precedent.
4. Writes a single consolidated note back to the case timeline, with
   one-click 👍 / 👎 feedback that loops back into model confidence.

Implementation lives under [`backend/app/orchestrator/`](./backend/app/orchestrator/).

### 1.2 Mitigation Safety & Staged Rollout (the spec)
*Specified in [`SRS.md`](./SRS.md); implemented under [`backend/app/mitigation_safety/`](./backend/app/mitigation_safety/) with its own [README](./backend/app/mitigation_safety/README.md).*

No mitigation the orchestrator produces touches production directly. Every
action is:

- **Staged** to an isolated branch (code) or non-prod scope (config) with a
  **registered, tested revert handle** (mandatory).
- Held in a **24-hour validation window** where five checks run: generated
  tests in CI, the regression suite, component telemetry within bounds, no
  new correlated incidents, and human sign-off where required.
- **Promoted** to production only after `overall_status == PASS` AND
  (for confirm-to-promote categories) an explicit human confirm.
- **Reversible in one action** — idempotent — for 24h after promotion.
- Watched by **guards** that auto-trip system or category-scoped Safe Mode
  if validation-failure / rollback / decline rates cross thresholds.
- **Safe Mode** is **default-on** at every restart and **never self-clears**
  — exit requires an explicit, logged human action (`human:<id>` actor).
- Every transition is recorded in an **append-only audit log**, enforced
  at the Postgres level by a trigger plus REVOKE on UPDATE/DELETE/TRUNCATE.

The 9 non-negotiable invariants from §1 of the SRS are enforced
server-side; the dashboard surfaces them but never enforces them.

---

## 2. System architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                          Dynamics 365 / ServiceNow                         │
│                  (Case form, timeline notes, BPF stages)                   │
└──────────────────────────┬─────────────────────────────────────────────────┘
                           │ webhook / polling
                           ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                              FastAPI backend                               │
│  ─────────────────────────────────────────────────────────────────────────│
│                                                                            │
│   ┌──────────────────────┐   ┌──────────────────────────────────────────┐│
│   │  Orchestrator        │   │  Mitigation Safety & Staged Rollout      ││
│   │  (existing)          │──▶│  (this repo's core safety guarantee)     ││
│   │                      │   │                                          ││
│   │  routing →           │   │   domain  → states + transitions guard   ││
│   │  diagnosis →         │   │   staging → scope isolation + runners    ││
│   │  recommendation →    │   │   validation → 5 checks + 24h window     ││
│   │  (eligibility gate)  │   │   safemode  → enter/exit (human only)    ││
│   │                      │   │   guards    → rolling-window evaluator   ││
│   │  audits to           │   │   audit     → immutable append-only log  ││
│   │  ai_audit_log        │   │   worker    → APScheduler durable jobs   ││
│   │                      │   │                                          ││
│   └──────────────────────┘   └────────────┬─────────────────────────────┘│
│                                            │                              │
│   ┌──────────────────────┐   ┌─────────────▼─────────────────────────────┐│
│   │  Azure OpenAI gpt-4o │   │   Postgres + pgvector (single DB)        ││
│   │  Bing / DDGS search  │   │   ┌─────────────────────────────────────┐ ││
│   │  Microsoft Learn API │   │   │ legacy tables:                      │ ││
│   └──────────────────────┘   │   │   users, tickets, resolutions, …    │ ││
│                              │   │ ms_* tables (mitigation_safety):    │ ││
│   ┌──────────────────────┐   │   │   ms_staging_deployment             │ ││
│   │  Redis (optional)    │   │   │   ms_validation_result              │ ││
│   │  - state + dedup     │   │   │   ms_safe_mode_state                │ ││
│   │  - context cache     │   │   │   ms_bot_action_log                 │ ││
│   └──────────────────────┘   │   │   ms_audit_log  ← append-only       │ ││
│                              │   │   ms_guard_event                    │ ││
│                              │   │   ms_apscheduler_jobs ← durable     │ ││
│                              │   └─────────────────────────────────────┘ ││
│                              └───────────────────────────────────────────┘│
│                                                                            │
└─────────────┬──────────────────────────────────────────────────────────────┘
              │ HTTP/SSE (REST + realtime stream)
              ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                  Next.js operator dashboard (frontend/)                    │
│  ─────────────────────────────────────────────────────────────────────────│
│                                                                            │
│   /                       Overview — "is it safe right now?"               │
│   /actions  /actions/[id] Pipeline + action detail (LoopRing signature)    │
│   /validation             In-flight 24h windows + component telemetry      │
│   /safe-mode              Posture control + guard thresholds + history     │
│   /audit                  Immutable, queryable, CSV-exportable trail       │
│   /settings               Hot-reloadable windows + confirm-to-promote      │
│                                                                            │
│   Mock adapter ships in-process so the dashboard runs with NO backend.     │
└────────────────────────────────────────────────────────────────────────────┘
```

### Key safety boundaries

| Boundary | Where it lives | Enforced by |
|---|---|---|
| Production effect | `backend/app/mitigation_safety/staging/promotion.py::PromotionService.promote` | The **only** call site of `apply_to_production` |
| Append-only audit | `backend/app/mitigation_safety/db/grants.py::apply_immutability` | Postgres trigger + REVOKE UPDATE/DELETE/TRUNCATE |
| Default-on Safe Mode | `backend/app/mitigation_safety/safemode/boot.py::ensure_default_on` | FastAPI startup hook in `backend/app/main.py` |
| Human-only Safe Mode exit | `backend/app/mitigation_safety/safemode/controller.py::exit` | Raises `SafeModeHumanRequired` on any non-`human:*` actor + DB CHECK constraint |
| State machine | `backend/app/mitigation_safety/domain/states.py` + `transitions.py` | `assert_legal` chokepoint every state write passes through |
| Idempotent revert | `backend/app/mitigation_safety/staging/revert.py::RevertService.revert` | Terminal short-circuit returns `idempotent=True` |
| Scope isolation | `backend/app/mitigation_safety/staging/scope_isolation.py` | NFKC-normalised token-bound prod-pattern blocklist |

---

## 3. Repository layout

```
Quest/
├── README.md                    ← you are here
├── SRS.md                       ← the specification (single source of truth)
├── docker-compose.yml           ← Postgres (pgvector) + Redis
├── requirements.txt             ← top-level shortcut for pip
│
├── backend/                     ← FastAPI app
│   ├── app/
│   │   ├── main.py              ← FastAPI factory; wires both stacks
│   │   ├── config.py            ← DATABASE_URL, JWT secrets, embeddings
│   │   ├── api/routers/         ← health, auth, tickets, resolutions, users, mcp, orchestrator
│   │   ├── auth/                ← JWT (+ aud/iss validation; refuse boot in prod with dev secret)
│   │   ├── agents/              ← summarization, web-solutions, insights, communication agents
│   │   ├── db/                  ← session, base, models/  (legacy schema)
│   │   ├── mcp/                 ← Model Context Protocol tools the agents call
│   │   ├── orchestrator/        ← Supervisor + 4 agents (routing/diagnosis/recommendation)
│   │   ├── schemas/             ← Pydantic DTOs
│   │   ├── services/, utils/    ← shared helpers
│   │   └── mitigation_safety/   ← THE SAFETY MODULE  (own README inside)
│   │       ├── README.md        ← MS-01..MS-26 → code/test traceability map
│   │       ├── domain/          ← states, transitions, errors, ids
│   │       ├── staging/         ← scope isolation, revert handles, runners
│   │       ├── validation/      ← 5 checks + CI/telemetry interfaces + mocks + real impls
│   │       ├── safemode/        ← controller + boot (default-on, human-only exit)
│   │       ├── guards/          ← rolling-window evaluator + auto-revert
│   │       ├── audit/           ← append-only logger + reconstructors
│   │       ├── notifications/   ← engineer + lead alerts (logging + webhook)
│   │       ├── api/             ← 6 routes + require_human dep + 410 shims
│   │       ├── db/              ← ms_* SQLAlchemy models + grants.py (trigger SQL)
│   │       ├── worker/          ← APScheduler factory + jobs + on_startup_rearm
│   │       ├── config.py        ← hot-reloadable JSON config (MS-19)
│   │       └── startup.py       ← fail-loud boot (immutability + Safe Mode + scheduler)
│   ├── alembic/                 ← migrations (two revisions; legacy baseline + ms_*)
│   ├── alembic.ini
│   ├── scripts/                 ← one-off SQL + embedding backfill + agent smoke tests
│   ├── d365/                    ← inline D365 popup (vanilla HTML/JS)
│   ├── orchestrator_server.py   ← slim orchestrator-only entrypoint
│   ├── requirements.txt         ← full app deps
│   ├── requirements-orchestrator.txt  ← slim deps (no ML, no APScheduler)
│   ├── Dockerfile               ← slim orchestrator image
│   └── Dockerfile.app           ← full app image (runs alembic upgrade head on boot)
│
├── frontend/                    ← Next.js operator dashboard
│   ├── package.json, tsconfig.json, next.config.mjs, tailwind.config.ts
│   ├── lib/
│   │   ├── design/tokens.css    ← dark + light semantic tokens (WCAG-verified)
│   │   ├── api/                 ← typed Api contract + mock + REST adapters
│   │   ├── hooks/               ← useRealtime, useCountdown, useSafeMode, useGuardStatus, useTheme
│   │   └── util/                ← cn, format
│   ├── components/              ← signature primitives + global frame + ui/ shadcn-style
│   ├── app/                     ← App Router routes (G5 build in progress)
│   └── _archive_vite_mvp/       ← earlier Vite MVP (kept for reference; superseded)
│
├── tests/
│   └── mitigation_safety/       ← 92 pytest tests (domain, audit, S1–S4, HTTP, worker, …)
│       └── conftest.py          ← isolated SQLite schema with UuidStr TypeDecorator
│
├── mcp-service/                 ← Placeholder MCP tool registry (FastAPI stub + Dockerfile)
├── docs/                        ← Architecture write-ups
│   └── AI_Support_Agent_Architecture.md
└── History/                     ← Durable plans + remediation logs (one per phase)
    ├── mitigation-safety-staged-rollout-2026-06-17.md   (F1–F10 implementation)
    ├── mitigation-safety-review-remediation-2026-06-17.md (F11–F18 fixes)
    └── mitigation-safety-dashboard-ui-2026-06-17.md     (G1–G9 dashboard build)
```

---

## 4. Run it locally

### 4.1 Prerequisites

- **Python 3.11+** (3.12 in the Dockerfile).
- **Node.js 20+** + npm for the dashboard.
- **Docker** (only for Postgres + Redis; you can use your own if you prefer).

### 4.2 First-time setup

```bash
# 1. Postgres (pgvector) + Redis
docker compose up -d pgvector redis

# 2. Backend deps
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Environment — copy and fill in values
cat > .env <<EOF
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/support_ai
JWT_SECRET=replace-me-outside-dev
APP_ENV=dev
# Optional: real backends for staged rollout
# MITIGATION_SAFETY_CI_BACKEND=github
# MITIGATION_SAFETY_TELEMETRY_BACKEND=azure
EOF

# 4. Apply database migrations (creates BOTH legacy + ms_* tables)
alembic upgrade head

# 5. Start the full backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Verify it's up:

```bash
curl http://localhost:8000/health
# → {"status":"ok"}

# Open /docs in a browser for the OpenAPI surface.
open http://localhost:8000/docs
```

### 4.3 Run the slim orchestrator (no mitigation safety)

If you only need the agent pipeline (ServiceNow / D365 webhook + recommendations),
use the orchestrator-only entrypoint — it skips the ML stack, the
APScheduler worker, and the Azure SDKs.

```bash
cd backend
pip install -r requirements-orchestrator.txt
uvicorn orchestrator_server:app --reload --host 0.0.0.0 --port 8000
```

### 4.4 Run the dashboard against the real backend

```bash
cd frontend
npm install

# Point the dashboard at the FastAPI host
cat > .env.local <<EOF
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_BRAND=Sentinel
NEXT_PUBLIC_DEFAULT_THEME=dark
NEXT_PUBLIC_REALTIME=sse
EOF

npm run dev
# → http://localhost:3000
```

The dashboard's API client proxies through `/api/*` (see
`frontend/next.config.mjs` rewrites) so you never hit CORS in dev.

---

## 5. Run the dashboard against a mock (no backend)

The dashboard ships with a **full in-memory mock adapter** that satisfies
the same `Api` contract as the live REST client. It seeds five mitigation
actions in different states (one happy-path Validating, one PASSed
awaiting confirm, one Promoted with rollback countdown, one Failed→
Reverted, one Expired→Reverted), simulates a streaming event source,
ticks down the 24-hour validation window, and supports scenario triggers
(fail a check, trip a guard).

```bash
cd frontend
npm install

# DO NOT set NEXT_PUBLIC_API_BASE_URL — the absence selects the mock.
npm run dev
```

The mock lives at [`frontend/lib/api/mock.ts`](./frontend/lib/api/mock.ts).
Test scenario helpers are exported from `mockHelpers` (`fail(actionId)`,
`tripGuard(category)`).

---

## 6. Run it in Docker

There are **two** images, by design:

### 6.1 Full app (mitigation safety enabled)

```bash
cd backend
docker build -f Dockerfile.app -t sentinel-app:latest .
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=postgresql://postgres:postgres@host.docker.internal:5432/support_ai \
  -e JWT_SECRET="$(openssl rand -hex 32)" \
  -e APP_ENV=prod \
  sentinel-app:latest
```

The image runs `alembic upgrade head` on container start, then serves
`app.main:app`. If migrations fail, the app still boots and its own
startup hook installs the audit-immutability trigger as a belt-and-braces.

### 6.2 Slim orchestrator (no mitigation safety)

```bash
cd backend
docker build -f Dockerfile -t sentinel-orchestrator:latest .
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=... \
  sentinel-orchestrator:latest
```

This is the existing production image — small, fast, no ML, no APScheduler,
no Azure SDKs.

### 6.3 Dev stack (Postgres + Redis only)

```bash
docker compose up -d
# pgvector → localhost:5432
# redis    → localhost:6379
```

---

## 7. Tests

**92 tests pass against the mitigation_safety module — including every
non-negotiable invariant and acceptance scenario S1–S4.**

```bash
cd /Users/isaachernandez/Documents/GitHub/Quest    # repo root
pytest tests/mitigation_safety -q
# → 92 passed
```

The test conftest builds an isolated SQLite schema with a `UuidStr`
TypeDecorator that round-trips `uuid.UUID` ↔ string transparently, so the
same runtime code paths exercise without psycopg2 or pgvector installed.
The DB-level append-only trigger is emulated via a SQLAlchemy `before_flush`
listener that matches the Postgres trigger's behavior on the ORM path; the
real trigger is unit-tested separately via the SQL-shape assertion in
[`tests/mitigation_safety/test_audit_raw_sql_immutability.py`](./tests/mitigation_safety/test_audit_raw_sql_immutability.py).

Other test entrypoints:

- `backend/app/orchestrator/test_orchestrator.py` — orchestrator state-machine
  tests (run from inside the orchestrator package).
- `backend/test_search.py` — ad-hoc similarity-search smoke test.
- `backend/scripts/test_agents.py` — manual test of the four orchestrator
  agents (diagnosis → routing → prevention → recommendation).

---

## 8. How to develop in this repo

### 8.1 Where to make a change

| You want to … | Open this file |
|---|---|
| Add a backend API route for mitigation flows | `backend/app/mitigation_safety/api/tickets_routes.py` or `safemode_routes.py` |
| Add a new mitigation state | `backend/app/mitigation_safety/domain/states.py` + `transitions.py` + a test in `tests/mitigation_safety/test_domain_transitions.py` |
| Add a new MS-09 validation check | `backend/app/mitigation_safety/validation/checks/<your_check>.py`, then register in `validation/checks/__init__.py::default_checks` |
| Wire a real CI / telemetry backend | implement the protocol in `validation/ci/<your_runner>.py` or `validation/telemetry/<your_source>.py`; select via `MITIGATION_SAFETY_CI_BACKEND=...` in `api/container.py::_pick_ci` |
| Change a window duration / threshold | runtime — edit `MITIGATION_SAFETY_CONFIG_PATH=<file>.json` (hot-reloaded; MS-19). Defaults live in `mitigation_safety/config.py`. |
| Add an audit-row reconstructor | `backend/app/mitigation_safety/audit/reconstruct.py` |
| Add a new dashboard route | create `frontend/app/<route>/page.tsx`; use `getApi()` from `lib/api/` so it works against both mock + REST |
| Add a new dashboard component | put it in `frontend/components/`; if it's UI-primitive, in `frontend/components/ui/` |
| Change a design token | `frontend/lib/design/tokens.css` (both light + dark variants; verify contrast in both) |

### 8.2 Add a migration

```bash
cd backend
alembic revision -m "describe-your-change"
# Edit the generated file under alembic/versions/...
alembic upgrade head
```

Every migration that touches `ms_audit_log` should re-call
`apply_immutability(op.get_bind())` at the end so the trigger and grants
survive any DDL.

### 8.3 Add a test

The test conftest is doing real work — read it once before writing new
mitigation_safety tests:
[`tests/mitigation_safety/conftest.py`](./tests/mitigation_safety/conftest.py).

```python
def test_some_new_invariant(service_bundle, make_action):
    s = service_bundle
    action = make_action(state="APPROVED", category="capacity_quota")
    # ... use s["staging"], s["validation"], s["promotion"], s["revert"],
    # s["safe_mode"], s["guard"], s["rolling"], s["audit"] ...
```

For HTTP-level tests use the pattern in
[`tests/mitigation_safety/test_http_routes.py`](./tests/mitigation_safety/test_http_routes.py)
(FastAPI `TestClient` with `get_db` dependency-overridden).

### 8.4 Add a feature end-to-end

When a new feature touches multiple layers (e.g. "add a per-category
notification webhook"):

1. **Spec / SRS**: if it's a safety guarantee, propose an `MS-xx` ID and
   update [`SRS.md`](./SRS.md) first.
2. **Backend domain layer**: add types + tests in
   `backend/app/mitigation_safety/domain/` and `tests/mitigation_safety/`.
3. **Service layer**: implement in the right subpackage
   (`staging/`, `validation/`, `guards/`, `notifications/`).
4. **Wire in `api/container.py`** so both HTTP routes and worker jobs see
   the new service (the worker reuses `api.container.services(db)` —
   never duplicate runtime composition).
5. **Migration**: add an Alembic revision.
6. **README + traceability**: add the MS-xx row to
   [`backend/app/mitigation_safety/README.md`'s traceability table](./backend/app/mitigation_safety/README.md#ms-xx--code--test-traceability-map).
7. **Dashboard**: surface it under the appropriate route — add a typed
   field in `frontend/lib/api/types.ts`, add the mock seed in
   `frontend/lib/api/mock.ts`, render it.

### 8.5 House rules

- **Never bypass `assert_legal`** for a state write. Every transition
  passes through `backend/app/mitigation_safety/domain/transitions.py`.
- **Production effect is only `apply_to_production`**, only inside
  `PromotionService.promote`, only after `assert_can_promote` passes.
  Grep should show **one** call site, ever.
- **Safe Mode exit must come from a `human:*` actor.** The controller
  rejects anything else; the DB CHECK constraint backs it up. Don't
  add a code path that calls `exit` from anywhere else.
- **No raw `UPDATE` or `DELETE` against `ms_audit_log`.** The test
  `tests/mitigation_safety/test_audit_raw_sql_immutability.py` greps the
  whole module for these substrings and fails the build if it finds them.
- **Don't put `db.commit()` inside a service method.** The caller
  (route, worker job) owns the transaction. The one exception is the
  isolated MS-23 Safe Mode write — see
  `staging/service.py::_persist_safe_mode_in_isolation`.
- **Color is never the only signal in the dashboard.** Every status pairs
  color + icon + text label + shape (`StateBadge` is the canonical
  example).
- **No `localStorage` / `sessionStorage` in the dashboard.** Auth tokens
  belong in httpOnly cookies; app state lives in React state / TanStack
  Query.

---

## 9. Reference: SRS guarantees → backend code → UI surface

| SRS invariant | Backend implementation | UI surface |
|---|---|---|
| **#1** No direct-to-prod | `staging/promotion.py::PromotionService.promote` (sole `apply_to_production` site) | Promote button gated by validation PASS + consequence dialog |
| **#2** Never auto-promote on timeout | `validation/service.py::mark_expired`, `worker/jobs.py::expiry_poller` | LoopRing breaks visibly on Expire; toast `window_expired` |
| **#3** Failed check → auto-revert | `validation/service.py::evaluate_now::_mark_failed` | Per-check FAIL row + toast `validation_failed` |
| **#4** No execution without tested revert handle | `domain/transitions.py::assert_can_stage` + `staging/service.py::stage` | Stage button disabled with tooltip "no revert handle" |
| **#5** Safe Mode default-on, never self-clears | `safemode/boot.py::ensure_default_on`, `safemode/controller.py::exit` | Striped halt banner + pill on every page; toggle confirm dialog requires reason |
| **#6** Fail toward human/revert | per-check deadline timeouts, mock fallback when env is incomplete | Validation panel shows PENDING → FAIL on timeout; no silent pass |
| **#7** Staging isolation | `staging/scope_isolation.py::ScopeIsolationVerifier` | Stage API returns 409 with `scope_isolation` error; UI shows it inline |
| **#8** Idempotent revert | `staging/revert.py::RevertService.revert` (terminal short-circuit) | Revert dialog reports "Already reverted" on re-issue, never an error |
| **#9** Immutable audit | `db/grants.py::apply_immutability` (Postgres trigger + REVOKE) | Audit table has no edit/delete affordances; rows are time-ordered, immutable |
| **MS-04** Code → staging branch + CI | `staging/runners/code_runner.py`, `validation/ci/github_actions.py` | Action card shows branch name (mono); per-check links to CI run |
| **MS-08** 24h validation window | `validation/service.py::open_window`, `config.py::validation_window_for` | LoopRing radial countdown; mono `time_remaining_seconds` |
| **MS-15** 24h rollback window | `staging/promotion.py` sets `rollback_window_end` | Rollback countdown chip on PROMOTED action cards |
| **MS-16** Guard-triggered auto-revert | `guards/evaluator.py::evaluate_post_promotion` | Guard proximity bars + toast `guard_rollback` on trip |
| **MS-20** Guard auto-trip | `guards/evaluator.py::evaluate` (rolling rates over MS-14 thresholds) | `/safe-mode` shows guard rates vs thresholds; striped banner appears system-wide |
| **MS-21** In-flight needs human confirm | `domain/transitions.py::assert_can_promote` | Promote dialog explicitly says "Safe Mode active — explicit confirm required" |
| **MS-22** Human-only Safe Mode exit | `safemode/controller.py::exit` (raises `SafeModeHumanRequired`) | Safe Mode toggle confirm dialog requires typed reason; cannot be cleared by any automation |
| **MS-24** Append-only audit, single-query reconstruct | `audit/reconstruct.py::by_action_id` / `by_ticket_id` | `/audit?action=<id>` deep-link reconstructs the full lifecycle |
| **MS-25** Dashboard health metrics | KPI snapshot + sparklines | Overview KPI row: pass/fail rate, rollback rate, mean time-in-validation, expired count, decline rate |
| **MS-26** Engineer + lead notifications | `notifications/sink.py` + emit sites | Toaster with role="alert"/aria-live="assertive" for the four critical events |
| **S1** Quota happy + guard-revert | `tests/mitigation_safety/test_s1_quota_happy_and_revert.py` | Driven via mock; `mockHelpers.tripGuard("capacity_quota")` |
| **S2** Backend defect happy + CI-fail | `tests/mitigation_safety/test_s2_backend_defect.py` | `mockHelpers.fail(action_id)` in the dashboard demo |
| **S3** Window expiry | `tests/mitigation_safety/test_s3_window_expiry.py` | LoopRing reaches zero → breaks → action goes Expired→Reverted |
| **S4** Safe Mode auto-trip | `tests/mitigation_safety/test_s4_safe_mode_autotrip.py` | Striped banner appears; in-flight actions require manual promote |

The complete `MS-01..MS-26` traceability table — every requirement mapped
to its implementing file and verifying test — lives in
[`backend/app/mitigation_safety/README.md`](./backend/app/mitigation_safety/README.md#ms-xx--code--test-traceability-map).

---

## 10. Environment variables

### 10.1 Backend (read in `backend/app/config.py` and across modules)

| Variable | Purpose | Required? | Default |
|---|---|---|---|
| `DATABASE_URL` | Postgres connection (must include pgvector if using ML features) | **yes** | — |
| `JWT_SECRET` | HMAC key for the JWT bearer; refuses to boot if default outside dev | **yes in prod** | `dev_only_change_me` |
| `JWT_ALGORITHM` | JWT signing alg | no | `HS256` |
| `JWT_EXPIRE_MINUTES` | JWT TTL | no | `480` |
| `JWT_AUDIENCE` | Required `aud` claim on every token | no | `sentinel-mitigation-safety` |
| `JWT_ISSUER` | Required `iss` claim on every token | no | `sentinel-<env>` |
| `APP_ENV` | `dev` / `development` / `local` / `test` relax the default-secret guard | no | `dev` |
| `REDIS_URL` | Orchestrator state + dedup + context cache; in-memory if unset | no | — |
| `OPENAI_API_KEY` + `OPENAI_ENDPOINT` + `LLM_MODEL` + `LLM_API_VERSION` | Azure OpenAI for the agents | for the orchestrator | — |
| `EMBEDDING_PROVIDER` + `LOCAL_EMBEDDING_MODEL` + `EMBEDDING_DIM` | Embeddings | no | `local` / `all-MiniLM-L6-v2` / `1536` |
| `BING_SEARCH_API_KEY` + `BING_SEARCH_ENDPOINT` | Web search agent (falls back to DDGS) | no | — |
| `MITIGATION_SAFETY_CONFIG_PATH` | JSON config for windows / thresholds / categories (hot-reloaded; MS-19) | no | defaults in `mitigation_safety/config.py` |
| `MITIGATION_SAFETY_CI_BACKEND` | `github` or `mock` | no | `mock` |
| `MITIGATION_SAFETY_TELEMETRY_BACKEND` | `azure` or `mock` | no | `mock` |
| `GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_WORKFLOW_FILE`, `GITHUB_CI_REF`, `GITHUB_CI_TIMEOUT_SECONDS`, `GITHUB_API_BASE` | Real `GitHubActionsCIRunner`; `GITHUB_API_BASE` allowlisted for SSRF | only when CI backend = github | — |
| `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_MONITOR_WORKSPACE_ID`, `AZURE_MONITOR_TIMEOUT_SECONDS` | Real `AzureMonitorTelemetrySource` | only when telemetry backend = azure | — |
| `NOTIFY_WEBHOOK_URL`, `NOTIFY_WEBHOOK_ALLOWED_HOSTS` | Engineer + lead webhook notifications (SSRF-guarded) | no | logging sink |
| `WEBHOOK_SECRET` | Optional shared secret for the D365 webhook receiver | no | — |
| `DATAVERSE_URL`, `AZURE_*` | Dataverse client credentials for the D365 popup integration | for D365 integration | — |
| `PROBE_DELAY_SECONDS` | Recommendation health-check probe delay | no | `900` |
| `SENDGRID_API_KEY`, `SENDGRID_FROM` | Outbound email | no | — |

### 10.2 Frontend (read by `frontend/`)

| Variable | Purpose | Default |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | FastAPI host; **omit to select the mock** | mock |
| `NEXT_PUBLIC_BRAND` | Product name in the top bar | `Sentinel` |
| `NEXT_PUBLIC_DEFAULT_THEME` | `dark` or `light` | `dark` |
| `NEXT_PUBLIC_REALTIME` | `sse` or `websocket` | `sse` |
| `NEXT_PUBLIC_DEV_BEARER` | Dev-only bearer token (NOT for prod; cookies preferred) | — |

---

## 11. API surface

### 11.1 Mitigation Safety (the six routes from SRS §7)

| Method | Path | Purpose | Auth scope |
|---|---|---|---|
| `POST` | `/tickets/{id}/mitigate/stage` | Apply to staging; open the 24h window | `mitigation:write` |
| `GET`  | `/tickets/{id}/mitigate/validation` | Per-check status + time remaining | `mitigation:read` |
| `POST` | `/tickets/{id}/mitigate/promote` | Promote on PASS (consequence dialog) | `mitigation:promote` |
| `POST` | `/tickets/{id}/mitigate/revert` | Revert (idempotent) | `mitigation:revert` |
| `GET`  | `/mitigation/safe-mode` | System + per-category snapshot | `mitigation:read` |
| `POST` | `/mitigation/safe-mode` | Enter / exit; exit refused for any non-`human:*` actor | `mitigation:safemode` |
| `POST` | `/mitigate/execute` | **410 Gone** — superseded by `stage + promote` | — |
| `POST` | `/mitigate/rollback` | **410 Gone** — superseded by `revert` | — |

All four 4xx statuses map cleanly: `409` for illegal transitions /
scope-isolation / no-revert-handle / not-passed; `423` for Safe Mode hold
or confirm-to-promote required; `403` for non-human Safe Mode exit; `410`
for the shims.

### 11.2 AI Support Agent (orchestrator)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/orchestrator/webhook` | ServiceNow event ingress |
| `POST` | `/orchestrator/d365-webhook` | D365 Power Automate ingress |
| `POST` | `/orchestrator/decision` | Engineer accept/reject of an advisory |
| `GET`  | `/orchestrator/state/{ticket_id}` | Inspect pipeline state |
| `GET`  | `/orchestrator/recommendation?case=...` | HTML for the D365 in-form popup |
| `GET`  | `/orchestrator/feedback?case=...&v=like` | Record 👍 / 👎 + comment |
| `GET`  | `/orchestrator/refine?case=...&comment=...` | Regenerate display-only after feedback |
| `GET`  | `/orchestrator/health` | Liveness |

### 11.3 Domain CRUD (legacy)

`/auth/*`, `/users/*`, `/tickets/*`, `/resolutions/*`, `/mcp/*` — see
[`backend/README.md`](./backend/README.md) and the auto-generated OpenAPI
docs at `http://localhost:8000/docs`.

---

## 12. History & change log

The [`History/`](./History/) directory is durable — every phase of work
records its plan, the issues found, and the fixes applied. Read these in
order for the full archeology:

| File | Phases | What changed |
|---|---|---|
| [`mitigation-safety-staged-rollout-2026-06-17.md`](./History/mitigation-safety-staged-rollout-2026-06-17.md) | F1–F10 | Initial implementation: domain + audit + Safe Mode + validation + staging/promotion/revert + guards + worker + API + 60 tests + frontend MVP + README + first verification sweep |
| [`mitigation-safety-review-remediation-2026-06-17.md`](./History/mitigation-safety-review-remediation-2026-06-17.md) | F11–F18 | End-to-end code review surfaced 48 findings; all 44 remediated (43 fully + 1 partial closed inline). Brings tests to **92 passing**. |
| [`mitigation-safety-dashboard-ui-2026-06-17.md`](./History/mitigation-safety-dashboard-ui-2026-06-17.md) | G1–G9 | Next.js operator dashboard build — G1–G4 complete (tokens + mock + signature primitives + global frame); G5–G9 in progress (routes, tables, dialogs, charts, docs). |

`SRS.md` itself has not changed since draft v1.0 — the work has been
making it real.

---

## 13. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `alembic upgrade head` fails with `relation "tickets" does not exist` | Database is fresh and you're starting from before the legacy baseline | Run `alembic upgrade head` (the `20260617_0000_legacy_baseline` revision creates the legacy schema idempotently). If the legacy schema is already in place, run `alembic stamp 20260617_0000` once, then `alembic upgrade head`. |
| `psycopg2` import error in tests | You're trying to run the orchestrator tests against a clean venv | The mitigation_safety tests don't need psycopg2 (they use SQLite). Install only what you need: `pip install pytest sqlalchemy fastapi httpx python-jose` |
| Backend won't boot in `prod` | `JWT_SECRET` is still `dev_only_change_me` | Set a real secret; `app/auth/jwt.py` deliberately refuses to start with the committed default unless `APP_ENV=dev`/`development`/`local`/`test` |
| Dashboard shows "Safe Mode active" with no obvious reason | Backend boot-time enforcement entered Safe Mode after `apply_immutability` or scheduler failed — that's the fail-loud contract | Check the backend logs for `apply_immutability failed` or `scheduler.start failed`; fix the underlying error, then manually exit Safe Mode via the dashboard `/safe-mode` page |
| `pytest tests/mitigation_safety` fails on `import app.mitigation_safety` | You're running from inside `backend/` instead of repo root | Run from repo root: `cd /Users/isaachernandez/Documents/GitHub/Quest && pytest tests/mitigation_safety -q` |
| Mock dashboard shows nothing | Browser tab needs to refresh after the seed scenario kicks in | Hard-reload (Cmd-Shift-R / Ctrl-Shift-R) once after `npm run dev` boots |

---

## License & contact

Internal product, no external license. Questions: open an item in the
repo issue tracker or message the team channel.

For the safety model itself, [`SRS.md`](./SRS.md) is the source of truth.
For the implementation, [`backend/app/mitigation_safety/README.md`](./backend/app/mitigation_safety/README.md)
carries the MS-xx → code/test map.
