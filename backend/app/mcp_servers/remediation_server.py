"""
Remediation MCP server (Phase 1).

Exposes the auto-remediation runbooks + the safety gate as MCP tools, wrapping
the existing mitigation code. This is the server where, in production (Phase 3),
the SIMULATED actions are replaced with real Graph / SQL / Defender connectors
and the gate + least-privilege auth + audit are enforced centrally.

Run standalone:  python -m app.mcp_servers.remediation_server
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.orchestrator.mitigation import (
    RECIPES, _RECIPE_BY_KEY, match_recipe, assess, execution_trace,
)

mcp = FastMCP("remediation")


@mcp.tool()
def list_runbooks() -> list:
    """List the available auto-remediation runbooks."""
    return [{"key": r["key"], "name": r["name"], "tier": r["tier"],
             "reversible": r["reversible"]} for r in RECIPES]


@mcp.tool()
def match_runbook(title: str, description: str = "") -> dict:
    """Does this case match a known runbook (by signature)? Returns the matched
    runbook, or {"matched": false} for an unknown problem (-> suggest-only)."""
    r = match_recipe({"title": title, "description": description})
    if not r:
        return {"matched": False}
    return {"matched": True, "key": r["key"], "name": r["name"],
            "tier": r["tier"], "reversible": r["reversible"]}


@mcp.tool()
def assess_remediation(title: str, description: str,
                       precedent_match: float, confidence: float) -> dict:
    """Run the safety GATE: should this case be auto-remediated? Auto-execute
    only if confidence >= 0.85 AND precedent match >= 0.80 AND reversible AND
    Tier A. Returns the full decision (gate_passed + reason)."""
    similar = [{"display_score": precedent_match, "ticket_number": "precedent"}] if precedent_match else []
    return assess({"title": title, "description": description}, similar, confidence)


@mcp.tool()
def run_runbook(key: str) -> dict:
    """Execute a runbook's fixed steps. The external actions are SIMULATED in
    this POC (a real connector executes them in production). Returns the trace."""
    r = _RECIPE_BY_KEY.get(key)
    if not r:
        return {"error": f"unknown runbook '{key}'"}
    return {"runbook": r["name"], "executed": execution_trace(r), "verify": r["verify"],
            "note": "external actions simulated in this POC; a real connector executes them in production"}


if __name__ == "__main__":
    mcp.run()
