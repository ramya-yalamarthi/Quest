"""
Phase 2 — model-driven tool-calling agent.

Instead of calling the MCP tools in a fixed order (Phase 1), the MODEL (gpt-4o)
decides which tool to call next. The agent:
  1. exposes the MCP tools to the model as OpenAI function schemas,
  2. runs a reason-act loop: model -> tool call -> result -> model -> ...,
  3. lets the model produce the final recommendation.

The safety GATE is NOT decided by the model: the model can *request* a
remediation, but `assess_remediation` (in the remediation MCP server) enforces
confidence/precedent/reversible/tier. The model cannot bypass it.

Run locally with a stub LLM (no gpt-4o needed):
    python -m app.mcp_client.tool_calling_agent
On Render / with creds, pass the real chat function (chat_raw) instead.
"""

from __future__ import annotations

import json
import os

# The MCP tools (in-process handles; identical to what the MCP servers expose).
import app.mcp_servers.dataverse_server as ds
import app.mcp_servers.knowledge_server as kn
import app.mcp_servers.remediation_server as rem


def _fn(t):
    return getattr(t, "fn", t)


# ---- the tool registry the model can call (name -> (callable, schema)) -------
TOOLS = {
    "find_similar_cases": (_fn(ds.find_similar_cases), {
        "description": "Find the most similar past Cases (semantic search). Returns matches with display_score.",
        "parameters": {"title": "string", "description": "string"}}),
    "match_runbook": (_fn(rem.match_runbook), {
        "description": "Does this case match a known auto-remediation runbook? Returns the runbook or matched=false.",
        "parameters": {"title": "string", "description": "string"}}),
    "assess_remediation": (_fn(rem.assess_remediation), {
        "description": "Run the SAFETY GATE. Auto-execute only if confidence>=0.85 AND precedent_match>=0.80 AND reversible AND Tier A.",
        "parameters": {"title": "string", "description": "string", "precedent_match": "number", "confidence": "number"}}),
    "run_runbook": (_fn(rem.run_runbook), {
        "description": "Execute a runbook's steps (external actions simulated). Only call after assess_remediation passed.",
        "parameters": {"key": "string"}}),
    "search_docs": (_fn(kn.search_docs), {
        "description": "Search official product documentation for this problem.",
        "parameters": {"query": "string", "count": "number"}}),
}


def openai_tool_schemas() -> list:
    """Bridge: MCP tools -> OpenAI function-calling 'tools' schema."""
    out = []
    for name, (_, meta) in TOOLS.items():
        props = {p: {"type": t} for p, t in meta["parameters"].items()}
        out.append({"type": "function", "function": {
            "name": name, "description": meta["description"],
            "parameters": {"type": "object", "properties": props,
                           "required": list(props)}}})
    return out


def _execute(name: str, args: dict):
    fn, _ = TOOLS[name]
    return fn(**args)


SYSTEM = (
    "You are an autonomous support agent. Use the available tools to process the "
    "case end to end: find similar past cases, decide if it matches a known runbook, "
    "and if it does, ALWAYS call assess_remediation first; only call run_runbook if "
    "the gate passed. Then fetch one official documentation link. Finally, summarise "
    "your recommendation. Never claim to have auto-fixed unless run_runbook succeeded."
)


def run_agent(title: str, description: str, chat_raw, max_steps: int = 8) -> dict:
    """Reason-act loop. `chat_raw(messages, tools)` must return an OpenAI-style
    assistant message dict (with optional tool_calls). Returns the trace + final text."""
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Case title: {title}\nDescription: {description}"},
    ]
    tools = openai_tool_schemas()
    trace = []
    for _ in range(max_steps):
        msg = chat_raw(messages, tools)
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        if not calls:
            return {"final": msg.get("content", ""), "trace": trace}
        for c in calls:
            name = c["function"]["name"]
            args = json.loads(c["function"].get("arguments") or "{}")
            result = _execute(name, args)
            trace.append({"tool": name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": c["id"],
                             "content": json.dumps(result, default=str)[:4000]})
    return {"final": "(max steps reached)", "trace": trace}


# --- a STUB LLM so the loop runs locally without gpt-4o ----------------------
class _StubLLM:
    """Scripts a realistic tool-calling sequence for a lockout case, so the loop
    is verifiable locally. gpt-4o produces this dynamically at runtime."""
    def __init__(self):
        self._step = 0

    def __call__(self, messages, tools):
        title = messages[1]["content"]
        self._step += 1
        def tc(i, name, args):
            return {"id": f"call_{i}", "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)}}
        t = title.split("\n")[0].replace("Case title: ", "")
        d = ""
        if self._step == 1:
            return {"role": "assistant", "content": None,
                    "tool_calls": [tc(1, "find_similar_cases", {"title": t, "description": d})]}
        if self._step == 2:
            return {"role": "assistant", "content": None,
                    "tool_calls": [tc(2, "match_runbook", {"title": t, "description": d})]}
        if self._step == 3:
            return {"role": "assistant", "content": None,
                    "tool_calls": [tc(3, "assess_remediation",
                                      {"title": t, "description": d, "precedent_match": 1.0, "confidence": 0.95})]}
        if self._step == 4:
            return {"role": "assistant", "content": None,
                    "tool_calls": [tc(4, "run_runbook", {"key": "account_lockout"})]}
        if self._step == 5:
            return {"role": "assistant", "content": None,
                    "tool_calls": [tc(5, "search_docs", {"query": t, "count": 2})]}
        return {"role": "assistant",
                "content": "Matched the Account Lockout runbook; the safety gate passed, so the "
                           "runbook was executed (unlock -> reset MFA -> verify) and an official "
                           "Microsoft Entra doc was attached."}


if __name__ == "__main__":
    title = "User locked out - cannot sign in, password reset needed after leave"
    desc = "Account locked after repeated failed logins; old MFA device, manager approval attached."
    print("=" * 72)
    print("PHASE 2 — model-driven tool-calling agent  (stub LLM; gpt-4o does this live)")
    print("=" * 72)
    out = run_agent(title, desc, _StubLLM())
    for i, step in enumerate(out["trace"], 1):
        r = step["result"]
        short = (r if isinstance(r, dict) else r)
        print(f"  step {i}: model chose -> {step['tool']}")
    print("\nFINAL (model):", out["final"])
