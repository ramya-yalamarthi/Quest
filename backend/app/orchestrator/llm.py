"""
LLM helper for the orchestrator's agents (Azure OpenAI / gpt-4o).

Self-contained and *optional*: if the OPENAI_* env vars aren't set (e.g. in the
demo/tests), llm_available() is False and chat_json() returns None, so agents
fall back to deterministic behaviour instead of crashing.

Required env vars (set in backend/.env locally and in Render for deploy):
    OPENAI_ENDPOINT   e.g. https://<resource>.openai.azure.com/
    OPENAI_API_KEY    the key
    LLM_MODEL         the deployment name, e.g. gpt-4o
    LLM_API_VERSION   optional, defaults to 2024-12-01-preview
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Optional


@lru_cache(maxsize=1)
def _client():
    endpoint = os.getenv("OPENAI_ENDPOINT")
    api_key = os.getenv("OPENAI_API_KEY")
    deployment = os.getenv("LLM_MODEL")
    if not (endpoint and api_key and deployment):
        return None
    try:
        from openai import AzureOpenAI
        return AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=os.getenv("LLM_API_VERSION", "2024-12-01-preview"),
        )
    except Exception as exc:  # pragma: no cover
        print(f"[orchestrator.llm] could not init client: {exc}")
        return None


def llm_available() -> bool:
    return _client() is not None


def chat_json(system: str, user: str, *, max_tokens: int = 400,
              temperature: float = 0.0) -> Optional[dict]:
    """Call the LLM and parse a JSON object reply. Returns None if the LLM
    isn't configured or anything fails (caller should fall back)."""
    client = _client()
    if client is None:
        return None
    deployment = os.getenv("LLM_MODEL")
    try:
        resp = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as exc:
        print(f"[orchestrator.llm] call failed: {exc}")
        return None
