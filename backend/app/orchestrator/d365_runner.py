"""
D365 runner (Approach #2): turn a Case into a recommendation Note.

Ties the pieces together -- pull similar Cases, run the Recommendation agent
grounded in them, format a Case note. The actual D365 read/write is done by the
caller via DataverseClient, so this module stays network-free and testable.
"""

from __future__ import annotations

from typing import Callable, Optional

from app.orchestrator.agents import RecommendationAgent
from app.orchestrator.similarity import rank_similar

NOTE_SUBJECT = "AI Support Recommendation"


def format_note(advisory: dict) -> str:
    """Render an advisory dict as the plain-text Note posted to a D365 Case."""
    imm = advisory.get("immediate_action") or {}
    dur = advisory.get("durable_fix") or {}
    prev = advisory.get("prevention") or {}
    delta = advisory.get("delta") or {}
    L = ["AI SUPPORT RECOMMENDATION", ""]
    if advisory.get("root_cause"):
        L.append(f"Root cause: {advisory['root_cause']}")
    if delta.get("prior_fix_gap"):
        L.append(f"Why it may recur: {delta['prior_fix_gap']}")
    L.append("")
    L.append(f"IMMEDIATE (~{imm.get('eta_minutes', '?')} min): {imm.get('summary', '')}")
    for s in imm.get("steps", []):
        L.append(f"  - {s}")
    cm = "  [Change Management required]" if dur.get("requires_change_mgmt") else ""
    L.append(f"DURABLE (~{dur.get('eta_hours', '?')} hr): {dur.get('summary', '')}{cm}")
    for s in dur.get("steps", []):
        L.append(f"  - {s}")
    if prev.get("monitoring_rule"):
        L.append(f"PREVENTION: {prev['monitoring_rule']}")
    if advisory.get("similar_cases"):
        L.append("")
        L.append("Similar past cases:")
        for s in advisory["similar_cases"]:
            L.append(f"  - {s.get('ticket_number')}: {s.get('title')}  (match {s.get('score')})")
    L.append("")
    L.append(f"Confidence: {advisory.get('confidence')}")
    return "\n".join(L)


def _context(case: dict, similar: list) -> dict:
    return {
        "event": {"type": "reactivate", "payload": {
            "ticket_id": case.get("id"),
            "title": case.get("title", ""),
            "description": case.get("description", ""),
        }},
        "similar": similar,
    }


def process_case(
    case: dict,
    corpus: list,
    agent: Optional[RecommendationAgent] = None,
    top_k: int = 4,
    min_score: float = 0.2,
    embed_fn: Optional[Callable] = None,
) -> tuple:
    """Run the Recommendation agent for `case` grounded in similar `corpus`
    cases. Returns (advisory, note_text). No network here -- embeddings/LLM are
    reached through the agent + similarity, which fall back gracefully."""
    agent = agent or RecommendationAgent()
    similar = rank_similar(case, corpus, top_k=top_k, min_score=min_score, embed_fn=embed_fn)
    advisory = agent.run(_context(case, similar))
    return advisory, format_note(advisory)
