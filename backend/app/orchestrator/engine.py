"""
Orchestration engine selector (the fallback flag).

    ENGINE=mcp      -> the deterministic MCP engine (reasoning driven through the
                       MCP tool boundary -- app.orchestrator.mcp_engine)
    ENGINE=legacy   -> the original in-process engine (default)

Both produce the SAME (advisory, note) -- the MCP engine reuses process_case and
only changes the call path -- so flipping the flag is risk-free. We keep legacy
as the default through the demo so we can fall back instantly; once the MCP path
is proven in production we flip the default to `mcp` and retire legacy.
"""

from __future__ import annotations

import logging
import os


def engine_name() -> str:
    return (os.getenv("ENGINE", "legacy").strip().lower() or "legacy")


def select_engine():
    """Return the process_case-compatible callable for the configured engine.

    Fails SAFE: if ENGINE=mcp but the MCP layer can't be imported (e.g. the `mcp`
    package isn't installed in a slim deploy), we fall back to the legacy engine
    instead of erroring -- the webhook keeps working."""
    if engine_name() == "mcp":
        try:
            from app.orchestrator.mcp_engine import process_case_mcp
            return process_case_mcp
        except Exception:
            logging.getLogger(__name__).warning(
                "ENGINE=mcp requested but MCP layer unavailable; using legacy engine")
    from app.orchestrator.d365_runner import process_case
    return process_case
