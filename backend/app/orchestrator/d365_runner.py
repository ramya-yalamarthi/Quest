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
import re
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from app.orchestrator.agents import RoutingAgent, DiagnosisAgent, RecommendationAgent
from app.orchestrator.appconfig import env_float
from app.orchestrator.roster import _TEAM_ALIASES
from app.orchestrator.similarity import rank_similar
from app.orchestrator.sla import sla_status, escalation_reminder
from app.orchestrator.web_refs import search_refs, validate_links, is_official_doc

NOTE_SUBJECT = "AI Support Recommendation"
# Public base URL of the deployed orchestrator (override via PUBLIC_BASE_URL env).
DEFAULT_PUBLIC_URL = os.getenv("PUBLIC_BASE_URL", "https://quest-z7e4.onrender.com")
# Hide matches weaker than this CALIBRATED relevance from the note (the weak
# tail), but always keep the single strongest match.
MIN_DISPLAY = env_float("MIN_DISPLAY", 0.35)


def case_url(org_base: str, case_id: str) -> str:
    """Deep link that opens a Case (incident) record in the D365 web app."""
    if not (org_base and case_id):
        return ""
    return f"{org_base.rstrip('/')}/main.aspx?pagetype=entityrecord&etn=incident&id={case_id}"


def _ref_query(title: str, root_cause: str) -> str:
    """Build the reference-search query from the descriptive root cause + title,
    stripping ticket-id tokens (CASE-010, CAS-01124) so the Learn search can't
    keyword-collide with unrelated docs (e.g. the SQL 'CASE' statement)."""
    raw = f"{root_cause or ''} {title or ''}"
    q = re.sub(r"\b(?:CASE|CAS)-?\d[\w-]*\b", " ", raw, flags=re.I)
    return re.sub(r"\s+", " ", q).strip()


def _pct(x) -> str:
    try:
        return f"{round(float(x) * 100)}%"
    except (TypeError, ValueError):
        return "-"


def _context(case: dict, similar: list, feedback: str = "") -> dict:
    return {
        "event": {"type": "reactivate", "payload": {
            "ticket_id": case.get("id"),
            "title": case.get("title", ""),
            "description": case.get("description", ""),
            "assigned_team": case.get("assigned_team", ""),
        }},
        "similar": similar,
        "feedback": feedback,        # engineer's 👎 comment -> agents correct the answer
    }


def _status(state) -> str:
    return "✓ resolved" if state == 1 else "open"


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _href(u) -> str:
    return str(u).replace("&", "&amp;")


def _parse_created(s) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


_WINDOWS = (("week", timedelta(days=7)), ("month", timedelta(days=30)), ("quarter", timedelta(days=90)))


def _historical_routing_match(team: str, matches: list) -> Optional[dict]:
    """How many of the RELEVANT similar past incidents (display_score >=
    MIN_DISPLAY) read as the same category, by keyword (the same alias list
    roster.py uses for skill matching) -- a real, computable proxy for
    'historical routing accuracy' since Dataverse cases don't carry a stored
    team field we can query. None if there's no relevant evidence to check."""
    relevant = [m for m in matches if m.get("display_score", 0) >= MIN_DISPLAY]
    if not relevant or not team:
        return None
    keywords = [team.lower()] + [k.lower() for k in _TEAM_ALIASES.get(team, [])]
    hits = 0
    for m in relevant:
        text = f"{m.get('title', '')} {m.get('description', '')}".lower()
        if any(k in text for k in keywords if k):
            hits += 1
    return {"count": hits, "total": len(relevant)}


# Category/keyword -> a workflow that COULD be triggered (capacity/quota
# changes, scale-up) -- always shown as a SUGGESTION for a manager to approve,
# never auto-run. Keep this conservative: only suggest when the signal is
# clear, since a wrong suggestion erodes trust faster than no suggestion.
_WORKFLOW_SUGGESTIONS = (
    (("quota", "capacity", "instance types", "pricing"), {
        "title": "Increase NodePool/instance-type quota or capacity allocation",
        "steps": [
            "Check current quota/limits for the affected instance type (cloud console or NodePool spec).",
            "Raise the NodePool's instance-type/capacity limit to cover the shortfall.",
            "Apply the updated NodePool configuration.",
            "Confirm Karpenter provisions new nodes and the pending pods schedule.",
        ],
    }),
    (("autoscaling", "scale-up", "scale down", "scaling"), {
        "title": "Review/trigger an autoscaling policy adjustment",
        "steps": [
            "Check the autoscaler logs for recent scale-up/scale-down decisions.",
            "Review the policy thresholds (min/max nodes, scale-down delay).",
            "Adjust the thresholds if scaling is too conservative for current load.",
            "Trigger a manual scale-up if pods are pending on insufficient nodes.",
        ],
    }),
    (("pending", "provisioning", "nodepool", "scheduling"), {
        "title": "Run a NodePool provisioning health-check",
        "steps": [
            "Verify the Karpenter controller is running and healthy.",
            "Check the NodePool/EC2NodeClass status for errors.",
            "Confirm cloud-provider service quotas aren't blocking provisioning.",
            "Re-trigger provisioning once the blocker is cleared and confirm pods schedule.",
        ],
    }),
)


