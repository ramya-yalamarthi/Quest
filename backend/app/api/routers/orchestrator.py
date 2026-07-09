"""
Orchestrator API (WBS tasks O-07 webhook listener, O-09 accept/reject).

Follows the same APIRouter pattern as the other routers.  Register in main.py:
    from app.api.routers.orchestrator import router as orchestrator_router
    app.include_router(orchestrator_router)

The supervisor instance persists ticket state in Redis (or in-memory if
REDIS_URL is unset) and writes its audit trail to Postgres ai_audit_log.
"""

from typing import Optional
from uuid import UUID

import os

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from app.orchestrator import Orchestrator, OrchestrationRecord
from app.orchestrator.agents import default_agents
from app.orchestrator.audit import AuditLogger
from app.orchestrator.db_sink import postgres_audit_sink

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


def _live_prior_resolution_fetcher(ticket_id: str) -> Optional[dict]:
    """DB-backed fetcher for the Recommendation Agent (WBS R-03): the most recent
    resolution for this ticket. Fully optional -- any failure (no DB, non-UUID
    ticket id, no prior row) returns None so the pipeline degrades gracefully to
    'no prior resolution on record'.
    """
    try:
        tid = UUID(str(ticket_id))
    except (ValueError, TypeError, AttributeError):
        return None
    try:
        from app.db.session import SessionLocal
        from app.db.models.resolution import Resolution
    except Exception:
        return None
    db = None
    try:
        db = SessionLocal()
        row = (
            db.query(Resolution)
            .filter(Resolution.ticket_id == tid)
            .order_by(Resolution.created_at.desc())
            .first()
        )
        if row is None:
            return None
        return {
            "resolution_text": row.resolution_text,
            "root_cause": row.root_cause,
            "recommendedsteps": row.recommendedsteps,
        }
    except Exception:
        return None
    finally:
        if db is not None:
            db.close()


def _live_feedback_stats(root_cause_type: str) -> tuple:
    """Feedback-aware confidence input for the Recommendation Agent: (likes,
    dislikes) for advisories of this root-cause type. Joins feedback to its
    audited recommendation via ai_event_id. Fully optional -- any failure (no DB,
    missing tables, unlinked feedback) returns (0, 0) so confidence is unchanged.
    """
    try:
        from app.db.session import SessionLocal
    except Exception:
        return (0, 0)
    db = None
    try:
        db = SessionLocal()
        row = db.execute(
            text(
                "SELECT "
                "COUNT(*) FILTER (WHERE f.verdict = 'like')    AS likes, "
                "COUNT(*) FILTER (WHERE f.verdict = 'dislike') AS dislikes "
                "FROM recommendation_feedback f "
                "JOIN ai_audit_log a ON a.ai_event_id = f.ai_event_id "
                "WHERE a.output_json -> 'prevention' ->> 'root_cause_type' = :rct"
            ),
            {"rct": root_cause_type},
        ).first()
        if row is None:
            return (0, 0)
        return (int(row.likes or 0), int(row.dislikes or 0))
    except Exception:
        return (0, 0)
    finally:
        if db is not None:
            db.close()


def _live_link_stats(ticket_id: str, links: list) -> list:
    """DB-backed per-reference-link stats (times shown / success rate) for the
    note's Refs line. Fully optional -- any failure (no DB, bad ticket id)
    returns the links unchanged so the note never breaks on this."""
    try:
        from uuid import UUID
        from app.db.session import SessionLocal
        from app.agents.kb import record_ref_link_recommendation
        tid = UUID(str(ticket_id))
    except Exception:
        return links
    db = None
    try:
        db = SessionLocal()
        annotated = []
        for ln in links:
            url = ln.get("url")
            if not url:
                annotated.append(ln)
                continue
            stats = record_ref_link_recommendation(db, tid, url, ln.get("title", ""))
            annotated.append({**ln, **stats})
        return annotated
    except Exception:
        return links
    finally:
        if db is not None:
            db.close()


# One supervisor for the app: state store is shared (Redis/in-memory),
# audit goes to Postgres ai_audit_log via the existing SessionLocal pattern.
_orchestrator = Orchestrator(
    agents=default_agents(
        prior_resolution_fetcher=_live_prior_resolution_fetcher,
        feedback_stats=_live_feedback_stats,
    ),
    audit=AuditLogger(db_sink=postgres_audit_sink),
)


class WebhookEvent(BaseModel):
    """Event ServiceNow/D365 sends when a ticket is created/transferred/reactivated.

    Only ticket_id is required. event_type is inferred if omitted. Any extra
    fields ServiceNow sends are accepted and forwarded to the agents as context.
    """
    model_config = ConfigDict(extra="allow")  # tolerate any extra ServiceNow fields

    ticket_id: str = Field(..., description="ServiceNow sys_id or ticket number")
    event_id: Optional[str] = Field(None, description="Unique id of THIS delivery; used for dedupe")
    event_type: Optional[str] = Field(None, description="create | transfer | reactivate (inferred if omitted)")
    priority: Optional[str] = Field(None, description="e.g. P1..P3")
    assigned_team: Optional[str] = Field(None, description="Currently assigned team")
    previous_team: Optional[str] = Field(None, description="Prior team (signals a transfer)")
    reactivation_count: Optional[int] = Field(None, description="Times reopened (>0 signals reactivation)")
    title: Optional[str] = Field(None, description="Ticket short description / title")
    description: Optional[str] = Field(None, description="Ticket full description")
    severity: Optional[str] = Field(None, description="Severity / impact")
    status: Optional[str] = Field(None, description="Ticket status")


class Decision(BaseModel):
    ticket_id: str = Field(..., description="The ticket the engineer is responding to")
    decision: str = Field(..., description="accept | reject")


