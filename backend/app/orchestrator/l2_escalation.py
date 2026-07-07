"""
Automatic L1 → L2 escalation.

Triggers when a ticket's SLA is breached (or critically at risk) and the ticket
has not already been escalated. Finds an available L2/L3 engineer from the roster,
then posts a comprehensive escalation note to Dataverse carrying all L1 context
forward so the L2 engineer never starts cold.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from app.orchestrator.roster import (
    _best_match, is_on_shift, load_roster, remaining_shift_minutes,
)

L2_NOTE_SUBJECT = "AI L2 Escalation"

_ASSIGNED_RE = re.compile(r"Assigned engineer:\s*([^\n(<]+?)(?:\s*\(([^)]+)\))?[\n<]")


def parse_l1_engineer(note_text: str) -> Optional[dict]:
    m = _ASSIGNED_RE.search(note_text or "")
    if not m:
        return None
    return {"name": m.group(1).strip(), "email": (m.group(2) or "").strip()}


def find_l2_engineer(team: str, title: str, description: str,
                     exclude_email: str = "") -> Optional[dict]:
    """Pick the best available L2 engineer for escalation.

    Strictly follows L1 → L2 → L3 hierarchy: only promotes to L3 when
    no L2 engineer is available at all, so the caller (popup button) always
    escalates to the next level, never skipping one.
    """
    roster = load_roster()

    def _pool(seniorities: list[str]) -> list[dict]:
        return [e for e in roster
                if e.get("seniority", "").upper() in seniorities
                and e.get("email", "") != exclude_email]

    # Strict ordering: L2 first, then L3, then anyone who isn't L1
    l2_pool = _pool(["L2"]) or _pool(["L3"]) or _pool(["L2", "L3"])
    if not l2_pool:
        l2_pool = [e for e in roster
                   if e.get("seniority", "").upper() != "L1"
                   and e.get("email", "") != exclude_email]
    if not l2_pool:
        return None

    on_shift = [e for e in l2_pool if is_on_shift(e)]
    on_call  = [e for e in l2_pool if e.get("on_call")]
    pool = on_shift or on_call or l2_pool

    candidates, _, _ = _best_match(pool, team, f"{title} {description}")
    if not candidates:
        candidates = pool

    candidates.sort(key=lambda e: (
        -(e["capacity"] - e["load"]),
        not is_on_shift(e),
        not e.get("on_call"),
    ))
    chosen = candidates[0]
    rem = remaining_shift_minutes(chosen)
    spare = chosen["capacity"] - chosen["load"]

    avail = "on shift" if is_on_shift(chosen) else ("on-call" if chosen.get("on_call") else "off shift")
    reason = (f"{chosen['seniority']} specialist for '{chosen['specialty']}'; {avail}; "
              f"spare capacity {spare} ({chosen['load']}/{chosen['capacity']})")
    if rem is not None:
        reason += f"; {rem // 60}h {rem % 60}m left in shift"

    return {
        "name": chosen["name"], "email": chosen["email"],
        "team": chosen["specialty"], "seniority": chosen["seniority"],
        "on_shift": is_on_shift(chosen), "on_call": chosen.get("on_call", False),
        "capacity": chosen["capacity"], "load": chosen["load"],
        "skills": chosen.get("skills", []),
        "remaining_shift_minutes": rem,
        "reason": reason,
    }


def should_escalate(sla: Optional[dict], notes: list[dict]) -> bool:
    """Return True when the ticket meets the auto-escalation criteria."""
    if not sla:
        return False
    # Trigger: SLA breached OR critical breach risk
    if not (sla.get("resolution_breached") or sla.get("breach_risk") == "critical"):
        return False
    # Do not escalate twice
    return not any(
        (n.get("subject") or "").startswith("AI L2 Escalation") for n in notes
    )


def build_escalation_note(case: dict, l1: Optional[dict], l2: dict,
                          notes: list[dict], ai_note: str,
                          sla: Optional[dict]) -> str:
    """Build the rich escalation note posted to Dataverse."""
    ticket_num = case.get("ticket_number", "")
    title = case.get("title", "")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sep = "=" * 52

    def esc(s: str) -> str:
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    parts: list[str] = [
        f"<b>AUTO L1 → L2 ESCALATION — {esc(ticket_num)}</b>",
        sep,
        f"<b>Ticket:</b> {esc(title)}",
        f"<b>Escalated at:</b> {now_str}",
        f"<b>L1 Engineer:</b> {esc(l1['name']) if l1 else 'Unknown'}"
        + (f" ({esc(l1['email'])})" if l1 and l1.get('email') else ""),
        f"<b>Assigned L2 Engineer:</b> {esc(l2['name'])} ({esc(l2['email'])})"
        + f" — {esc(l2['seniority'])} · {esc(l2['team'])}",
        "",
    ]

    # SLA status
    if sla:
        mins = sla.get("minutes_to_resolution_deadline", 0)
        clock = (f"OVERDUE by {-mins} min" if mins < 0 else f"{mins} min remaining")
        parts += [
            "── SLA STATUS ──",
            f"{esc(sla.get('tier', ''))} · Resolution {clock}"
            + (" · <b>SLA BREACHED</b>" if sla.get("resolution_breached") else ""),
            "",
        ]

    # What L1 understood — pull from AI note (strip HTML so we don't double-encode)
    parts.append("── WHAT L1 UNDERSTOOD ──")
    if ai_note:
        import re as _re
        plain = _re.sub(r"<[^>]+>", " ", ai_note)
        plain = plain.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ")
        plain = _re.sub(r" {2,}", " ", plain).strip()
        snippet = plain[:600]
        parts.append(esc(snippet) + ("…" if len(plain) > 600 else ""))
    else:
        parts.append("(AI analysis note not found)")
    parts.append("")

    # What L1 already tried — human notes only
    human_notes = [n for n in notes
                   if not (n.get("subject") or "").startswith("AI ")
                   and (n.get("notetext") or "").strip()]
    parts.append("── WHAT L1 ALREADY TRIED ──")
    if human_notes:
        for n in human_notes[:6]:
            when = (n.get("createdon") or "")[:16]
            text = (n.get("notetext") or "").strip()[:350]
            parts.append(f"[{esc(when)}] {esc(text)}")
    else:
        parts.append("No engineer notes recorded at L1 level.")
    parts.append("")

    # Full customer communication log
    comm_notes = [n for n in notes if (n.get("notetext") or "").strip()]
    parts.append("── ALL CUSTOMER COMMUNICATIONS ──")
    if comm_notes:
        for n in comm_notes:
            subj = esc(n.get("subject") or "(no subject)")
            when = esc((n.get("createdon") or "")[:16])
            text = esc((n.get("notetext") or "").strip()[:400])
            parts.append(f"[{when}] <b>{subj}</b>: {text}")
            parts.append("")
    else:
        parts.append("No communications recorded.")
    parts.append("")

    parts += [
        "── WHY ESCALATION WAS TRIGGERED ──",
        "• SLA breached or in critical breach risk",
        "• Ticket unresolved beyond L1 resolution window",
        "",
        f"<i>This note was generated automatically by the AI Insights system.</i>",
    ]

    return "<br>".join(parts)


def detect_existing_escalation(notes: list[dict]) -> Optional[dict]:
    """If an L2 escalation note exists, return its key fields for the popup."""
    for n in reversed(notes):
        if (n.get("subject") or "").startswith("AI L2 Escalation"):
            text = n.get("notetext") or ""
            # Parse L2 engineer name from the note
            m = re.search(r"Assigned L2 Engineer:</b>\s*([^\(]+)\(([^)]+)\)", text)
            name = m.group(1).strip() if m else ""
            email = m.group(2).strip() if m else ""
            when = (n.get("createdon") or "")[:16]
            return {
                "escalated": True,
                "l2_engineer_name": name,
                "l2_engineer_email": email,
                "escalated_at": when,
                "note_preview": text[:800],
            }
    return None
