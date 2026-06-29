"""Shift-based handoff: when the assigned engineer's shift ends before an
open ticket is resolved, reassign to someone available NOW, and carry the
conversation history forward so the new engineer doesn't start cold.

There's no separate persisted "currently assigned engineer" field (the D365
pipeline doesn't write one back to Dataverse) -- the only record of who's
assigned is the text of the latest AI note, so that's what we parse.
"""
from __future__ import annotations

import re
from typing import Optional

from app.orchestrator.roster import assign_engineer, is_on_shift, load_roster

_ASSIGNED_RE = re.compile(r"Assigned engineer:\s*([^(]+)\(([^)]+)\)")

HANDOFF_NOTE_SUBJECT = "AI Handoff"


def parse_assigned_engineer(note_text: str) -> Optional[dict]:
    """Pull the currently-assigned engineer's name/email out of the latest AI
    note text."""
    m = _ASSIGNED_RE.search(note_text or "")
    if not m:
        return None
    return {"name": m.group(1).strip(), "email": m.group(2).strip()}


def build_conversation_history(notes: list[dict], max_chars: int = 300) -> str:
    """Chronological digest of everything logged on the case so far -- handed
    to the new engineer on reassignment. '(no prior notes...)' if empty,
    never raises on malformed note rows."""
    lines = []
    for n in notes:
        subject = n.get("subject") or "(no subject)"
        text = (n.get("notetext") or "").strip()
        when = n.get("createdon") or ""
        snippet = text if len(text) <= max_chars else text[: max_chars - 3] + "..."
        lines.append(f"[{when}] {subject}: {snippet}")
    return "<br>".join(lines) if lines else "(no prior notes on this case)"


def check_handoff(case: dict, latest_assigned_text: str) -> Optional[dict]:
    """If the case is still ACTIVE and its currently-assigned engineer is no
    longer on shift or on-call, pick a new one (same logic as initial
    assignment -- the unavailable engineer is naturally excluded by the
    on-shift/on-call tiering) and return the handoff package. None if no
    handoff is needed or nobody else is available."""
    if case.get("state") not in (0, None):          # only ACTIVE cases need a live engineer
        return None
    current = parse_assigned_engineer(latest_assigned_text)
    if not current:
        return None
    roster = load_roster()
    current_eng = next((e for e in roster if e.get("email") == current["email"]), None)
    if current_eng is None:
        return None
    if is_on_shift(current_eng) or current_eng.get("on_call"):
        return None                                  # still available -- no handoff needed

    new_eng = assign_engineer(current_eng.get("specialty", ""), case.get("title", ""), case.get("description", ""))
    if not new_eng or new_eng.get("email") == current["email"]:
        return None                                  # nobody else available -- can't hand off

    return {"previous_engineer": current, "new_engineer": new_eng}


def format_handoff_note(result: dict, conversation_history: str) -> str:
    prev, new = result["previous_engineer"], result["new_engineer"]
    return (
        f"<b>HANDOFF</b> &mdash; {prev['name']}'s shift has ended; ticket is still open.<br>"
        f"Reassigned to: {new['name']} ({new['email']})<br>"
        f"Why: {new.get('reason', '')}<br>"
        f"<br><b>Conversation history so far:</b><br>{conversation_history}"
    )