def _summary(record: Optional[OrchestrationRecord]) -> dict:
    if record is None:
        return {"status": "ignored", "detail": "duplicate or unknown event"}
    return {
        "ticket_id": record.ticket_id,
        "event_type": record.event_type,
        "pipeline": record.pipeline,
        "current_agent": record.current_agent,
        "state": record.state,
        "advisories": record.advisories,
        "status_detail": record.status_detail,
    }


@router.post("/webhook")
def ingest_event(evt: WebhookEvent):
    """O-07: receive an ICM event and run the first agent in the pipeline."""
    record = _orchestrator.handle_event(evt.model_dump(exclude_none=True))
    return _summary(record)


class D365CaseEvent(BaseModel):
    """Payload the Power Automate flow (or a Dataverse webhook) POSTs when a new
    Case is created. Send the Case GUID as `id` (or `incidentid`), or the
    `ticketnumber`. Extra fields are tolerated."""
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    incidentid: Optional[str] = None
    ticketnumber: Optional[str] = None


@router.post("/d365-webhook")
def d365_webhook(evt: D365CaseEvent, x_webhook_secret: Optional[str] = Header(default=None)):
    """Event-driven entry point: a new D365 Case fires this (via Power Automate),
    so the AI note appears in SECONDS instead of waiting for the ~2-min poller.
    Runs the SAME analysis pipeline as the poller, and is idempotent
    (skips a Case that already has the AI note).

    Auth: if the WEBHOOK_SECRET env var is set, the caller MUST send the same
    value in the `X-Webhook-Secret` header."""
    secret = os.getenv("WEBHOOK_SECRET")
    if secret and x_webhook_secret != secret:
        raise HTTPException(status_code=401, detail="invalid webhook secret")

    from app.orchestrator.dataverse import DataverseClient, available
    if not available():
        raise HTTPException(status_code=503, detail="Dataverse not configured")
    client = DataverseClient()

    cid = (evt.id or evt.incidentid or "").strip()
    num = (evt.ticketnumber or "").strip()
    case = client.get_case(cid) if cid else (client.get_case_by_number(num) if num else None)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")

    from app.orchestrator.d365_runner import NOTE_SUBJECT
    from app.orchestrator.engine import select_engine, engine_name
    if client.case_has_note(case["id"], NOTE_SUBJECT):
        return {"status": "already_processed", "ticket": case["ticket_number"]}

    # De-dup: a slow (~20s) call makes Power Automate RETRY. The in-memory claim
    # blocks same-instance retries; the PERSISTENT placeholder note below blocks
    # retries on OTHER instances (Render may run more than one).
    from app.orchestrator.dedup import claim, release
    if not claim(case["id"]):
        return {"status": "already_processing", "ticket": case["ticket_number"]}
    # Drop a placeholder note immediately -> any concurrent retry now sees
    # case_has_note == True and returns 'already_processed' before posting.
    try:
        ann_id = client.create_case_note(
            case["id"], NOTE_SUBJECT, "<i>\U0001f916 AI analysis in progress…</i>")
    except Exception:
        ann_id = None
    try:
        corpus = client.list_cases(top=100, resolved_only=True)   # learn from closed cases only
        advisory, note = select_engine()(case, corpus, org_base=client.cfg["base"], link_stats_fn=_live_link_stats)
        if ann_id:
            client.update_case_note(ann_id, note)  # fill in the placeholder
        else:
            client.create_case_note(case["id"], NOTE_SUBJECT, note)
        from app.orchestrator.notify import notify_assigned_engineer
        notify_assigned_engineer(advisory, case)   # best-effort; never blocks the case
        from app.orchestrator.queues import move_case_to_queue
        team = (advisory.get("routing") or {}).get("recommended_team", "")
        move_case_to_queue(client, case["id"], team)  # best-effort; never blocks the case
        try:
            client.dedupe_case_notes(case["id"], NOTE_SUBJECT)  # backstop: collapse any race dup
        except Exception:
            pass
    except Exception:
        if ann_id:
            try:
                client.delete_note(ann_id)         # roll back the placeholder
            except Exception:
                pass
        release(case["id"])                        # allow a retry on hard failure
        raise

    return {"status": "processed", "ticket": case["ticket_number"],
            "engine": engine_name()}


@router.post("/check-handoffs")
def check_handoffs(x_webhook_secret: Optional[str] = Header(default=None)):
    """Run on a SCHEDULE (e.g. a Power Automate Recurrence flow every 15-30
    min) -- there's no event that fires when an engineer's shift simply ends,
    so this has to be polled for, unlike case-created which is event-driven.

    For every still-OPEN case that already has an AI note: if the
    currently-assigned engineer is no longer on shift/on-call, reassign to
    whoever's available now and post a HANDOFF note carrying the full
    conversation history forward, so the new engineer isn't starting cold.

    Auth: same WEBHOOK_SECRET as /d365-webhook, if set."""
    secret = os.getenv("WEBHOOK_SECRET")
    if secret and x_webhook_secret != secret:
        raise HTTPException(status_code=401, detail="invalid webhook secret")

    from app.orchestrator.dataverse import DataverseClient, available
    if not available():
        raise HTTPException(status_code=503, detail="Dataverse not configured")
    client = DataverseClient()

    from app.orchestrator.d365_runner import NOTE_SUBJECT
    from app.orchestrator.handoff import check_handoff, build_conversation_history, format_handoff_note, HANDOFF_NOTE_SUBJECT
    from app.orchestrator.notify import notify_assigned_engineer

    handed_off, errors = [], []
    for case in client.list_cases(top=200):
        if case.get("state") != 0:                          # only ACTIVE cases need a live engineer
            continue
        if not client.case_has_note(case["id"], NOTE_SUBJECT):
            continue                                        # not processed yet -- the webhook will catch it
        try:
            notes = client.list_case_notes(case["id"])
            latest_ai_note = next((n["notetext"] for n in reversed(notes)
                                    if n.get("subject") == NOTE_SUBJECT), "")
            result = check_handoff(case, latest_ai_note)
            if not result:
                continue
            history = build_conversation_history(notes)
            client.create_case_note(case["id"], HANDOFF_NOTE_SUBJECT, format_handoff_note(result, history))
            notify_assigned_engineer({"routing": {"assigned_engineer": result["new_engineer"]}}, case)
            handed_off.append(case.get("ticket_number"))
        except Exception as exc:                            # one bad case must not stop the run
            errors.append({"ticket": case.get("ticket_number"), "error": str(exc)})

    return {"handed_off": handed_off, "errors": errors}


