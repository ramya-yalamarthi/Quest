"""
D365 runner (Approach #2): run the full agent pipeline on a Case and let the
orchestrator bind the three agents' outputs into ONE note for the Case timeline.

    Routing      -> which team should own it
 -> Diagnosis    -> root cause + similar past incidents (clickable, with match %)
 -> Recommendation -> Hot Fix + Ultimate Fix + matching public reference links

Network-free / testable: the caller does the D365 read/write via DataverseClient.
"""

from __future__ import annotations

from typing import Callable, Optional

from app.orchestrator.agents import RoutingAgent, DiagnosisAgent, RecommendationAgent
from app.orchestrator.similarity import rank_similar

NOTE_SUBJECT = "AI Support Recommendation"


def case_url(org_base: str, case_id: str) -> str:
    """Deep link that opens a Case (incident) record in the D365 web app."""
    if not (org_base and case_id):
        return ""
    return f"{org_base.rstrip('/')}/main.aspx?pagetype=entityrecord&etn=incident&id={case_id}"


def _pct(x) -> str:
    try:
        return f"{round(float(x) * 100)}%"
    except (TypeError, ValueError):
        return "-"


def _context(case: dict, similar: list) -> dict:
    return {
        "event": {"type": "reactivate", "payload": {
            "ticket_id": case.get("id"),
            "title": case.get("title", ""),
            "description": case.get("description", ""),
            "assigned_team": case.get("assigned_team", ""),
        }},
        "similar": similar,
    }


_DIV = "-" * 30


def _bold(s: str) -> str:
    """Unicode sans-serif bold -- renders bold in plain text (no rich-text needed)."""
    out = []
    for ch in s:
        o = ord(ch)
        if 65 <= o <= 90:      # A-Z
            out.append(chr(0x1D5D4 + o - 65))
        elif 97 <= o <= 122:   # a-z
            out.append(chr(0x1D5EE + o - 97))
        elif 48 <= o <= 57:    # 0-9
            out.append(chr(0x1D7EC + o - 48))
        else:
            out.append(ch)
    return "".join(out)


def _status(state) -> str:
    return "✓ resolved" if state == 1 else "open"


def format_note(advisory: dict) -> str:
    """Bind the three agents into ONE crisp, bulleted Case note.

    Headings are real (Unicode) bold; incident URLs are raw so Dynamics
    auto-links them (clickable)."""
    r = advisory.get("routing") or {}
    d = advisory.get("diagnosis") or {}
    rec = advisory.get("recommendation") or {}
    hot = rec.get("hot_fix") or {}
    ult = rec.get("ultimate_fix") or {}
    sims = d.get("similar_incidents") or []
    links = rec.get("trusted_links") or []

    L = [_bold("AI SUPPORT ANALYSIS"),
         f"Confidence: {_pct(advisory.get('confidence'))}  "
         f"(based on {len(sims)} similar tickets and {len(links)} references)",
         _DIV, ""]

    # TEAM ASSIGNMENT (conditional)
    L.append(_bold("TEAM ASSIGNMENT"))
    if r.get("assignment_correct") is True:
        L.append(f"• Correct — handled by {r.get('assigned_team')}")
    elif r.get("assignment_correct") is False:
        L.append(f"• Incorrect — recommended team: {r.get('recommended_team')}")
    else:
        L.append(f"• Recommended team: {r.get('recommended_team')}")
    L.append("")

    # DIAGNOSIS = root cause + similar incidents (status + clickable URL)
    L.append(_bold("DIAGNOSIS"))
    if d.get("root_cause"):
        L.append(f"• Root cause: {d['root_cause']}")
    if sims:
        L.append("• Similar past incidents:")
        for s in sims:
            L.append(f"   – {s.get('ticket_number')}  {s.get('title')}  "
                     f"({_pct(s.get('score'))} match)  {_status(s.get('state'))}")
            if s.get("url"):
                L.append(f"     {s['url']}")
    L.append("")

    # RECOMMENDATION = Hot Fix + Ultimate Fix + refs (crisp, one line each)
    L.append(_bold("RECOMMENDATION"))
    he = f" ({hot['eta']})" if hot.get("eta") else ""
    L.append(f"• Hot fix{he}: {hot.get('summary', '')}")
    ue = f" ({ult['eta']})" if ult.get("eta") else ""
    cm = "   ⚠ Change Management" if ult.get("requires_change_mgmt") else ""
    L.append(f"• Ultimate fix{ue}: {ult.get('summary', '')}{cm}")
    if links:
        refs = " · ".join((ln.get("title") or ln.get("source") or "ref") for ln in links)
        L.append(f"• Refs: {refs}")
    L.append("")

    L.append(_DIV)
    L.append("Was this recommendation helpful?    \U0001f44d  /  \U0001f44e")
    return "\n".join(L)


def process_case(
    case: dict,
    corpus: list,
    org_base: str = "",
    top_k: int = 4,
    min_score: float = 0.2,
    embed_fn: Optional[Callable] = None,
    agents: Optional[dict] = None,
) -> tuple:
    """Run Routing -> Diagnosis -> Recommendation for `case`, grounded in the
    similar `corpus` cases, and bind into one note. Returns (advisory, note)."""
    agents = agents or {}
    routing_agent = agents.get("routing") or RoutingAgent()
    diagnosis_agent = agents.get("diagnosis") or DiagnosisAgent()
    rec_agent = agents.get("recommendation") or RecommendationAgent()

    similar = rank_similar(case, corpus, top_k=top_k, min_score=min_score, embed_fn=embed_fn)
    for s in similar:                                  # add clickable D365 links
        s["url"] = case_url(org_base, s.get("id"))
    context = _context(case, similar)

    routing = routing_agent.run(context)               # team check
    diag = diagnosis_agent.run(context)                # root cause
    diagnosis = {**diag, "similar_incidents": similar}  # similarity is part of diagnosis
    context["diagnosis"] = diag
    recommendation = rec_agent.run(context)            # hot + ultimate fix + links

    # Meaningful confidence: blend the model's confidence with the strength of
    # the best real-case match (the actual evidence).
    top_match = similar[0]["score"] if similar else None
    llm_conf = recommendation.get("confidence", 0.5)
    confidence = round((0.5 * llm_conf + 0.5 * top_match), 2) if top_match is not None else llm_conf

    advisory = {"routing": routing, "diagnosis": diagnosis,
                "recommendation": recommendation, "confidence": confidence}
    return advisory, format_note(advisory)
