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
from app.orchestrator.mitigation import assess as mitigation_assess
from app.orchestrator.similarity import rank_similar
from app.orchestrator.web_refs import search_refs, validate_links, is_official_doc

NOTE_SUBJECT = "AI Support Recommendation"
# Public base URL of the deployed orchestrator (where the feedback links point).
DEFAULT_PUBLIC_URL = "https://quest-z7e4.onrender.com"
# Hide matches weaker than this CALIBRATED relevance from the note (the weak
# tail), but always keep the single strongest match.
MIN_DISPLAY = 0.35


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

    mit = advisory.get("mitigation") or {}
    if mit.get("gate_passed"):
        name = _esc(mit.get("recipe_name"))
        P.append(f"<b>🤖 AUTO-REMEDIATION — {name}</b>")
        P.append(f"✓ Matched the {name} runbook — 100% (signature confirmed)")
        prec = mit.get("precedent_ticket")
        prec_txt = (f" · precedent {_esc(prec)} ({_pct(mit.get('precedent_match'))})"
                    if prec else "")
        P.append(f"• Confidence: {_pct(mit.get('confidence'))} · "
                 f"Tier {_esc(mit.get('tier'))} (reversible){prec_txt}")
        P.append("• Actions executed:")
        for line in mit.get("executed", []):
            P.append(f"&nbsp;&nbsp;– {_esc(line)}")
        P.append(f"• Verification: {_esc(mit.get('verify'))} ✓")
        P.append("• Outcome: Case auto-resolved by the AI agent.")
        P.append("<i>External actions simulated in this environment; the D365 "
                 "resolve/close is live.</i>")
        P.append("")

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
            shown_score = s.get("display_score", s.get("score"))
            P.append(f"&nbsp;&nbsp;– {link} ({_pct(shown_score)} match) · {_status(s.get('state'))}")
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
    link_validate_fn: Optional[Callable] = None,
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
    context = _context(case, similar)                  # agents ground on ALL matches

    routing = routing_agent.run(context)               # team check
    diag = diagnosis_agent.run(context)                # root cause
    # In the NOTE, show only matches that are reasonably relevant after
    # calibration (hide the weak tail), but always keep the strongest one.
    shown = [s for s in similar if s.get("display_score", 0) >= MIN_DISPLAY] or similar[:1]
    diagnosis = {**diag, "similar_incidents": shown}    # similarity is part of diagnosis
    context["diagnosis"] = diag
    recommendation = rec_agent.run(context)            # hot + ultimate fix + links

    # Reference links: the agent proposes the OFFICIAL doc for the case's actual
    # technology (Microsoft Learn / PostgreSQL / Cisco / vendor KB / ...). We then
    # VALIDATE each one actually resolves (so we never show a dead link), and only
    # if we come up short do we backfill from a focused Microsoft Learn search.
    validate = link_validate_fn if link_validate_fn is not None else validate_links
    search = ref_search_fn if ref_search_fn is not None else search_refs
    # Quality over quantity: keep at most 2 precise links; only backfill from a
    # focused Microsoft Learn search if the agent gave us none (don't pad).
    try:
        links = validate(recommendation.get("trusted_links") or [], 2)
    except Exception:
        links = []
    if not links:
        try:                                           # focused query = the title alone
            extra = search(case.get("title", "").strip(), 4)
        except Exception:
            extra = []
        links = [e for e in (extra or []) if is_official_doc(e.get("url", ""))][:2]
    recommendation["trusted_links"] = links

    # Meaningful confidence: blend the model's confidence with the strength of
    # the best real-case match (calibrated relevance, the actual evidence).
    top_match = similar[0].get("display_score", similar[0]["score"]) if similar else None
    llm_conf = recommendation.get("confidence", 0.5)
    confidence = round((0.5 * llm_conf + 0.5 * top_match), 2) if top_match is not None else llm_conf
    # Evidence-grounding gate: if the diagnosis isn't supported by the cited case
    # (an assumed/hallucinated cause), cap confidence -- never show a confident
    # number for an unconfirmed root cause.
    if not diag.get("grounded", True):
        confidence = round(min(confidence, 0.6), 2)

    advisory = {"routing": routing, "diagnosis": diagnosis,
                "recommendation": recommendation, "confidence": confidence}

    # Mitigation stage: can this Case be auto-remediated? (matches a runbook AND
    # clears the safety gate). The caller (poller) does the real D365 close when
    # gate_passed is True; otherwise the note is suggest-only, as before.
    advisory["mitigation"] = mitigation_assess(case, similar, confidence)

    # Clickable feedback links -> the orchestrator's /feedback endpoint records
    # the vote onto the case.
    fb_base = (feedback_base or os.getenv("PUBLIC_BASE_URL", DEFAULT_PUBLIC_URL)).rstrip("/")
    cid = case.get("id")
    if fb_base and cid:
        advisory["feedback_like_url"] = f"{fb_base}/orchestrator/feedback?case={cid}&v=like"
        advisory["feedback_dislike_url"] = f"{fb_base}/orchestrator/feedback?case={cid}&v=dislike"
    return advisory, format_note(advisory)