@router.post("/decision")
def submit_decision(d: Decision):
    """O-09: engineer ACCEPT -> next agent; REJECT -> block + flag retraining."""
    try:
        record = _orchestrator.handle_decision(d.ticket_id, d.decision)
    except KeyError:
        raise HTTPException(status_code=404, detail="no orchestration state for ticket")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _summary(record)


@router.get("/state/{ticket_id}")
def get_state(ticket_id: str):
    """Inspect where a ticket currently sits in the pipeline."""
    record = _orchestrator.get_state(ticket_id)
    if record is None:
        raise HTTPException(status_code=404, detail="no orchestration state for ticket")
    return _summary(record)


@router.get("/health")
def health():
    """Liveness check for your teammate / ServiceNow connectivity test."""
    return {"status": "ok", "service": "orchestrator"}


@router.get("/recommendation", response_class=HTMLResponse)
def get_recommendation(case: str):
    """Return the AI recommendation for a Case as HTML (for the D365 pop-up
    dialog). Serves the latest saved note; if none exists yet, generates one,
    saves it, and returns it. CORS is open (see orchestrator_server.py)."""
    try:
        from app.orchestrator.dataverse import DataverseClient, available
        if not available():
            return "<p style='font-family:Segoe UI,Arial'>Service not configured.</p>"
        import urllib.parse
        client = DataverseClient()
        case = case.replace("{", "").replace("}", "").strip()
        params = {
            "$select": "notetext,createdon", "$top": "1", "$orderby": "createdon desc",
            "$filter": f"_objectid_value eq {case} and subject eq 'AI Support Recommendation'",
        }
        rows = (client._request("GET", "annotations?" + urllib.parse.urlencode(params)) or {}).get("value", [])
        if rows and rows[0].get("notetext"):
            try:
                client.dedupe_case_notes(case, "AI Support Recommendation")  # heal any race dup
            except Exception:
                pass
            return rows[0]["notetext"]                 # latest saved recommendation
        # none yet -> generate for DISPLAY ONLY. The webhook is the SINGLE writer of
        # timeline notes, so the pop-up never creates one -> it can't race the
        # webhook into a duplicate note.
        from app.orchestrator.d365_runner import process_case
        target = client.get_case(case)                            # the (open) case being viewed
        if not target:
            return "<p style='font-family:Segoe UI,Arial'>No recommendation found for this case.</p>"
        corpus = client.list_cases(top=100, resolved_only=True)   # learn from closed cases only
        _, note = process_case(target, corpus, org_base=client.cfg["base"], link_stats_fn=_live_link_stats)
        return note
    except Exception as exc:
        return f"<p style='font-family:Segoe UI,Arial'>Could not load recommendation: {exc}</p>"


def _compute_resolution_prediction(similar_incidents: list, kb_docs: list) -> dict | None:
    """Estimate resolution time from the top KB doc's workflow availability
    and top similar-case match confidence. Workflow-guided = engineer has
    clear steps = faster; manual = needs investigation = slower."""
    top_kb = kb_docs[0] if kb_docs else None
    if not top_kb:
        return None
    if top_kb.get("workflow_available"):
        low, high, unit, basis = 15, 45, "min", "Workflow-guided resolution"
    else:
        low, high, unit, basis = 1, 4, "hr", "Manual investigation required"
    top_sim = similar_incidents[0] if similar_incidents else None
    sim_score = float((top_sim or {}).get("display_score", 0))
    if sim_score >= 0.80:
        confidence, note = "high", f"{round(sim_score * 100)}% similar resolved case found"
    elif sim_score >= 0.55:
        confidence, note = "medium", "Moderately similar past cases found"
    else:
        confidence, note = "low", "Novel issue — estimate may vary"
    return {"range_low": low, "range_high": high, "unit": unit, "basis": basis,
            "confidence": confidence, "note": note,
            "workflow_guided": top_kb.get("workflow_available", False)}


def _compute_ticket_risk(ticket: dict, now) -> dict:
    """Heuristic risk score from priority, age, and severity keywords -- no API
    calls or embeddings, so it runs for every open ticket in the dashboard."""
    score = 0.0
    signals = []
    priority = ticket.get("priority", 2)
    if priority == 1:
        score += 0.4
        signals.append("High priority")
    created_on = ticket.get("created_on")
    age_hours = 0.0
    if created_on:
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(str(created_on).replace("Z", "+00:00"))
            age_hours = (now - dt).total_seconds() / 3600
        except Exception:
            pass
    if age_hours >= 12:
        score += 0.4
        signals.append(f"Open {int(age_hours)}h")
    elif age_hours >= 4:
        score += 0.2
        signals.append(f"Open {int(age_hours)}h")
    elif age_hours >= 0.5:
        signals.append(f"Open {round(age_hours, 1)}h")
    text = ((ticket.get("title") or "") + " " + (ticket.get("description") or "")[:200]).lower()
    severity_kw = ["outage", "down", "critical", "failing", "stuck", "failed", "broke", "error"]
    if any(k in text for k in severity_kw):
        score += 0.2
        signals.append("Severity keywords detected")
    score = min(round(score, 4), 1.0)
    level = "high" if score >= 0.5 else ("medium" if score >= 0.2 else "low")
    return {"score": score, "level": level, "signals": signals, "age_hours": round(age_hours, 1)}


