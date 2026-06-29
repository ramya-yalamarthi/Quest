"""SLA timers + internal Tier 1/2/3 split, derived from ticket priority.

Tiers are this app's OWN SLA commitment, not the raw D365 prioritycode --
prioritycode semantics (what "1" means) vary by org configuration, so we
parse the priority TEXT first (works for the Postgres '\U0001f534 P1 — Critical'
format and any plain text containing "critical"/"high"/"low" or "P1/P2/P3").
An unrecognized priority falls to Tier 3 (the slowest clock) -- fail open, so
an unparsed priority never triggers a false urgent-SLA-breach alert.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

# (response SLA, resolution SLA) per internal tier.
SLA_TIERS = {
    "Tier 1": {"response_minutes": 15, "resolution_hours": 4},
    "Tier 2": {"response_minutes": 60, "resolution_hours": 8},
    "Tier 3": {"response_minutes": 240, "resolution_hours": 24},
}


def classify_tier(priority) -> str:
    text = str(priority or "").lower()
    if re.search(r"\bp1\b", text) or "critical" in text:
        return "Tier 1"
    if re.search(r"\bp2\b", text) or "high" in text:
        return "Tier 2"
    if re.search(r"\bp3\b", text) or "low" in text or "normal" in text:
        return "Tier 3"
    try:
        # Dataverse prioritycode default: 1=High, 2=Normal, 3=Low.
        n = int(priority)
        return {1: "Tier 2", 2: "Tier 3", 3: "Tier 3"}.get(n, "Tier 3")
    except (TypeError, ValueError):
        return "Tier 3"


def sla_status(
    priority, created_at: datetime, now: Optional[datetime] = None,
    assigned_at: Optional[datetime] = None,
) -> dict:
    """Internal SLA timer for a ticket: tier, deadlines, and breach flags."""
    tier = classify_tier(priority)
    rules = SLA_TIERS[tier]
    now = now or datetime.now(timezone.utc)
    response_deadline = created_at + timedelta(minutes=rules["response_minutes"])
    resolution_deadline = created_at + timedelta(hours=rules["resolution_hours"])
    return {
        "tier": tier,
        "resolution_hours": rules["resolution_hours"],
        "response_deadline": response_deadline,
        "resolution_deadline": resolution_deadline,
        "response_breached": assigned_at is None and now > response_deadline,
        "resolution_breached": now > resolution_deadline,
        "minutes_to_resolution_deadline": round((resolution_deadline - now).total_seconds() / 60),
    }


# Below this fraction of the resolution window remaining (and not yet
# breached), nudge toward escalation/handoff before it actually breaches.
ESCALATION_WARNING_FRACTION = 0.25


def escalation_reminder(sla: dict) -> Optional[str]:
    """Handoff/escalation reminder text when a ticket is stuck too long
    against its SLA. None if there's nothing to flag yet."""
    if sla["resolution_breached"]:
        return "ESCALATE NOW — resolution SLA breached. Notify the team/escalation manager."
    window_minutes = sla["resolution_hours"] * 60
    if sla["minutes_to_resolution_deadline"] <= window_minutes * ESCALATION_WARNING_FRACTION:
        hours_left = sla["minutes_to_resolution_deadline"] / 60
        return f"HANDOFF REMINDER — only {hours_left:.1f}h left before SLA breach; escalate if still unresolved."
    return None
