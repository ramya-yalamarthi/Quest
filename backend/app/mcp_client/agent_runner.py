"""
MCP client / agent (Phase 1).

This is the orchestrator re-expressed as an MCP CLIENT: instead of importing the
integration code directly, it CONNECTS to the three MCP servers, DISCOVERS their
tools, and CALLS them to process a Case. Same underlying logic as the live
pipeline -- the difference is the standardized, decoupled tool interface.

Run a demo:  python -m app.mcp_client.agent_runner
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# backend/ root, so the spawned servers can `import app...`
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SERVERS = {
    "dataverse": "app.mcp_servers.dataverse_server",
    "knowledge": "app.mcp_servers.knowledge_server",
    "remediation": "app.mcp_servers.remediation_server",
}


def _params(module: str) -> StdioServerParameters:
    env = dict(os.environ)
    env["PYTHONPATH"] = _ROOT + os.pathsep + env.get("PYTHONPATH", "")
    return StdioServerParameters(command=sys.executable, args=["-m", module], env=env)


def _parse(res):
    text = res.content[0].text if res.content else "null"
    try:
        return json.loads(text)
    except Exception:
        return text


async def run_case(title: str, description: str):
    # Open ONE persistent session per server (open once, call many, close once at
    # the end). All results print BEFORE cleanup, so a slow Windows stdio teardown
    # can't hide the output.
    async with AsyncExitStack() as stack:
        sess = {}
        for name, module in SERVERS.items():
            read, write = await stack.enter_async_context(stdio_client(_params(module)))
            s = await stack.enter_async_context(ClientSession(read, write))
            await s.initialize()
            sess[name] = s

        async def call(server, tool, args):
            res = await asyncio.wait_for(sess[server].call_tool(tool, args), timeout=60)
            return _parse(res)

        print("=" * 72)
        print("MCP CLIENT — discovering tools across the 3 servers")
        print("=" * 72)
        for name, s in sess.items():
            tools = await s.list_tools()
            print(f"  {name:12} -> {[t.name for t in tools.tools]}")

        print("\n" + "=" * 72)
        print(f"PROCESSING CASE:  {title}")
        print("=" * 72)

        similar = await call("dataverse", "find_similar_cases", {"title": title, "description": description})
        top = similar[0]["display_score"] if similar else 0.0
        print("1. dataverse.find_similar_cases ->")
        for s in similar[:3]:
            print(f"     {round((s.get('display_score') or 0)*100)}%  {s['ticket_number']}  {(s.get('title') or '')[:48]}")

        match = await call("remediation", "match_runbook", {"title": title, "description": description})
        print("2. remediation.match_runbook ->", match)

        if match.get("matched"):
            decision = await call("remediation", "assess_remediation",
                                  {"title": title, "description": description,
                                   "precedent_match": top, "confidence": 0.95})
            gate = "PASS -> auto-remediate" if decision.get("gate_passed") else "fail -> suggest-only"
            print(f"3. remediation.assess_remediation (gate) -> {gate}  [{decision.get('gate_reason')}]")
            if decision.get("gate_passed"):
                run = await call("remediation", "run_runbook", {"key": match["key"]})
                print("4. remediation.run_runbook ->")
                for line in run.get("executed", []):
                    print("     ", line)
                print("     (", run.get("note"), ")")
        else:
            print("3. no runbook matched -> SUGGEST-ONLY (a human handles it)")

        docs = await call("knowledge", "search_docs", {"query": title, "count": 2})
        print("5. knowledge.search_docs ->")
        for d in (docs or []):
            print(f"     {d.get('source')}: {d.get('title')}")

        print("\n" + "=" * 72)
        print("Done — the whole case was processed through MCP tools (3 decoupled servers).")
        print("=" * 72)
        sys.stdout.flush()


if __name__ == "__main__":
    t = "User locked out - cannot sign in, password reset needed after leave"
    d = ("Account locked after repeated failed logins; back from leave, old MFA device, "
         "manager approval attached.")
    asyncio.run(run_case(t, d))