_ESCALATION_KEYWORDS = [
    "escalate", "escalation", "manager", "supervisor", "urgent", "unacceptable",
    "disappointed", "frustrated", "complaint", "terrible", "legal", "cancel",
]

# Fields checked per domain; label → keywords that confirm the field is already present
_MISSING_INFO_KUBERNETES = [
    ("cluster name or ID", ["cluster name", "cluster id", "clusterid", "cluster:"]),
    ("Karpenter version", ["karpenter v", "version:", "karpenter version", "v0.", "v1."]),
    ("cloud provider region", ["us-east", "us-west", "eu-west", "eu-central", "ap-southeast",
                                "ap-northeast", "ap-south", "region:", "region "]),
    ("NodePool or EC2NodeClass name", ["nodepool", "node pool", "ec2nodeclass", "nodeclaim"]),
    ("error logs or kubectl output", ["kubectl", "error:", "failed:", "exception",
                                       "traceback", "logs:", "stderr", "output:"]),
]

_MISSING_INFO_FINANCE = [
    ("legal entity or company code", ["legal entity", "company code", "company:", "entity:"]),
    ("Finance module (GL/AP/AR/FA/Inventory)", ["general ledger", "accounts payable", "accounts receivable",
                                                 "fixed asset", "inventory", " gl ", " ap ", " ar ", " fa "]),
    ("error message from the infolog", ["infolog", "error:", "warning:", "failed to post",
                                         "cannot post", "blocked", "exception"]),
    ("voucher number or transaction date", ["voucher", "transaction date", "journal number",
                                             "invoice number", "posting date"]),
]

def _detect_domain(haystack: str) -> str:
    """Classify the ticket domain from its text for domain-aware missing-info checks."""
    finance_kws = ["general ledger", "accounts payable", "accounts receivable", "fixed asset",
                   "voucher", "ledger", "fiscal period", "d365 finance", "dynamics finance",
                   "journal posting", "vendor invoice", "customer invoice", "depreciation",
                   "inventory", "bill of materials", " gl ", " ap ", " ar "]
    if any(k in haystack for k in finance_kws):
        return "finance"
    return "kubernetes"


def _detect_missing_info(ticket: dict) -> dict | None:
    haystack = f"{ticket.get('title') or ''} {ticket.get('description') or ''}".lower()
    domain = _detect_domain(haystack)
    checks = _MISSING_INFO_FINANCE if domain == "finance" else _MISSING_INFO_KUBERNETES
    missing = [label for label, kws in checks if not any(k in haystack for k in kws)]
    raw_desc = (ticket.get("description") or "").strip()
    if len(raw_desc) < 120 and not missing:
        missing.append("detailed description (current description is too brief to diagnose)")
    if not missing:
        return None
    ticket_num = ticket.get("ticket_number") or ""
    fields_list = "\n".join(f"  • {f.capitalize()}" for f in missing)
    email = (
        f"Hi,\n\nThank you for contacting support regarding case {ticket_num}.\n\n"
        f"To investigate this issue efficiently, could you please provide the following details:\n\n"
        f"{fields_list}\n\n"
        f"Once we have this information we will proceed with the investigation immediately.\n\n"
        f"Best regards,\nSupport Team"
    )
    return {"missing_fields": missing, "suggested_email": email}


def _line1_context(client, target: dict) -> dict | None:
    """Read human-written case notes to surface what Line 1 has already tried.
    Returns None if no notes exist (ticket is brand new / unopened)."""
    try:
        case_id = target.get("id")
        if not case_id:
            return None
        notes = client.list_case_notes(case_id, top=15)
        human = [n for n in notes
                 if not (n.get("subject") or "").startswith("AI ")
                 and (n.get("notetext") or "").strip()]
        if not human:
            return None
        tried = [(n.get("notetext") or "").strip()[:300] for n in human[:3]]
        return {"note_count": len(human), "tried": tried}
    except Exception:
        return None


def _customer_comm_gap(client, target: dict) -> dict | None:
    try:
        from datetime import datetime, timezone
        case_id = target.get("id")
        if not case_id:
            return None
        notes = client.list_case_notes(case_id, top=20)
        human_notes = [n for n in notes if not (n.get("subject") or "").startswith("AI ")]
        now = datetime.now(timezone.utc)
        if not human_notes:
            raw = target.get("created_on") or target.get("createdon")
            if not raw:
                return None
            t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            hrs = (now - t).total_seconds() / 3600
            return {"hours_since_update": round(hrs, 1), "no_notes": True} if hrs >= 4 else None
        raw = human_notes[0].get("createdon") or human_notes[0].get("created_on")
        if not raw:
            return None
        t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        hrs = (now - t).total_seconds() / 3600
        return {"hours_since_update": round(hrs, 1), "no_notes": False} if hrs >= 4 else None
    except Exception:
        return None


