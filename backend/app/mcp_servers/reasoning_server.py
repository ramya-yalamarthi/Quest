"""
Reasoning MCP server (Phase 1).

Exposes the three reasoning agents -- Routing, Diagnosis, Recommendation -- as
governed MCP tools, so the orchestration engine drives ALL capabilities through
one tool boundary (alongside dataverse / knowledge), instead of calling the
agent classes directly.

The agents take a `context` dict (event payload + similar cases + optional prior
diagnosis + engineer feedback). In-process the engine hands that context across
as JSON; over HTTP/stdio the same JSON crosses the wire -- identical result.

Run standalone:  python -m app.mcp_servers.reasoning_server
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from app.orchestrator.agents import (
    RoutingAgent, DiagnosisAgent, RecommendationAgent,
)
from app.mcp_servers._runtime import run_server

mcp = FastMCP("reasoning")


def _ctx(context_json) -> dict:
    """Accept either a JSON string (real MCP transport) or a dict (in-process)."""
    if isinstance(context_json, str):
        try:
            return json.loads(context_json)
        except Exception:
            return {}
    return context_json or {}


@mcp.tool()
def route_case(context_json: str) -> dict:
    """Decide the correct support team for the case. Read-only reasoning; never
    writes. `context_json` is the orchestration context (event payload + similar
    cases)."""
    return RoutingAgent().run(_ctx(context_json))


@mcp.tool()
def diagnose_case(context_json: str) -> dict:
    """Diagnose the likely root cause, grounded in the cited similar cases.
    Read-only reasoning."""
    return DiagnosisAgent().run(_ctx(context_json))


@mcp.tool()
def recommend_case(context_json: str) -> dict:
    """Recommend the hot fix + ultimate fix + official reference links, grounded
    in the diagnosis and similar cases. Read-only reasoning."""
    return RecommendationAgent().run(_ctx(context_json))


if __name__ == "__main__":
    run_server(mcp, default_port=8104)
