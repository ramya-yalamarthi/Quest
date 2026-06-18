# MCP layer (Phase 1)

This is the **MCP (Model Context Protocol) version** of the AI Support Agent's
integrations. It is **additive** — it wraps the *same* code the live pipeline
uses and exposes it as standardized, discoverable **MCP tools**. The live
webhook/pipeline is untouched.

## Why
Today the orchestrator imports and calls each integration directly. With MCP,
each capability becomes a **server exposing tools**, and the agent **discovers
and calls them** over one protocol. This decouples the integrations, is the
foundation for *real, governed* remediation, and makes the tools reusable by
other agents (e.g. Microsoft Copilot Studio, which supports MCP).

## The 3 servers (wrap existing code)
| Server | Wraps | Tools |
|---|---|---|
| `dataverse_server.py` | `orchestrator/dataverse.py` + `similarity.py` | `list_cases`, `get_case`, `find_similar_cases`, `write_note`, `close_incident`, `advance_bpf` |
| `knowledge_server.py` | `orchestrator/web_refs.py` | `search_docs` |
| `remediation_server.py` | `orchestrator/mitigation.py` | `list_runbooks`, `match_runbook`, `assess_remediation`, `run_runbook` |

The **client** (`app/mcp_client/agent_runner.py`) is the agent: it connects to
the servers, discovers their tools, and processes a Case through them.

## Run the demo
(from `backend/`, with `DATAVERSE_*` and `EMBEDDING_*` env vars set)

**Reliable on any OS (recommended for a local walkthrough):**
```
python -m app.mcp_client.demo_inprocess
```

**Real over-the-wire MCP transport (stdio subprocess) — works on Linux/Render:**
```
python -m app.mcp_client.agent_runner
```
> ⚠️ On **Windows**, `agent_runner` does real MCP **discovery** fine, but the
> stdio subprocess transport can break (`anyio.BrokenResourceError`) during the
> ~10s embeddings call — a known MCP/anyio Windows limitation, not a code issue.
> Use `demo_inprocess` on Windows (it calls the *same* MCP tools in-process).

Both run one Case end-to-end:
`find_similar_cases → match_runbook → assess (gate) → run_runbook → search_docs`.

## The flow
```
Agent (MCP client)
  ├─ dataverse.find_similar_cases   -> closest past cases
  ├─ remediation.match_runbook      -> recipe or none
  ├─ remediation.assess_remediation -> safety gate (auto vs suggest)
  ├─ remediation.run_runbook        -> execute (external steps SIMULATED)
  └─ knowledge.search_docs          -> official doc link
```

## Phases 2–4 (built)

### Phase 2 — model-driven tool-calling  (`app/mcp_client/tool_calling_agent.py`)
The MODEL (gpt-4o) decides which tools to call, in what order, via a reason-act
loop. The MCP tools are bridged to OpenAI function schemas. The safety gate is
enforced server-side (`assess_remediation`) — the model can request a remediation
but cannot bypass the gate.
```
python -m app.mcp_client.tool_calling_agent      # runs with a stub LLM locally
```
> Live tool-selection needs gpt-4o (runs on Render); the loop + bridge are local-testable with the stub.

### Phase 3 — governed remediation  (`app/mcp_servers/connectors.py`)
Each runbook action runs through a **connector** that declares its **least-privilege
scope** and is audited. The runbook **tier** decides the flow:
- **Tier A** → auto-execute via connectors
- **Tier B** → prepare actions + **require human approval**
- **Tier C** → **human-only**

Connectors are **simulated** today; registering a real Graph/SQL/Defender
implementation in `connectors.register(...)` makes it live — nothing else changes.
This is the seam to wire real, scoped access when Microsoft grants it.

### Phase 4 — HTTP transport for Copilot reuse  (`app/mcp_servers/_runtime.py`)
Each server can run over **streamable-HTTP** so it's registerable in Copilot
Studio / Azure AI Foundry and reusable by other agents:
```
# stdio (default, local agent)
python -m app.mcp_servers.dataverse_server
# HTTP (network / registerable)
MCP_TRANSPORT=http MCP_PORT=8101 python -m app.mcp_servers.dataverse_server
```
**Register in Copilot Studio:** add a Tool → MCP server → point it at the server's
HTTP URL (e.g. `http://<host>:8101/mcp`). Copilot then discovers the tools and can
call them — the same `find_similar_cases` / `run_runbook` tools this agent uses.

> All phases are additive scaffolds. They do not replace the deployed webhook
> pipeline, which still runs on the proven direct-integration path. The remaining
> gaps to go fully live are EXTERNAL (gpt-4o for Phase 2, real connectors for
> Phase 3, a Copilot Studio environment for Phase 4) — not code.
