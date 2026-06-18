"""
MCP-based orchestration engine (deterministic).

Same pipeline as `d365_runner.process_case` -- routing -> diagnosis ->
recommendation -> references -> confidence blend -> mitigation safety gate ->
one bound note -- but the reasoning + knowledge capabilities are driven through
the MCP tool boundary (the reasoning / knowledge servers) instead of calling the
agent classes directly.

Why this is safe and deterministic:
  * It REUSES process_case verbatim, injecting MCP-tool-backed capabilities via
    the function's existing `agents` / `ref_search_fn` hooks. The orchestration,
    confidence blend, grounding cap, mitigation gate and note formatting are the
    SAME code -- so the output is identical to the legacy engine by construction
    (no drift), the tool order is fixed, and the safety gate is always evaluated.
  * The only change is the call PATH: each reasoning agent runs behind its MCP
    tool (context serialised to JSON -- the real tool boundary), so the live
    engine and the tools registered for Copilot Studio (Phase 4) are one and the
    same governed surface.

Transport: in-process (we import the tool callables directly). The identical
tools also run over stdio/HTTP for external reuse; we use the in-process path
live because Windows stdio is flaky for long-running calls.
"""

from __future__ import annotations

import json
from typing import Callable, Optional

from app.orchestrator import d365_runner
from app.mcp_servers import reasoning_server, knowledge_server


def _fn(tool):
    """Underlying callable of an @mcp.tool()-registered function (in-process)."""
    return getattr(tool, "fn", tool)


_route = _fn(reasoning_server.route_case)
_diagnose = _fn(reasoning_server.diagnose_case)
_recommend = _fn(reasoning_server.recommend_case)
_search_docs = _fn(knowledge_server.search_docs)


class _MCPToolAgent:
    """Drop-in for an Agent: runs the reasoning THROUGH its MCP tool. The context
    is serialised to JSON (the real tool boundary) and the tool returns the dict
    -- so in-process and over-the-wire behave identically."""

    def __init__(self, tool_fn: Callable):
        self._tool_fn = tool_fn

    def run(self, context: dict) -> dict:
        return self._tool_fn(json.dumps(context))


def _mcp_ref_search(query: str, count: int = 4) -> list:
    """Reference-doc search routed through the knowledge MCP server."""
    return _search_docs(query=query, count=count)


def process_case_mcp(
    case: dict,
    corpus: list,
    org_base: str = "",
    feedback_base: str = "",
    top_k: int = 4,
    min_score: float = 0.2,
    embed_fn: Optional[Callable] = None,
    agents: Optional[dict] = None,          # accepted for signature parity / tests
    ref_search_fn: Optional[Callable] = None,
    link_validate_fn: Optional[Callable] = None,
    feedback: str = "",
) -> tuple:
    """Deterministic MCP engine. Identical contract + output to
    `d365_runner.process_case`; the reasoning + knowledge capabilities are driven
    through the MCP tool boundary. Returns (advisory, note)."""
    mcp_agents = {
        "routing": _MCPToolAgent(_route),
        "diagnosis": _MCPToolAgent(_diagnose),
        "recommendation": _MCPToolAgent(_recommend),
    }
    return d365_runner.process_case(
        case, corpus,
        org_base=org_base,
        feedback_base=feedback_base,
        top_k=top_k,
        min_score=min_score,
        embed_fn=embed_fn,
        agents=mcp_agents,
        ref_search_fn=ref_search_fn if ref_search_fn is not None else _mcp_ref_search,
        link_validate_fn=link_validate_fn,
        feedback=feedback,
    )