def _cluster_open_tickets(client, target: dict, org_base: str = "",
                           threshold: float = 0.55, top: int = 25) -> None | dict:
    """Find other currently open tickets that are significantly similar to the
    target, suggesting they share the same root cause. Returns None (silently)
    if embeddings aren't configured, no open tickets exist, or nothing clears
    the similarity threshold -- so the section never appears for a lone ticket."""
    try:
        from app.orchestrator.similarity import rank_similar
        from app.orchestrator.d365_runner import case_url
        open_cases = client.list_cases(top=top, resolved_only=False)
        others = [c for c in open_cases
                  if c.get("id") != target.get("id")
                  and c.get("state") == 0
                  and not (c.get("title") or "").startswith("[k8s]")]
        if not others:
            return None
        ranked = rank_similar(target, others, top_k=len(others), min_score=0.0)
        matches = [r for r in ranked if r.get("display_score", 0) >= threshold]
        if not matches:
            return None
        tickets = [
            {"ticket_number": m.get("ticket_number"), "title": m.get("title"),
             "url": case_url(org_base, m.get("id")),
             "match_score": round(float(m.get("display_score", 0)), 4)}
            for m in matches[:5]
        ]
        return {"count": len(matches), "tickets": tickets}
    except Exception:
        return None


def _escalation_risk(client, target: dict) -> None | dict:
    """Predict escalation risk from the case's note history and ticket metadata.
    Returns None when there are no risk signals (no section shown for quiet tickets).
    Never raises -- if Dataverse notes can't be fetched, returns None silently."""
    try:
        from datetime import datetime, timezone, timedelta
        case_id = target.get("id")
        if not case_id:
            return None
        notes = client.list_case_notes(case_id, top=30)
        customer_notes = [n for n in notes
                          if not (n.get("subject") or "").startswith("AI ")]
        signals = []
        score = 0.0

        all_text = " ".join((n.get("notetext") or "") for n in customer_notes).lower()
        found_kw = [k for k in _ESCALATION_KEYWORDS if k in all_text]
        if found_kw:
            signals.append(f"Escalation language detected: {', '.join(found_kw[:3])}")
            score += 0.4

        if len(customer_notes) >= 4:
            signals.append(f"{len(customer_notes)} follow-up messages on this ticket")
            score += 0.3
        elif len(customer_notes) >= 2:
            signals.append(f"{len(customer_notes)} follow-up messages on this ticket")
            score += 0.15

        now = datetime.now(timezone.utc)
        recent = []
        for n in customer_notes:
            cd = n.get("createdon")
            if cd:
                try:
                    dt = datetime.fromisoformat(str(cd).replace("Z", "+00:00"))
                    if dt >= now - timedelta(hours=24):
                        recent.append(n)
                except Exception:
                    pass
        if len(recent) >= 3:
            signals.append(f"{len(recent)} messages in the last 24 hours")
            score += 0.25

        if target.get("priority") == 1:
            signals.append("High priority ticket")
            score += 0.1

        score = min(round(score, 4), 1.0)
        if not signals:
            return None
        level = "high" if score >= 0.5 else ("medium" if score >= 0.25 else "low")
        return {"level": level, "score": score, "signals": signals}
    except Exception:
        return None


def _kb_recommendations(team: str, title: str, description: str, top_k: int = 3) -> dict:
    """KB Recommendations cards for the popup: top_k articles from the static
    catalog, keyword-matched against the routed team + ticket text (same
    approach as workflows.py -- no database required).

    Returns {"docs": [...], "gap_detected": bool}. gap_detected=True when no
    catalog doc matched by keyword, meaning there is no KB article yet for this
    issue type -- the frontend shows a notice so the team knows to create one."""
    from app.orchestrator.kb_catalog import match_kb_docs
    docs, gap_detected = match_kb_docs(team, title, description, top_k=top_k)
    out = []
    for i, doc in enumerate(docs):
        base = doc["success_rate"]
        bump = 0.15 if doc["workflow_available"] else -0.10
        confidence = max(0.05, min(0.97, base + bump))
        out.append({**doc, "confidence": round(confidence, 4), "top_pick": i == 0})
    return {"docs": out, "gap_detected": gap_detected}


