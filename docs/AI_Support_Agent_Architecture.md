# AI Support Agent for Dynamics 365 — Architecture (POC)

**What it does:** When a support Case is created in Dynamics 365, the system automatically
analyzes it against the team's real case history and posts a grounded recommendation — team,
root cause, similar past incidents, a quick fix and a permanent fix, and reference links —
directly into the Case, with a one-click 👍/👎. Runs 24/7, hands-off.

---

## Architecture

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                     DYNAMICS 365 — Customer Service                        │
 │   Cases (system of record)  •  AI note on the Case timeline  •  pop-up     │
 └──────────▲───────────────────────────────────────────────────▲───────────┘
            │ (1) detect new Case / (6) write recommendation back │ (7) pop-up
            │     (Dataverse Web API)                             │   on click / on load
 ┌──────────┴──────────────────────────────────────────────────────────────┐
 │      ORCHESTRATOR SERVICE  —  FastAPI on Render (Python, no database)     │
 │                                                                          │
 │   Poller (every ~1–2 min)  ─►  Pipeline  ─►  one consolidated note        │
 │                                                                          │
 │     (2) Similarity     embed the Case + history, find the closest cases  │
 │     (3) Routing agent  which support team should own it                  │
 │     (4) Diagnosis      root cause + the similar past incidents           │
 │     (5) Recommendation hot fix + ultimate fix + real reference links     │
 │                                                                          │
 │   APIs:  /health   /recommendation (pop-up)   /feedback (👍/👎)          │
 └──────────▲────────────────────────────────▲─────────────────────────────┘
            │ gpt-4o + embeddings             │ live reference links
     ┌──────┴───────┐                 ┌───────┴────────────┐
     │ Azure OpenAI │                 │ Microsoft Learn API│
     └──────────────┘                 └────────────────────┘
```

## The flow (Case → recommendation)

1. **Poller** detects a new Case in Dynamics 365.
2. **Similarity** — turns the Case + the case history into vectors and finds the closest past cases.
3. **Routing agent** — recommends the right support team.
4. **Diagnosis agent** — determines the root cause and surfaces the similar past incidents.
5. **Recommendation agent** — produces a **Hot fix** (restore now) and an **Ultimate fix** (permanent), plus **real Microsoft Learn links**.
6. The orchestrator **binds all of it into one note** and writes it onto the Case.
7. The engineer sees it instantly, can **👍/👎** it, and can open the full **pop-up** from a button — or it auto-pops when ready.

## Technology
- **Dynamics 365 Customer Service** — front end + system of record
- **FastAPI / Python** on **Render** — the orchestrator service (stateless, no database)
- **Azure OpenAI** — `gpt-4o` (reasoning) + embeddings (similarity)
- **Microsoft Learn search API** — real, live reference links (no key)
- **Dataverse Web API** — read Cases / write notes

## Why this design
- **No new infrastructure** — Dynamics 365 is the store; the service is stateless and low-cost.
- **Grounded in real data** — recommendations cite the team's actual past cases, not generic examples.
- **Always-on** — the poller runs continuously; new Cases are handled automatically.
- **Resilient** — every step degrades safely; a single failure never breaks the pipeline.
- **Scales later** — in-memory similarity now; a vector database only if the case volume grows large.

## Status — working & deployed
- ✅ End-to-end automation live on Render (new Case → recommendation in ~30–60s)
- ✅ Recommendation grounded in real cases, with clickable incidents + live reference links
- ✅ In-Case note + one-click 👍/👎 feedback
- ✅ Pop-up dialog in Dynamics (button + auto-open)
