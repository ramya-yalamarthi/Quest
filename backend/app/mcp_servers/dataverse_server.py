"""
Dataverse MCP server (Phase 1).

Exposes the Dynamics 365 / Dataverse capabilities the agent needs as MCP tools.
Each tool is a thin wrapper over the EXISTING DataverseClient + similarity code,
so behaviour is identical to the live pipeline -- only the interface changes
(direct import  ->  discoverable MCP tool).

Run standalone:  python -m app.mcp_servers.dataverse_server
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.orchestrator.dataverse import DataverseClient
from app.orchestrator.similarity import rank_similar

mcp = FastMCP("dataverse")


@mcp.tool()
def list_cases(top: int = 100) -> list:
    """Return recent Cases from Dynamics 365 (id, ticket_number, title, description, state)."""
    return DataverseClient().list_cases(top=top)


@mcp.tool()
def get_case(case_id: str) -> dict:
    """Fetch one Case by its GUID."""
    return DataverseClient().get_case(case_id) or {}


@mcp.tool()
def find_similar_cases(title: str, description: str = "", top_k: int = 4) -> list:
    """Semantic search: find the past Cases most similar to this title/description.
    Returns each match with its raw score and calibrated relevance (display_score)."""
    client = DataverseClient()
    corpus = client.list_cases(top=100)
    query = {"id": "_query", "ticket_number": "_query", "title": title, "description": description}
    matches = rank_similar(query, corpus, top_k=top_k, min_score=0.2)
    return [{"ticket_number": m.get("ticket_number"), "title": m.get("title"),
             "score": m.get("score"), "display_score": m.get("display_score"),
             "state": m.get("state")} for m in matches]


@mcp.tool()
def write_note(case_id: str, text: str) -> str:
    """Write the AI recommendation Note onto a Case. Returns the new note id."""
    return DataverseClient().create_case_note(case_id, "AI Support Recommendation", text) or ""


@mcp.tool()
def close_incident(case_id: str, subject: str = "Auto-resolved by AI agent", text: str = "") -> bool:
    """Resolve + close a Case in Dynamics 365 (the real auto-remediation action)."""
    return DataverseClient().close_incident(case_id, subject, text)


@mcp.tool()
def advance_bpf(case_id: str) -> bool:
    """Advance the Phone-to-Case business process flow to its Resolve stage."""
    return DataverseClient().advance_bpf_to_resolve(case_id)


if __name__ == "__main__":
    mcp.run()