@router.get("/recommendation-data")
def get_recommendation_data(case: str):
    """Structured JSON for the rich card-based popup (incident trends with
    real ticket links, executive summary, KB recommendations with
    success-rate/workflow steps, and the recommended-assignment card).
    Always regenerates -- this is DISPLAY ONLY, same non-writing rule as
    /recommendation; the webhook remains the single writer of timeline notes."""
    from app.orchestrator.dataverse import DataverseClient, available
    if not available():
        raise HTTPException(status_code=503, detail="Dataverse not configured")
    client = DataverseClient()
    case = case.replace("{", "").replace("}", "").strip()
    target = client.get_case(case)
    if not target:
        raise HTTPException(status_code=404, detail="case not found")

    from app.orchestrator.d365_runner import process_case
    corpus = client.list_cases(top=100, resolved_only=True)
    advisory, _ = process_case(target, corpus, org_base=client.cfg["base"], link_stats_fn=_live_link_stats)

    r = advisory.get("routing") or {}
    d = advisory.get("diagnosis") or {}
    eng = r.get("assigned_engineer") or {}

    kb = _kb_recommendations(
        r.get("recommended_team") or "", target.get("title") or "", target.get("description") or "")

    cluster = _cluster_open_tickets(client, target, org_base=client.cfg["base"])
    escalation = _escalation_risk(client, target)
    missing_info = _detect_missing_info(target)
    comm_gap = _customer_comm_gap(client, target)
    line1_ctx = _line1_context(client, target)

    # Detect L2 and L3 escalation status
    from app.orchestrator.l2_escalation import detect_existing_escalation, detect_existing_l3_escalation
    all_notes_for_l2 = client.list_case_notes(target["id"], top=30)
    l2_escalation_status = detect_existing_escalation(all_notes_for_l2)
    l3_escalation_status = detect_existing_l3_escalation(all_notes_for_l2)

    # Auto-resolve: top similar case with >= 90% display score is near-identical
    # -- surface it so the engineer can apply the same resolution in one step.
    similar_incidents = d.get("similar_incidents") or []
    top_sim = similar_incidents[0] if similar_incidents else None
    auto_resolve = None
    if top_sim and top_sim.get("display_score", 0) >= 0.90:
        auto_resolve = {
            "available": True,
            "match_score": round(float(top_sim.get("display_score", 0)), 4),
            "matched_ticket": top_sim.get("ticket_number"),
            "matched_title": top_sim.get("title"),
            "resolution_text": (top_sim.get("description") or "")[:600],
            "url": top_sim.get("url"),
        }

    # SLA breach risk: compare time remaining against the top KB doc's average
    # resolution time. If the clock is tighter than what similar cases typically
    # needed, flag it before the breach happens rather than after.
    sla_obj = dict(advisory.get("sla") or {})
    mins_left = sla_obj.get("minutes_to_resolution_deadline")
    top_kb = kb["docs"][0] if kb["docs"] else None
    avg_hrs = top_kb.get("avg_resolution_hours") if top_kb else None
    if mins_left is not None and avg_hrs and not sla_obj.get("resolution_breached"):
        predicted_mins = avg_hrs * 60
        if mins_left < predicted_mins * 0.8:
            sla_obj["breach_risk"] = "critical"
        elif mins_left < predicted_mins * 1.5:
            sla_obj["breach_risk"] = "at_risk"

    return {
        "case": {"id": target.get("id"), "ticket_number": target.get("ticket_number"), "title": target.get("title")},
        "incident_trends": d.get("window_buckets") or {},
        "executive_summary": {
            "confidence": advisory.get("confidence"),
            "confidence_breakdown": advisory.get("confidence_breakdown"),
            "current_issue": target.get("description") or target.get("title"),
            "probable_cause": d.get("root_cause"),
            "grounded": d.get("grounded", True),
            "pattern_detected": d.get("pattern_detected"),
        },
        "kb_recommendations": kb["docs"],
        "kb_gap_detected": kb["gap_detected"],
        "auto_resolve": auto_resolve,
        "cluster": cluster,
        "escalation_risk": escalation,
        "resolution_prediction": _compute_resolution_prediction(similar_incidents, kb["docs"]),
        "recommended_assignment": {
            "team": r.get("recommended_team"), "team_confidence": r.get("confidence"),
            "engineer": eng or None,
        },
        "sla": sla_obj,
        "missing_info": missing_info,
        "customer_comm_gap": comm_gap,
        "line1_context": line1_ctx,
        "l2_escalation": l2_escalation_status,
        "l3_escalation": l3_escalation_status,
        "suggested_workflow": advisory.get("suggested_workflow"),
        "feedback": {
            "like_url": advisory.get("feedback_like_url"),
            "dislike_url": advisory.get("feedback_dislike_url"),
        },
    }


@router.get("/feedback", response_class=HTMLResponse)
def record_feedback(case: str, v: str = "like", comment: str = ""):
    """Clickable 👍/👎 from the Case note land here. Records the vote (and an
    optional free-text comment) as a feedback note on the Case and shows a small
    thank-you page. The in-dialog popup calls this and shows its own inline
    confirmation, so the returned HTML is only seen on direct link access.

    (Open GET on purpose so a plain link works; POC-grade -- add a signed token
    if you want to prevent casual re-voting.)"""
    verdict = "like" if str(v).lower() == "like" else "dislike"
    label = "\U0001f44d Helpful" if verdict == "like" else "\U0001f44e Not helpful"
    posted = False
    try:
        from app.orchestrator.dataverse import DataverseClient, available
        if available():
            text = f"Engineer rated the AI recommendation: {label}"
            if (comment or "").strip():
                text += f"\nComment: {comment.strip()}"
            DataverseClient().create_case_note(
                case, "AI Recommendation Feedback", text)
            posted = True
    except Exception:
        posted = False
    sub = "Recorded on the case — you can close this tab." if posted else "Thanks!"
    emoji = label.split(" ", 1)[0]
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Feedback</title></head>"
        "<body style='font-family:Segoe UI,Arial,sans-serif;text-align:center;padding:48px;color:#222'>"
        f"<div style='font-size:46px'>{emoji}</div>"
        "<h2>Thanks for your feedback!</h2>"
        f"<p style='color:#666'>{sub}</p></body></html>"
    )


@router.get("/ref-feedback", response_class=HTMLResponse)
def record_ref_feedback(case: str, kb: str, v: str = "like", comment: str = ""):
    """Per-document 👍/👎 from the Refs line -- distinct from /feedback, which
    rates the OVERALL recommendation. This tracks the success rate for the
    ONE specific reference document, feeding match_kb_articles()'s ranking."""
    verdict = "like" if str(v).lower() == "like" else "dislike"
    try:
        from uuid import UUID
        from app.db.session import SessionLocal
        from app.agents.kb import submit_kb_feedback, record_kb_outcome
        db = SessionLocal()
        try:
            tid, kid = UUID(case.replace("{", "").replace("}", "")), UUID(kb)
            submit_kb_feedback(db, ticket_id=tid, kb_id=kid, verdict=verdict, comment=comment)
            if verdict == "like":      # 👍 IS the success signal for this document
                record_kb_outcome(db, kid, resolved=True)
        finally:
            db.close()
    except Exception:
        pass
    try:
        from app.orchestrator.dataverse import DataverseClient, available
        if available():
            label = "\U0001f44d Helpful" if verdict == "like" else "\U0001f44e Not helpful"
            DataverseClient().create_case_note(case, "AI Reference Feedback",
                                                f"Engineer rated a cited reference document: {label}")
    except Exception:
        pass
    emoji = "\U0001f44d" if verdict == "like" else "\U0001f44e"
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Feedback</title></head>"
        "<body style='font-family:Segoe UI,Arial,sans-serif;text-align:center;padding:48px;color:#222'>"
        f"<div style='font-size:46px'>{emoji}</div>"
        "<h2>Thanks for rating this reference!</h2></body></html>"
    )


