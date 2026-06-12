"""
D365 runner (Approach #2): run the full agent pipeline on a Case and let the
orchestrator bind the three agents' outputs into ONE note for the Case timeline.

    Routing      -> which team should own it
 -> Diagnosis    -> root cause + similar past incidents (clickable, with match %)
 -> Recommendation -> Hot Fix + Ultimate Fix + matching public reference links

Network-free / testable: the caller does the D365 read/write via DataverseClient.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from app.orchestrator.agents import RoutingAgent, DiagnosisAgent, RecommendationAgent
from app.orchestrator.similarity import rank_similar
from app.orchestrator.web_refs import search_refs

NOTE_SUBJECT = "AI Support Recommendation"
# Public base URL of the deployed orchestrator (where the feedback links point).
DEFAULT_PUBLIC_URL = "https://quest-z7e4.onrender.com"


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


def _status(state) -> str:
    return "✓ resolved" if state == 1 else "open"


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _href(u) -> str:
    return str(u).replace("&", "&amp;")


def format_note(advisory: dict) -> str:
    """Bind the three agents into ONE Case note as HTML (the D365 timeline renders
    it): bold headings, clickable incident links, and clickable 👍/👎 -- no raw
    URLs shown."""
    r = advisory.get("routing") or {}
    d = advisory.get("diagnosis") or {}
    rec = advisory.get("recommendation") or {}
    hot = rec.get("hot_fix") or {}
    ult = rec.get("ultimate_fix") or {}
    sims = d.get("similar_incidents") or []
    links = rec.get("trusted_links") or []
    P = []

    P.append("<b>AI SUPPORT ANALYSIS</b>")
    P.append(f"Confidence: {_pct(advisory.get('confidence'))} "
             f"(based on {len(sims)} similar tickets and {len(links)} references)")
    P.append("")

    P.append("<b>TEAM ASSIGNMENT</b>")
    assigned = r.get("assigned_team") or "Unassigned"
    correct = r.get("assignment_correct")
    P.append(f"• Assigned team: {_esc(assigned)}")
    if correct is True:
        P.append("• Assignment correct: Yes")
    elif correct is False:
        P.append("• Assignment correct: No")
        P.append(f"• Recommended team: {_esc(r.get('recommended_team'))}")
    else:                                   # no team assigned yet -> just route it
        P.append(f"• Recommended team: {_esc(r.get('recommended_team'))}")
    P.append("")

    P.append("<b>DIAGNOSIS</b>")
    if d.get("root_cause"):
        P.append(f"• Root cause: {_esc(d['root_cause'])}")
    if sims:
        P.append("• Similar past incidents:")
        for s in sims:
            label = _esc(f"{s.get('ticket_number')} — {s.get('title')}")
            url = s.get("url") or ""
            link = f'<a href="{_href(url)}">{label}</a>' if url else label
            P.append(f"&nbsp;&nbsp;– {link} ({_pct(s.get('score'))} match) · {_status(s.get('state'))}")
    P.append("")

    P.append("<b>RECOMMENDATION</b>")
    he = f" ({_esc(hot['eta'])})" if hot.get("eta") else ""
    P.append(f"• Hot fix{he}: {_esc(hot.get('summary', ''))}")
    ue = f" ({_esc(ult['eta'])})" if ult.get("eta") else ""
    P.append(f"• Ultimate fix{ue}: {_esc(ult.get('summary', ''))}")
    if links:
        parts = []
        for ln in links:
            title = _esc(ln.get("title") or ln.get("source") or "ref")
            u = ln.get("url")
            parts.append(f'<a href="{_href(u)}">{title}</a>' if u else title)
        P.append("• Refs: " + " · ".join(parts))
    P.append("")

    like = advisory.get("feedback_like_url")
    dislike = advisory.get("feedback_dislike_url")
    if like and dislike:
        P.append("Was this recommendation helpful?")
        P.append(f'<a href="{_href(like)}">👍</a> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; '
                 f'<a href="{_href(dislike)}">👎</a>')
    return "<br>".join(P)


def process_case(
    case: dict,
    corpus: list,
    org_base: str = "",
    feedback_base: str = "",
    top_k: int = 4,
    min_score: float = 0.2,
    embed_fn: Optional[Callable] = None,
    agents: Optional[dict] = None,
    ref_search_fn: Optional[Callable] = None,
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

    # Option B: replace the model's reference links with REAL Microsoft Learn
    # search results (fall back to the model's links if search returns nothing).
    search = ref_search_fn if ref_search_fn is not None else search_refs
    try:
        web = search(f"{case.get('title', '')} {diag.get('root_cause', '')}".strip(), 3)
    except Exception:
        web = []
    if web:
        recommendation["trusted_links"] = web

    # Meaningful confidence: blend the model's confidence with the strength of
    # the best real-case match (the actual evidence).
    top_match = similar[0]["score"] if similar else None
    llm_conf = recommendation.get("confidence", 0.5)
    confidence = round((0.5 * llm_conf + 0.5 * top_match), 2) if top_match is not None else llm_conf

    advisory = {"routing": routing, "diagnosis": diagnosis,
                "recommendation": recommendation, "confidence": confidence}

    # Clickable feedback links -> the orchestrator's /feedback endpoint records
    # the vote onto the case.
    fb_base = (feedback_base or os.getenv("PUBLIC_BASE_URL", DEFAULT_PUBLIC_URL)).rstrip("/")
    cid = case.get("id")
    if fb_base and cid:
        advisory["feedback_like_url"] = f"{fb_base}/orchestrator/feedback?case={cid}&v=like"
        advisory["feedback_dislike_url"] = f"{fb_base}/orchestrator/feedback?case={cid}&v=dislike"
    return advisory, format_note(advisory)
