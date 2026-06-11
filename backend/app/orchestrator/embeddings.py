"""
Slim embedding helper for the orchestrator (Approach #2).

Uses Azure OpenAI embeddings (e.g. text-embedding-ada-002) via the `openai`
library that the orchestrator already ships -- NO torch, NO sentence-transformers,
NO database. Optional, mirroring llm.py: if not configured, returns None and
callers fall back (no similarity, agents use the 4 reference tickets).

Env vars (embedding-specific, falling back to the chat model's if unset):
    EMBEDDING_MODEL        the embedding *deployment* name (e.g. text-embedding)  [required]
    EMBEDDING_ENDPOINT     defaults to OPENAI_ENDPOINT
    EMBEDDING_API_KEY      defaults to OPENAI_API_KEY
    EMBEDDING_API_VERSION  defaults to 2023-05-15

The embedding deployment can live on the same Azure resource as the chat model
or a different endpoint/key -- both are supported.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional


@lru_cache(maxsize=1)
def _client():
    endpoint = os.getenv("EMBEDDING_ENDPOINT") or os.getenv("OPENAI_ENDPOINT")
    api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
    deployment = os.getenv("EMBEDDING_MODEL")
    if not (endpoint and api_key and deployment):
        return None
    try:
        from openai import AzureOpenAI
        return AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=os.getenv("EMBEDDING_API_VERSION", "2023-05-15"),
        )
    except Exception as exc:  # pragma: no cover
        print(f"[orchestrator.embeddings] could not init client: {exc}")
        return None


def embeddings_available() -> bool:
    return _client() is not None


def embed_texts(texts: list[str]) -> Optional[list[list[float]]]:
    """Embed a batch of texts. Returns a list of vectors, or None if the
    embedding model isn't configured or the call fails (caller falls back)."""
    client = _client()
    if client is None or not texts:
        return None
    deployment = os.getenv("EMBEDDING_MODEL")
    try:
        resp = client.embeddings.create(model=deployment, input=texts)
        return [d.embedding for d in resp.data]
    except Exception as exc:
        print(f"[orchestrator.embeddings] call failed: {exc}")
        return None


def embed_query(text: str) -> Optional[list[float]]:
    vecs = embed_texts([text])
    return vecs[0] if vecs else None
