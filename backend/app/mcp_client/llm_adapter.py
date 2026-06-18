"""
gpt-4o adapter for the Phase-2 tool-calling agent.

Provides `chat_raw(messages, tools)` -> an OpenAI-style assistant message dict
(with tool_calls), using Azure OpenAI function-calling. This is what makes the
model actually drive the MCP tools (vs the stub). Self-contained; uses the same
OPENAI_* env vars as the orchestrator.
"""

from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def _client():
    endpoint = os.getenv("OPENAI_ENDPOINT")
    api_key = os.getenv("OPENAI_API_KEY")
    if not (endpoint and api_key):
        return None
    try:
        from openai import AzureOpenAI
        return AzureOpenAI(
            azure_endpoint=endpoint, api_key=api_key,
            api_version=os.getenv("LLM_API_VERSION", "2024-12-01-preview"),
        )
    except Exception as exc:
        print(f"[mcp.llm_adapter] could not init client: {exc}")
        return None


def available() -> bool:
    return _client() is not None


def chat_raw(messages, tools):
    """Call gpt-4o with function-calling. Returns an assistant message dict that
    is API-compatible (so it can be appended and sent back next turn)."""
    client = _client()
    deployment = os.getenv("LLM_MODEL", "gpt-4o")
    resp = client.chat.completions.create(
        model=deployment, messages=messages, tools=tools,
        tool_choice="auto", temperature=0,
    )
    m = resp.choices[0].message
    out = {"role": "assistant", "content": m.content}
    if m.tool_calls:
        out["tool_calls"] = [{
            "id": tc.id, "type": "function",
            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
        } for tc in m.tool_calls]
    return out
