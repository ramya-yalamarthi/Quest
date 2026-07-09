# Project Quest — AI Insights for D365 Customer Service

## What this project is

An AI-powered support assistant embedded inside **Dynamics 365 Customer Service** as a web resource popup. When an agent opens a support ticket (Case), the popup auto-loads and shows:

- **Incident Trends** — how many similar cases this week / month / quarter
- **Current Issue + Probable Cause** — AI diagnosis grounded in past resolved cases
- **Missing Information Detected** — domain-aware checklist (Finance vs Kubernetes)
- **Knowledge Base Recommendations** — top matching KB articles with success rates
- **Suggested Workflow** — step-by-step resolution guide (toggle button)
- **Recommended Assignment** — best engineer from the roster (L1/L2/L3)
- **L1 → L2 → L3 Escalation** — manual escalation buttons with full context notes
- **Generate Customer Email** — draft email asking for missing info

## Architecture (no database, no embeddings needed)

```
D365 Case opens
    └─▶ new_airec_dialog.html (D365 web resource)
           ├─▶ GET /orchestrator/recommendation-data?case={id}   ← structured JSON for cards
           └─▶ GET /orchestrator/recommendation?case={id}        ← cached HTML note

Backend: FastAPI on Render (https://quest-z7e4.onrender.com)
  ├── similarity.py        — Jaccard keyword fallback (no OpenAI needed)
  ├── kb_catalog.py        — static KB articles, domain-aware (Finance vs K8s)
  ├── workflows.py         — step-by-step workflows, Finance FIRST then Kubernetes
  ├── roster.py            — engineer roster from engineer_roster.xlsx
  ├── dataverse.py         — Dataverse API client (cases, notes, queues)
  └── finance_ai.py        — D365 Finance OData question answering (optional)
```

## Two domains supported

### Kubernetes / Karpenter (original domain)
- Cases prefixed `[k8s]` imported from GitHub via `scripts/import_github_issues.py`
- ~200+ cases spread across week/month/quarter via `scripts/spread_demo_dates.py`
- KB articles: NodePool quota, Pods Pending, Autoscaler, Node drain, EC2NodeClass, Metrics, Networking
- Engineers: Kubernetes L1/L2/L3 team

### D365 Finance (new domain — Phase 1 complete)
- Cases prefixed `[fin]` imported via `scripts/import_finance_issues.py 200`
- 200 cases (1001–1200) spread via `scripts/spread_finance_dates.py`
- Covers: AP, GL, AR, Fixed Assets, Inventory/SCM, Tax, Batch Jobs, Budgeting, Project, Bank, Cost Accounting, Consolidation, HR, Compliance, Multi-currency
- KB articles: Vendor invoices, GL journals, Fixed Assets, AR settlement, DMF import, Inventory
- Engineers: Finance L1 (Priya Sharma/AP, Ravi Nair/AR, Meera Pillai/Inventory), L2 (Anand Krishnan/GL, Divya Menon/AP, Karthik Rajan/Batch), L3 (Suresh Babu/GL, Lakshmi Narayanan/Batch)

## Key files

| File | Purpose |
|------|---------|
| `backend/d365/new_airec_dialog.html` | The popup UI — must be manually re-uploaded to D365 after every change |
| `backend/app/api/routers/orchestrator.py` | Main API endpoints (`/recommendation-data`, `/recommendation`, escalation, etc.) |
| `backend/app/orchestrator/similarity.py` | Keyword-based Jaccard similarity fallback (no OpenAI needed) |
| `backend/app/orchestrator/kb_catalog.py` | 14 KB articles (6 Finance + 8 Kubernetes), domain-aware matching |
| `backend/app/orchestrator/workflows.py` | Workflows — Finance entries come FIRST to prevent keyword collision with K8s |
| `backend/app/orchestrator/roster.py` | Engineer team aliases and skill matching |
| `backend/app/orchestrator/dataverse.py` | Dataverse API — uses `overriddencreatedon` for date spread |
| `backend/app/orchestrator/finance_ai.py` | Finance OData question answering (needs FINANCE_URL env var) |
| `backend/app/orchestrator/finance_odata.py` | D365 Finance OData client |
| `backend/data/engineer_roster.xlsx` | All engineers with level, team, skills |
| `backend/scripts/finance_issues.json` | 200 Finance support tickets (offline snapshot) |
| `backend/scripts/import_finance_issues.py` | Import Finance cases into D365 (`python3 scripts/import_finance_issues.py 200`) |
| `backend/scripts/import_github_issues.py` | Import Kubernetes cases into D365 |
| `backend/scripts/spread_finance_dates.py` | Spread `[fin]` case dates (15% week / 35% month / 50% quarter) |
| `backend/scripts/spread_demo_dates.py` | Spread `[k8s]` case dates (same pattern) |
| `backend/scripts/seed_kb_articles.py` | Seed KB articles into D365 (both K8s and Finance) |

## Git / Deployment

- **Branch**: `Ramya-safety` (local) → pushed as `Ramya` branch on GitHub
- **Push command**: `git push origin Ramya-safety:Ramya`
- **Backend**: Auto-deploys to Render on push to `Ramya` branch (~2 min)
- **Frontend**: `new_airec_dialog.html` must be manually re-uploaded to D365:
  `make.powerapps.com → Solutions → [solution] → Web Resources → new_airec_dialog → Upload → Save → Publish`

## Credentials / Environment

- `backend/.env` — contains live Dataverse secrets — **NEVER commit this file**
- Required env vars: `DATAVERSE_URL`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`
- Optional: `FINANCE_URL` (for live Finance OData), `OPENAI_API_KEY` (for LLM; system works without it via keyword fallback)
- SSL fix needed on macOS when running scripts locally: `SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())") python3 scripts/...`

## Security constraints — never violate

- `backend/.env` must NEVER be committed
- Stray untracked files (`# CLARA explanation.md`, `docs/*.pptx`, `docs/*.pdf`) must NOT be committed
- Only commit specific named files, never `git add -A` or `git add .`

## D365 environment

- Org URL: `orgc409312b.crm.dynamics.com`
- The AI note is written to the Case timeline as an annotation with subject `"AI Support Recommendation"`
- The popup fetches this cached note; if none exists, it generates one on the fly (display only)
- Cases are queued to `AI_ROUTED` queue after processing
- Domain detection: Finance keywords (vendor invoice, fiscal period, accounts payable, etc.) → Finance domain; else → Kubernetes domain

## Domain detection logic (in orchestrator.py)

```python
finance_kws = ["general ledger", "accounts payable", "accounts receivable", "fixed asset",
               "voucher", "ledger", "fiscal period", "d365 finance", "dynamics finance",
               "journal posting", "vendor invoice", "customer invoice", "depreciation",
               "inventory", "bill of materials", " gl ", " ap ", " ar "]
```

## Escalation flow

1. **No escalation**: AI shows "Assign to L2 Engineer" button (purple)
2. **L2 assigned**: Purple banner shows L2 engineer + red "Escalate to L3" button
3. **L3 assigned**: Red banner shows L3 engineer (final, no further escalation)

## Running scripts locally (with SSL fix)

```bash
cd backend

# Import Finance cases (200)
SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())") python3 scripts/import_finance_issues.py 200

# Spread Finance case dates
SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())") python3 scripts/spread_finance_dates.py

# Spread Kubernetes case dates
SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())") python3 scripts/spread_demo_dates.py
```

## What is NOT done yet (future phases)

- Phase 2: Power Platform domain (Power Automate, Power Apps, Power BI)
- Phase 3: Azure Infrastructure domain (VMs, AKS, Storage, Networking)
