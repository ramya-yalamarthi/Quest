# MCP layer

This is the **MCP (Model Context Protocol) version** of the AI Support Agent's
capabilities. It wraps the *same* code the live pipeline uses and exposes it as
standardized, discoverable **MCP tools**, so the reasoning + integration work is
driven through one governed tool boundary — and is reusable by other agents
(e.g. Microsoft Copilot Studio, which supports MCP).

## Why
Instead of the orchestrator importing and calling each capability directly, each
becomes a **server exposing tools**, discovered and called over one protocol.
This decouples the capabilities and makes them reusable across agents.

## The 3 servers (wrap existing code)
| Server | Wraps | Tools |
|---|---|---|
| `dataverse_server.py` | `orchestrator/dataverse.py` + `similarity.py` | `list_cases`, `get_case`, `find_similar_cases`, `write_note` |
| `knowledge_server.py` | `orchestrator/web_refs.py` | `search_docs` |
| `reasoning_server.py` | `orchestrator/agents.py` | `route_case`, `diagnose_case`, `recommend_case` |

## The live engine runs on these tools
`app/orchestrator/mcp_engine.py` (selected by `ENGINE=mcp`) reuses
`process_case` and drives the reasoning + knowledge capabilities through the MCP
tool boundary above — identical output to the legacy engine, just routed through
the governed tools. The flow:
```
dataverse.find_similar_cases  -> closest past cases
reasoning.route_case          -> team / queue
reasoning.diagnose_case       -> root cause (grounded in the similar cases)
reasoning.recommend_case      -> hot fix + ultimate fix + links
knowledge.search_docs         -> official doc link (backfill)
```

## Transport for Copilot reuse  (`app/mcp_servers/_runtime.py`)
Each server can run over **stdio** (local) or **streamable-HTTP** (network), so
it's registerable in Copilot Studio / Azure AI Foundry and reusable by other
agents:
```
# stdio (default, local agent)
python -m app.mcp_servers.reasoning_server
# HTTP (network / registerable)
MCP_TRANSPORT=http MCP_PORT=8104 python -m app.mcp_servers.reasoning_server
```
**Register in Copilot Studio:** add a Tool → MCP server → point it at the
server's HTTP URL (e.g. `http://<host>:8104/mcp`). Copilot then discovers the
tools and can call them — the same tools the live engine uses.

> Live, the engine uses the **in-process** path (it imports the tool callables
> directly) because Windows stdio is flaky for long-running calls; the identical
> tools also run over stdio/HTTP for external reuse.
