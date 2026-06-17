"""
MCP client (WBS tasks O-05 context, O-08 MCP integration).

The supervisor calls the Day-3 MCP service for all ticket data and for posting
advisory comments back to the ticket.  Until that service exists, this mock
returns deterministic fake data so the whole pipeline runs.

Swap MockMCPClient for a real HTTP client (same method names) when Day-3 lands.
"""

from typing import Protocol


class MCPClient(Protocol):
    def ticket_context_fetch(self, ticket_id: str) -> dict: ...
    def similarity_search(self, text: str, top_k: int = 5) -> list[dict]: ...
    def telemetry_query(self, ticket_id: str, time_window: str = "1h") -> dict: ...
    def gold_layer_lookup(self, ticket_id: str) -> dict: ...
    def post_icm_comment(self, ticket_id: str, agent_name: str, payload: dict) -> str: ...
    def update_ticket_status(self, ticket_id: str, **changes) -> bool: ...


class MockMCPClient:
    """Stand-in for the Day-3 MCP service. Prints comments instead of calling D365."""

    def ticket_context_fetch(self, ticket_id: str) -> dict:
        return {
            "ticket_id": ticket_id,
            "title": "[mock] Storage latency spike in East-US",
            "description": "[mock] Customer reports intermittent 5xx and high TTFB.",
            "assigned_team": "Networking",
            "severity": "P2",
            "reactivation_count": 0,
        }

    def similarity_search(self, text: str, top_k: int = 5) -> list[dict]:
        return [
            {"ticket_id": "past-001", "score": 0.91, "team": "Storage", "resolution": "Throttling rule reset"},
            {"ticket_id": "past-002", "score": 0.88, "team": "Storage", "resolution": "Cache node restart"},
        ][:top_k]

    def telemetry_query(self, ticket_id: str, time_window: str = "1h") -> dict:
        return {"ticket_id": ticket_id, "window": time_window, "error_rate": 0.07, "p99_ms": 1840}

    def gold_layer_lookup(self, ticket_id: str) -> dict:
        # In the no-Fabric build this becomes a plain Postgres query.
        return {
            "avg_ttm_minutes": {"Storage": 95, "Networking": 140},
            "common_root_causes": ["throttling", "cache eviction"],
            "runbook_refs": ["RB-STORAGE-014"],
        }

    def post_icm_comment(self, ticket_id: str, agent_name: str, payload: dict) -> str:
        comment_id = f"cmt-{agent_name}-{ticket_id[:8]}"
        print(f"    [MCP] posted {agent_name} advisory to ticket {ticket_id} "
              f"-> {payload.get('title', '(advisory)')}  ({comment_id})")
        return comment_id

    def update_ticket_status(self, ticket_id: str, **changes) -> bool:
        print(f"    [MCP] update ticket {ticket_id}: {changes}")
        return True