@router.get("/refine", response_class=HTMLResponse)
def refine_recommendation(case: str, comment: str = ""):
    """Regenerate the recommendation for a Case, taking the engineer's 👎 comment
    into account, and return the new note HTML for the pop-up. DISPLAY ONLY --
    does not overwrite the timeline note (the webhook is the single writer)."""
    try:
        from app.orchestrator.dataverse import DataverseClient, available
        if not available():
            return "<p style='font-family:Segoe UI,Arial'>Service not configured.</p>"
        client = DataverseClient()
        case = case.replace("{", "").replace("}", "").strip()
        target = client.get_case(case)
        if not target:
            return "<p style='font-family:Segoe UI,Arial'>Case not found.</p>"
        from app.orchestrator.d365_runner import process_case
        corpus = client.list_cases(top=100, resolved_only=True)
        _, note = process_case(target, corpus, org_base=client.cfg["base"],
                               link_stats_fn=_live_link_stats, feedback=(comment or ""))
        return note
    except Exception as exc:
        return f"<p style='font-family:Segoe UI,Arial'>Could not refine: {exc}</p>"


@router.get("/manager-dashboard-ui", response_class=HTMLResponse)
def get_manager_dashboard_ui():
    """Serves the manager dashboard HTML page directly (avoids static-file path issues)."""
    import pathlib
    html_path = (pathlib.Path(__file__).parent.parent.parent.parent / "d365" / "manager_dashboard.html")
    if not html_path.is_file():
        raise HTTPException(status_code=404, detail="Dashboard page not found")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@router.get("/manager-dashboard")
def get_manager_dashboard():
    """Queue-level view for managers: all open tickets ranked by risk score
    (priority + age + severity keywords). Pure heuristic — no LLM or embedding
    calls, so it returns fast enough for a live manager refresh."""
    from datetime import datetime, timezone
    from app.orchestrator.dataverse import DataverseClient, available
    if not available():
        raise HTTPException(status_code=503, detail="Dataverse not configured")
    client = DataverseClient()
    org_base = client.cfg["base"]
    open_cases = client.list_cases(top=50, resolved_only=False)
    tickets = [c for c in open_cases
               if c.get("state") == 0
               and not (c.get("title") or "").startswith("[k8s]")]
    now = datetime.now(timezone.utc)
    from app.orchestrator.d365_runner import case_url
    result = []
    for t in tickets:
        risk = _compute_ticket_risk(t, now)
        result.append({**t, "url": case_url(org_base, t.get("id")), "risk": risk})
    result.sort(key=lambda x: (-x["risk"]["score"], -x["risk"].get("age_hours", 0)))
    high_risk = sum(1 for r in result if r["risk"]["level"] == "high")
    medium_risk = sum(1 for r in result if r["risk"]["level"] == "medium")
    return {"total_open": len(result), "high_risk": high_risk,
            "medium_risk": medium_risk, "tickets": result}


@router.post("/escalate-to-l2")
def escalate_to_l2_manual(case: str):
    """Manual L1 → L2 escalation triggered by the L1 engineer from the popup.

    Finds the best available L2/L3 engineer, posts the full context note to
    Dataverse, and returns the assigned engineer details so the popup can confirm.
    Idempotent: returns the existing escalation if one has already been posted."""
    from app.orchestrator.dataverse import DataverseClient, available
    if not available():
        raise HTTPException(status_code=503, detail="Dataverse not configured")

    client = DataverseClient()
    case = case.replace("{", "").replace("}", "").strip()
    target = client.get_case(case)
    if not target:
        raise HTTPException(status_code=404, detail="case not found")

    from app.orchestrator.l2_escalation import (
        L2_NOTE_SUBJECT, detect_existing_escalation,
        find_l2_engineer, build_escalation_note, parse_l1_engineer,
    )
    from app.orchestrator.d365_runner import NOTE_SUBJECT
    from app.orchestrator.sla import sla_status
    from datetime import datetime, timezone as _tz

    notes = client.list_case_notes(target["id"], top=30)

    # Idempotent — if already escalated return existing info
    existing = detect_existing_escalation(notes)
    if existing:
        return {"already_escalated": True, **existing}

    # Build SLA info for the note
    created_raw = target.get("created_on") or target.get("createdon") or ""
    try:
        created_dt = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
    except Exception:
        created_dt = datetime.now(_tz.utc)
    sla = sla_status(target.get("priority", 2), created_dt)

    # Find L1 engineer from the AI note
    ai_note_text = next(
        (n["notetext"] for n in reversed(notes) if n.get("subject") == NOTE_SUBJECT), ""
    )
    l1_eng = parse_l1_engineer(ai_note_text)

    team = target.get("specialty") or "Provisioning / scheduling"
    l2_eng = find_l2_engineer(
        team,
        target.get("title", ""),
        target.get("description", ""),
        exclude_email=(l1_eng or {}).get("email", ""),
    )
    if not l2_eng:
        raise HTTPException(status_code=422, detail="No L2 engineer available in the roster")

    note_body = build_escalation_note(target, l1_eng, l2_eng, notes, ai_note_text, sla)
    client.create_case_note(target["id"], L2_NOTE_SUBJECT, note_body)

    return {
        "escalated": True,
        "l2_engineer_name": l2_eng["name"],
        "l2_engineer_email": l2_eng["email"],
        "l2_seniority": l2_eng["seniority"],
        "l2_team": l2_eng["team"],
        "escalated_at": datetime.now(_tz.utc).strftime("%Y-%m-%d %H:%M"),
        "note_preview": note_body[:800],
    }


