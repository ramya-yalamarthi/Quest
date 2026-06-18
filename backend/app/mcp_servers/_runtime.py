"""
Phase 4 — transport runtime.

Lets each MCP server run over either stdio (local agent) or HTTP (network), so the
SAME server can be registered in Microsoft Copilot Studio / Azure AI Foundry and
reused by other agents.

    MCP_TRANSPORT=stdio   (default)  -> local subprocess transport
    MCP_TRANSPORT=http               -> streamable-HTTP on MCP_HOST:MCP_PORT

Each server passes a default port so the three can run side by side.
"""

from __future__ import annotations

import os


def run_server(mcp, default_port: int) -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()
    if transport in ("http", "streamable-http", "streamable_http"):
        try:
            mcp.settings.host = os.getenv("MCP_HOST", "127.0.0.1")
            mcp.settings.port = int(os.getenv("MCP_PORT", str(default_port)))
        except Exception:
            pass
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