def _suggested_workflow(team: str, root_cause: str, ticket_text: str = "") -> Optional[dict]:
    """A concrete workflow -- title + steps -- grounded in the routed team +
    root cause + ticket text. None (no filler) if nothing clearly points to
    one. These are steps for a human to RUN, not something this app executes;
    there's no API/Power Automate wiring behind this yet."""
    text = f"{team} {root_cause} {ticket_text}".lower()
    for keywords, workflow in _WORKFLOW_SUGGESTIONS:
        if any(k in text for k in keywords):
            return workflow
    return None


def _window_counts(matches: list, now: Optional[datetime] = None) -> dict:
    """Count RELEVANT matches (display_score >= MIN_DISPLAY, same bar used to
    decide what's shown) created within the last week / month / quarter."""
    now = now or datetime.now(timezone.utc)
    counts = {"week": 0, "month": 0, "quarter": 0}
    for m in matches:
        if m.get("display_score", 0) < MIN_DISPLAY:
            continue
        created = _parse_created(m.get("created_on"))
        if not created:
            continue
        age = now - created
        for key, span in _WINDOWS:
            if age <= span:
                counts[key] += 1
    return counts


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

    P.append("<b>AI INSIGHTS &mdash; SUPPORT ANALYSIS</b>")
    P.append(f"Composite Confidence: {_pct(advisory.get('confidence'))} "
             f"(based on {len(sims)} similar tickets and {len(links)} references)")
    cb = advisory.get("confidence_breakdown") or {}
    if cb:
        P.append(f"&nbsp;&nbsp;Evidence: {_pct(cb.get('similarity'))} · Routing: {_pct(cb.get('routing'))} "
                  f"· Diagnosis: {_pct(cb.get('diagnosis'))} · Recommendation: {_pct(cb.get('recommendation'))}")
    sla = advisory.get("sla")
    if sla:
        mins = sla["minutes_to_resolution_deadline"]
        clock = f"{mins} min left" if mins >= 0 else f"OVERDUE by {-mins} min"
        P.append(f"SLA: {sla['tier']} &nbsp;·&nbsp; Resolution {clock}" +
                 (" · ⚠ RESOLUTION SLA BREACHED" if sla["resolution_breached"] else "") +
                 (" · ⚠ RESPONSE SLA BREACHED — not yet assigned" if sla["response_breached"] else ""))
    reminder = advisory.get("escalation_reminder")
    if reminder:
        P.append(f"&nbsp;&nbsp;&#9888; {_esc(reminder)}")
    P.append("")

    P.append(f"<b>TEAM ASSIGNMENT</b> &nbsp;·&nbsp; Confidence: {_pct(r.get('confidence'))}")
    assigned = (r.get("assigned_team") or "").strip()
    correct = r.get("assignment_correct")
    team = r.get("recommended_team")
    if correct is True:
        # already on the right team
        P.append(f"• Assigned team: {_esc(assigned)}")
    elif correct is False:
        # on the wrong team -> show current and the better one
        P.append(f"• Currently assigned: {_esc(assigned)} (recommend reassigning)")
        P.append(f"• Assigned team: {_esc(team)}")
    else:
        # not assigned yet -> the recommended team IS the assignment (no "Unassigned")
        P.append(f"• Assigned team: {_esc(team)}")
    if r.get("reason"):
        P.append(f"• Why this team: {_esc(r.get('reason'))}")
    eng = r.get("assigned_engineer")
    if eng:
        P.append(f"• Assigned engineer: {_esc(eng.get('name'))} ({_esc(eng.get('email'))})")
        if eng.get("reason"):
            P.append(f"• Why this engineer: {_esc(eng.get('reason'))}")
        if eng.get("track_record"):
            P.append(f"• Track record: {_esc(eng.get('track_record'))}")

    hm = r.get("historical_match")
    cards = []
    cards.append(f"Team match — {_pct(r.get('confidence'))} confidence" +
                 (f", consistent with {hm['count']}/{hm['total']} similar past incidents" if hm else ""))
    if eng and eng.get("specialty"):
        cards.append(f"Engineer fit — {_esc(eng.get('specialty'))} specialist")
    if eng and eng.get("remaining_shift_minutes") is not None:
        risk = " · ⚠ handoff risk" if eng.get("handoff_risk") else ""
        cards.append(f"Availability — {eng['remaining_shift_minutes'] / 60:.1f}h left in shift{risk}")
    elif eng and eng.get("sla_risk"):
        cards.append("Availability — ⚠ no specialist on-shift or on-call")
    if eng and eng.get("track_record"):
        cards.append(f"Track record — {_esc(eng['track_record'])}")
    if cards:
        P.append("• Insight cards:")
        for c in cards[:4]:
            P.append(f"&nbsp;&nbsp;[ {c} ]")
    P.append("")

    P.append(f"<b>DIAGNOSIS</b> &nbsp;·&nbsp; Confidence: {_pct(d.get('confidence'))}")
    if d.get("root_cause"):
        P.append(f"• Root cause: {_esc(d['root_cause'])}")
        P.append("&nbsp;&nbsp;Probable cause, grounded in the resolved tickets below" if d.get("grounded", True)
                  else "&nbsp;&nbsp;Probable cause -- not yet confirmed by precedent; verify before acting")
    if sims:
        P.append("• Supporting resolved tickets (evidence for the probable cause):")
        for s in sims:
            label = _esc(f"{s.get('ticket_number')} — {s.get('title')}")
            url = s.get("url") or ""
            link = f'<a href="{_href(url)}">{label}</a>' if url else label
            shown_score = s.get("display_score", s.get("score"))
            P.append(f"&nbsp;&nbsp;– {link} ({_pct(shown_score)} match) · {_status(s.get('state'))}")
        wc = d.get("window_counts") or {}
        if wc:
            P.append(f"&nbsp;&nbsp;Similar tickets matched — last 7 days: {wc.get('week', 0)} "
                      f"· last 30 days: {wc.get('month', 0)} · last quarter: {wc.get('quarter', 0)}")
    P.append("")

    P.append(f"<b>RECOMMENDATION</b> &nbsp;·&nbsp; Confidence: {_pct(rec.get('confidence'))}")
    he = f" ({_esc(hot['eta'])})" if hot.get("eta") else ""
    P.append(f"• Hot fix{he}: {_esc(hot.get('summary', ''))}")
    ue = f" ({_esc(ult['eta'])})" if ult.get("eta") else ""
    P.append(f"• Ultimate fix{ue}: {_esc(ult.get('summary', ''))}")
    if links:
        P.append("• Refs:")
        for ln in links:
            title = _esc(ln.get("title") or ln.get("source") or "ref")
            u = ln.get("url")
            label = f'<a href="{_href(u)}">{title}</a>' if u else title
            line = f"&nbsp;&nbsp;– {label}"
            if ln.get("times_recommended"):
                line += f" ({_pct(ln['success_rate'])} solved, {ln['times_recommended']} tickets)"
            if ln.get("like_url") and ln.get("dislike_url"):
                line += (f' &nbsp; <a href="{_href(ln["like_url"])}">👍</a>'
                         f' <a href="{_href(ln["dislike_url"])}">👎</a>')
            P.append(line)
    P.append("")

    workflow = advisory.get("suggested_workflow")
    if workflow:
        P.append(f"<b>SUGGESTED WORKFLOW</b> &nbsp;·&nbsp; {_esc(workflow['title'])}")
        for i, step in enumerate(workflow.get("steps") or [], 1):
            P.append(f"&nbsp;&nbsp;{i}. {_esc(step)}")
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
    link_stats_fn: Optional[Callable] = None,
    feedback: str = "",
) -> tuple:
    """Run Routing -> Diagnosis -> Recommendation for `case`, grounded in the
    similar `corpus` cases, and bind into one note. Returns (advisory, note).

    feedback: an engineer's 👎 comment on a previous answer; when set, the
    agents produce a corrected answer that addresses it."""
    agents = agents or {}
    routing_agent = agents.get("routing") or RoutingAgent()
    diagnosis_agent = agents.get("diagnosis") or DiagnosisAgent()
    rec_agent = agents.get("recommendation") or RecommendationAgent()

    # Only learn from CLOSED/resolved cases (statecode 1). Open (0) and
    # cancelled (2) tickets have no proven resolution, so they must NOT be used
    # as similar-incident matches. Cases with no state set (unit-test fixtures)
    # are kept so tests still exercise the ranking.
    closed_corpus = [c for c in (corpus or []) if c.get("state") not in (0, 2)]
    # Rank against the FULL closed corpus (not just top_k) so the 1wk/1mo/quarter
    # pattern-matching counts below reflect every relevant match, not only the
    # handful shown in the note.
    ranked = rank_similar(case, closed_corpus, top_k=len(closed_corpus) or 1,
                           min_score=min_score, embed_fn=embed_fn)
    similar = ranked[:top_k]
    for s in similar:                                  # add clickable D365 links
        s["url"] = case_url(org_base, s.get("id"))
    context = _context(case, similar, feedback=feedback)   # agents ground on ALL matches

    routing = routing_agent.run(context)               # team check
    routing["historical_match"] = _historical_routing_match(
        routing.get("recommended_team", ""), ranked)
    diag = diagnosis_agent.run(context)                # root cause
    # In the NOTE, show only matches that are reasonably relevant after
    # calibration (hide the weak tail), but always keep the strongest one.
    shown = [s for s in similar if s.get("display_score", 0) >= MIN_DISPLAY] or similar[:1]
    window_counts = _window_counts(ranked)
    diagnosis = {**diag, "similar_incidents": shown, "window_counts": window_counts}
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
        # search on the descriptive root cause (not the raw title), with ticket-id
        # tokens stripped -- avoids keyword collisions like "CASE-010" -> SQL CASE.
        q = _ref_query(case.get("title", ""), diag.get("root_cause", ""))
        try:
            extra = search(q, 4) if len(q) >= 5 else []
        except Exception:
            extra = []
        links = [e for e in (extra or []) if is_official_doc(e.get("url", ""))][:2]
    # Per-doc success-rate tracking (DB-backed, fully optional -- never
    # blocks the note if unavailable): annotates each link with how many
    # tickets it's been shown on and resolved how many of those.
    if links and link_stats_fn:
        try:
            links = link_stats_fn(case.get("id"), links) or links
        except Exception:
            pass
    recommendation["trusted_links"] = links

    # Composite confidence: blend ALL four signal sources (not just the
    # recommendation model) so the displayed score reflects the whole pipeline --
    # how strong the best real-case match is (the actual evidence), how sure
    # routing/diagnosis/recommendation each are. Weights favor real evidence
    # (similarity) over any single model's self-reported confidence.
    top_match = similar[0].get("display_score", similar[0]["score"]) if similar else None
    routing_conf = routing.get("confidence", 0.5)
    diagnosis_conf = diag.get("confidence", 0.5)
    rec_conf = recommendation.get("confidence", 0.5)
    composite_breakdown = {
        "similarity": top_match, "routing": routing_conf,
        "diagnosis": diagnosis_conf, "recommendation": rec_conf,
    }
    if top_match is not None:
        confidence = round(
            0.30 * top_match + 0.15 * routing_conf + 0.25 * diagnosis_conf + 0.30 * rec_conf, 2
        )
    else:
        confidence = round((routing_conf + diagnosis_conf + rec_conf) / 3, 2)
    # Evidence-grounding gate: if the diagnosis isn't supported by the cited case
    # (an assumed/hallucinated cause), cap confidence -- never show a confident
    # number for an unconfirmed root cause.
    if not diag.get("grounded", True):
        confidence = round(min(confidence, 0.6), 2)

    advisory = {"routing": routing, "diagnosis": diagnosis,
                "recommendation": recommendation, "confidence": confidence,
                "confidence_breakdown": composite_breakdown}

    created_dt = _parse_created(case.get("created_on"))
    if created_dt:
        sla = sla_status(case.get("priority"), created_dt)
        advisory["sla"] = sla
        reminder = escalation_reminder(sla)
        if reminder:
            advisory["escalation_reminder"] = reminder

    suggested_workflow = _suggested_workflow(routing.get("recommended_team", ""), diag.get("root_cause", ""),
                                              f"{case.get('title', '')} {case.get('description', '')}")
    if suggested_workflow:
        advisory["suggested_workflow"] = suggested_workflow

    # Clickable feedback links -> the orchestrator's /feedback endpoint records
    # the vote onto the case.
    fb_base = (feedback_base or os.getenv("PUBLIC_BASE_URL", DEFAULT_PUBLIC_URL)).rstrip("/")
    cid = case.get("id")
    if fb_base and cid:
        advisory["feedback_like_url"] = f"{fb_base}/orchestrator/feedback?case={cid}&v=like"
        advisory["feedback_dislike_url"] = f"{fb_base}/orchestrator/feedback?case={cid}&v=dislike"
        for ln in links:
            if ln.get("kb_id"):
                ln["like_url"] = f"{fb_base}/orchestrator/ref-feedback?case={cid}&kb={ln['kb_id']}&v=like"
                ln["dislike_url"] = f"{fb_base}/orchestrator/ref-feedback?case={cid}&kb={ln['kb_id']}&v=dislike"
    return advisory, format_note(advisory)
