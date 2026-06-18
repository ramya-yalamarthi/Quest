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

## Roadmap (beyond Phase 1)
- **Phase 2** — let the LLM choose tools (model-driven tool calling) instead of a fixed sequence.
- **Phase 3** — replace the SIMULATED remediation with real **Graph / SQL / Defender** connectors behind a **least-privilege** identity + the approval gate (this is where auto-remediation becomes real and governed).
- **Phase 4** — register the servers in **Copilot Studio / Azure AI Foundry** so other agents reuse them.

> Phase 1 is a scaffold/demonstration. It does not replace the deployed webhook
> pipeline — that still runs on the proven direct-integration path.
