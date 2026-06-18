"""
Knowledge MCP server (Phase 1).

Exposes documentation search as an MCP tool, wrapping the existing web_refs code
(official-docs-only search, Q&A/forum/blog filtered out).

Run standalone:  python -m app.mcp_servers.knowledge_server
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.orchestrator.web_refs import search_refs, is_official_doc

mcp = FastMCP("knowledge")


@mcp.tool()
def search_docs(query: str, count: int = 2) -> list:
    """Search OFFICIAL product documentation for this problem. Q&A / forum / blog
    pages are excluded. Returns [{title, url, source}]."""
    refs = search_refs(query, count=max(count * 2, 4))
    return [r for r in refs if is_official_doc(r.get("url", ""))][:count]


if __name__ == "__main__":
    from app.mcp_servers._runtime import run_server
    run_server(mcp, default_port=8102)