@router.post("/escalate-to-l3")
def escalate_to_l3_manual(case: str):
    """Manual L2 → L3 escalation triggered by the L2 engineer from the popup.

    Only callable after a ticket has been escalated to L2. Finds the best L3
    engineer, posts a context note to Dataverse, and returns assignment details.
    Idempotent: returns the existing escalation if one has already been posted."""
    from app.orchestrator.dataverse import DataverseClient, available
    if not available():
        raise HTTPException(status_code=503, detail="Dataverse not configured")

    client = DataverseClient()
    case = case.replace("{", "").replace("}", "").strip()
    target = client.get_case(case)
    if not target:
        raise HTTPException(status_code=404, detail="case not found")

    from app.orchestrator.l2_escalation import (
        L3_NOTE_SUBJECT, detect_existing_l3_escalation, detect_existing_escalation,
        find_l3_engineer, build_l3_escalation_note,
    )
    from app.orchestrator.sla import sla_status
    from datetime import datetime, timezone as _tz

    notes = client.list_case_notes(target["id"], top=30)

    existing = detect_existing_l3_escalation(notes)
    if existing:
        return {"already_escalated": True, **existing}

    l2_info = detect_existing_escalation(notes)
    l2_eng = None
    if l2_info:
        l2_eng = {"name": l2_info.get("l2_engineer_name", ""), "email": l2_info.get("l2_engineer_email", "")}

    created_raw = target.get("created_on") or target.get("createdon") or ""
    try:
        created_dt = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
    except Exception:
        created_dt = datetime.now(_tz.utc)
    sla = sla_status(target.get("priority", 2), created_dt)

    team = target.get("specialty") or "Provisioning / scheduling"
    l3_eng = find_l3_engineer(
        team,
        target.get("title", ""),
        target.get("description", ""),
        exclude_email=(l2_eng or {}).get("email", ""),
    )
    if not l3_eng:
        raise HTTPException(status_code=422, detail="No L3 engineer available in the roster")

    note_body = build_l3_escalation_note(target, l2_eng, l3_eng, notes, sla)
    client.create_case_note(target["id"], L3_NOTE_SUBJECT, note_body)

    return {
        "escalated": True,
        "l3_engineer_name": l3_eng["name"],
        "l3_engineer_email": l3_eng["email"],
        "l3_seniority": l3_eng["seniority"],
        "l3_team": l3_eng["team"],
        "escalated_at": datetime.now(_tz.utc).strftime("%Y-%m-%d %H:%M"),
    }


@router.post("/check-escalations")
def check_escalations(x_webhook_secret: Optional[str] = Header(default=None)):
    """Run on a schedule (e.g. every 15 min via Power Automate Recurrence).

    For every open ticket whose SLA is breached or critically at risk:
    - Find an available L2/L3 engineer from the roster
    - Post a comprehensive escalation note to Dataverse carrying all L1 context
      (what L1 understood, what was tried, full customer communications)
    - Skip tickets that already have an L2 escalation note

    Auth: same WEBHOOK_SECRET as /d365-webhook, if set."""
    secret = os.getenv("WEBHOOK_SECRET")
    if secret and x_webhook_secret != secret:
        raise HTTPException(status_code=401, detail="invalid webhook secret")

    from app.orchestrator.dataverse import DataverseClient, available
    if not available():
        raise HTTPException(status_code=503, detail="Dataverse not configured")

    from app.orchestrator.d365_runner import NOTE_SUBJECT
    from app.orchestrator.l2_escalation import (
        L2_NOTE_SUBJECT, should_escalate, find_l2_engineer,
        build_escalation_note, parse_l1_engineer,
    )

    client = DataverseClient()
    open_cases = [c for c in client.list_cases(top=200) if c.get("state") == 0]

    escalated, skipped, errors = [], [], []

    for case in open_cases:
        try:
            notes = client.list_case_notes(case["id"], top=30)

            # Build a minimal SLA dict from ticket age so we can check breach
            from app.orchestrator.sla import sla_status
            from datetime import datetime, timezone as _tz
            created_raw = case.get("created_on") or case.get("createdon") or ""
            try:
                created_dt = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
            except Exception:
                created_dt = datetime.now(_tz.utc)
            sla = sla_status(case.get("priority", 2), created_dt)

            if not should_escalate(sla, notes):
                skipped.append(case.get("ticket_number"))
                continue

            # Find the L1 engineer name from the latest AI note
            ai_note_text = next(
                (n["notetext"] for n in reversed(notes) if n.get("subject") == NOTE_SUBJECT), ""
            )
            l1_eng = parse_l1_engineer(ai_note_text)

            team = case.get("specialty") or "Provisioning / scheduling"
            l2_eng = find_l2_engineer(
                team,
                case.get("title", ""),
                case.get("description", ""),
                exclude_email=(l1_eng or {}).get("email", ""),
            )
            if not l2_eng:
                errors.append({"ticket": case.get("ticket_number"), "error": "No L2 engineer available"})
                continue

            note_body = build_escalation_note(case, l1_eng, l2_eng, notes, ai_note_text, sla)
            client.create_case_note(case["id"], L2_NOTE_SUBJECT, note_body)
            escalated.append({
                "ticket": case.get("ticket_number"),
                "l2_engineer": l2_eng["name"],
                "l2_email": l2_eng["email"],
            })

        except Exception as exc:
            errors.append({"ticket": case.get("ticket_number"), "error": str(exc)})

    return {
        "escalated": escalated,
        "skipped_count": len(skipped),
        "errors": errors,
    }
