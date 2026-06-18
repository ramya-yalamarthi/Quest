"""
In-process MCP demo (reliable on every OS, incl. Windows).

Runs the SAME case flow as agent_runner.py and calls the SAME MCP tools -- but
in-process, so it sidesteps the Windows stdio-subprocess transport quirk
(anyio BrokenResourceError on long calls). Use agent_runner.py for the real
over-the-wire MCP transport (works on Linux / Render); use this for a reliable
local walkthrough.

Run:  python -m app.mcp_client.demo_inprocess
"""

from __future__ import annotations

import app.mcp_servers.dataverse_server as ds
import app.mcp_servers.knowledge_server as kn
import app.mcp_servers.remediation_server as rem


def _tool(t):
    """Return the underlying callable for an @mcp.tool()-registered function."""
    return getattr(t, "fn", t)


def run_case(title: str, description: str):
    print("=" * 72)
    print("MCP tools (in-process) — processing a case through the 3 servers")
    print("=" * 72)
    print("CASE:", title, "\n")

    similar = _tool(ds.find_similar_cases)(title=title, description=description)
    top = similar[0]["display_score"] if similar else 0.0
    print("1. dataverse.find_similar_cases ->")
    for s in similar[:3]:
        print(f"     {round((s.get('display_score') or 0)*100)}%  {s['ticket_number']}  {(s.get('title') or '')[:46]}")

    match = _tool(rem.match_runbook)(title=title, description=description)
    print("2. remediation.match_runbook ->", match)

    if match.get("matched"):
        dec = _tool(rem.assess_remediation)(title=title, description=description,
                                            precedent_match=top, confidence=0.95)
        print("3. remediation.assess (gate) ->",
              "PASS -> auto-remediate" if dec.get("gate_passed") else "fail -> suggest-only")
        if dec.get("gate_passed"):
            run = _tool(rem.run_runbook)(match["key"])
            print("4. remediation.run_runbook ->")
            for line in run.get("executed", []):
                print("     ", line)
            print("     (", run.get("note"), ")")
    else:
        print("3. no runbook matched -> SUGGEST-ONLY")

    docs = _tool(kn.search_docs)(title, 2)
    print("5. knowledge.search_docs ->")
    for d in (docs or []):
        print(f"     {d.get('source')}: {d.get('title')}")

    print("\n" + "=" * 72)
    print("Done — the case was processed entirely through MCP tools (3 servers).")
    print("=" * 72)


if __name__ == "__main__":
    run_case(
        "User locked out - cannot sign in, password reset needed after leave",
        "Account locked after repeated failed logins; old MFA device, manager approval attached.",
    )
