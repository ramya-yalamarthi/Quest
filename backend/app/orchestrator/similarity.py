"""
In-memory semantic similarity for the orchestrator (Approach #2).

Given a query Case and a small corpus of past Cases, embed them with Azure
ada-002 and return the top-K most similar by cosine similarity. Pure stdlib
math (no numpy) -- fine for tens/low-hundreds of cases, which is the POC scale.

No database, no torch. If embeddings aren't configured, returns [] and the
caller grounds on the 4 reference tickets instead.
"""

from __future__ import annotations

import math
from typing import Callable, Optional

from app.orchestrator.embeddings import embed_texts as _default_embed


def case_text(case: dict) -> str:
    """Canonical text for a Case dict (title + description)."""
    title = (case.get("title") or "").strip()
    desc = (case.get("description") or "").strip()
    return f"Title: {title}\nDescription: {desc}".strip()


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def rank_similar(
    query: dict,
    corpus: list[dict],
    top_k: int = 5,
    min_score: float = 0.0,
    embed_fn: Optional[Callable[[list[str]], Optional[list[list[float]]]]] = None,
) -> list[dict]:
    """Return up to top_k corpus cases most similar to `query`, each with a
    `score`. Excludes the query itself (matched by id/ticket_number). Returns []
    if embeddings are unavailable or the corpus is empty.
    """
    embed = embed_fn or _default_embed
    qid = query.get("id")
    qnum = query.get("ticket_number")
    pool = [c for c in corpus
            if c.get("id") != qid and (qnum is None or c.get("ticket_number") != qnum)]
    if not pool:
        return []

    vectors = embed([case_text(query)] + [case_text(c) for c in pool])
    if not vectors or len(vectors) != len(pool) + 1:
        return []

    qv, rest = vectors[0], vectors[1:]
    scored = [(c, _cosine(qv, v)) for c, v in zip(pool, rest)]
    scored.sort(key=lambda t: t[1], reverse=True)
    return [{**c, "score": round(s, 4)} for c, s in scored if s >= min_score][:top_k]
