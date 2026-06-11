"""
D365 runner (Approach #2): run the FULL agent pipeline on a Case and render the
note posted to its timeline.

A new Case flows through the same agents the supervisor coordinates, in order:
    Routing  (is the assigned team correct?)
 -> Diagnosis (root cause + matched reference + link)
 -> Recommendation (two-track fix + prevention + trusted links), grounded in the
    real similar Cases found by similarity search.

Network-free / testable: the D365 read/write is done by the caller via
DataverseClient; the agents reach the LLM/embeddings through their own optional
helpers and fall back gracefully.
"""

from __future__ import annotations

from typing import Callable, Optional

from app.orchestrator.agents import RoutingAgent, DiagnosisAgent, RecommendationAgent
from app.orchestrator.similarity import rank_similar

NOTE_SUBJECT = "AI Support Recommendation"


def _context(case: dict, similar: list) -> dict:
    return {
        "event": {"type": "reactivate", "payload": {
            "ticket_id": case.get("id"),
            "title": case.get("title", ""),
            "description": case.get("description", ""),
        }},
        "similar": similar,
    }


def format_note(advisory: dict) -> str:
    """Render the full pipeline output as the plain-text Case note."""
    r = advisory.get("routing") or {}
    d = advisory.get("diagnosis") or {}
    rec = advisory.get("recommendation") or {}
    imm = rec.get("immediate_action") or {}
    dur = rec.get("durable_fix") or {}
    prev = rec.get("prevention") or {}
    L = ["AI SUPPORT - ORCHESTRATED ANALYSIS", ""]

    # 1) Routing
    L.append("1) TEAM ASSIGNMENT  (Routing agent)")
    assigned, recm, ok = r.get("assigned_team"), r.get("recommended_team"), r.get("assignment_correct")
    if ok is True:
        L.append(f"   Assigned team '{assigned}' looks correct.")
    elif ok is False:
        L.append(f"   Assigned '{assigned}' may be wrong - recommend '{recm}'.")
    else:
        L.append(f"   Suggested team: {recm}")
    L.append("")

    # 2) Diagnosis
    L.append("2) DIAGNOSIS  (Diagnosis agent)")
    if d.get("root_cause"):
        L.append(f"   Root cause: {d['root_cause']}")
    if d.get("reasoning"):
        L.append(f"   Reasoning: {d['reasoning']}")
    if d.get("reference"):
        L.append(f"   Reference: {d.get('reference')}  {d.get('reference_link', '')}".rstrip())
    L.append("")

    # 3) Similar past cases (from similarity search over real Cases)
    sim = rec.get("similar_cases") or [
        {"ticket_number": s.get("ticket_number"), "title": s.get("title"), "score": s.get("score")}
        for s in advisory.get("similar", [])
    ]
    if sim:
        L.append("3) SIMILAR PAST CASES  (similarity search)")
        for s in sim:
            L.append(f"   - {s.get('ticket_number')}: {s.get('title')}  (match {s.get('score')})")
        L.append("")

    # 4) Recommendation
    L.append("4) RECOMMENDATION  (Recommendation agent)")
    L.append(f"   IMMEDIATE (~{imm.get('eta_minutes', '?')} min): {imm.get('summary', '')}")
    for s in imm.get("steps", []):
        L.append(f"      - {s}")
    cm = "  [Change Management required]" if dur.get("requires_change_mgmt") else ""
    L.append(f"   DURABLE (~{dur.get('eta_hours', '?')} hr): {dur.get('summary', '')}{cm}")
    for s in dur.get("steps", []):
        L.append(f"      - {s}")
    if prev.get("monitoring_rule"):
        L.append(f"   PREVENTION: {prev['monitoring_rule']}")
    links = rec.get("trusted_links") or []
    if links:
        L.append("   Reference links:")
        for ln in links:
            L.append(f"      - {ln.get('title')}: {ln.get('url')}")
    L.append("")
    L.append(f"Confidence: {rec.get('confidence')}")
    return "\n".join(L)


def process_case(
    case: dict,
    corpus: list,
    top_k: int = 4,
    min_score: float = 0.2,
    embed_fn: Optional[Callable] = None,
    agents: Optional[dict] = None,
) -> tuple:
    """Run Routing -> Diagnosis -> Recommendation for `case`, grounded in the
    similar `corpus` cases. Returns (advisory, note_text). No network here."""
    agents = agents or {}
    routing_agent = agents.get("routing") or RoutingAgent()
    diagnosis_agent = agents.get("diagnosis") or DiagnosisAgent()
    rec_agent = agents.get("recommendation") or RecommendationAgent()

    similar = rank_similar(case, corpus, top_k=top_k, min_score=min_score, embed_fn=embed_fn)
    context = _context(case, similar)

    routing = routing_agent.run(context)            # team check
    diagnosis = diagnosis_agent.run(context)        # root cause + reference
    context["diagnosis"] = diagnosis                # feed diagnosis into recommendation
    recommendation = rec_agent.run(context)         # two-track + prevention + links

    advisory = {"routing": routing, "diagnosis": diagnosis,
                "recommendation": recommendation, "similar": similar}
    return advisory, format_note(advisory)
