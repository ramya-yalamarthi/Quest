"""
Engineer roster + skill-based, shift-aware assignment.

The roster (who's on which specialty, current load, on-call status, shift) lives
in an Excel file -- backend/data/engineer_roster.xlsx -- not the database, so it
can be edited by ops without a migration. Override the path with the
ROSTER_PATH env var.

assign_engineer() picks the best engineer for a routed team: match the team
(and the ticket's own text) against each engineer's specialty/skills, but
ONLY among engineers who are actually awake right now (on-shift in their own
timezone, or on-call) -- an SLA clock doesn't care what timezone the customer
filed from; it cares whether the assignee is working at this moment.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone as dt_timezone
from functools import lru_cache
from typing import Optional
from zoneinfo import ZoneInfo

import openpyxl

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROSTER_PATH = os.getenv("ROSTER_PATH") or os.path.join(_BACKEND, "data", "engineer_roster.xlsx")

# Team (from RoutingAgent) -> extra keyword aliases beyond the team name itself,
# for matching against an engineer's specialty / skills tags.
_TEAM_ALIASES = {
    "Provisioning / scheduling": ["provisioning", "scheduling", "nodepool", "pending-pods"],
    "Autoscaling / scaling": ["autoscaling", "scaling", "capacity", "scale-down"],
    "Consolidation / disruption": ["consolidation", "disruption", "drift"],
    "Metrics / observability": ["metrics", "observability", "controller", "logs"],
    "Termination / eviction": ["termination", "eviction", "drain", "nodeclaim", "lifecycle"],
    "Instance types / pricing": ["instance-types", "instance types", "gpu", "spot", "pricing"],
    "Config / API (EC2NodeClass)": ["ec2nodeclass", "subnet", "iam", "ami", "aws", "config", "api"],
    "Networking": ["networking", "dns", "vpc", "tls"],
    "Docs": ["docs", "documentation"],
}


def _split_tags(s: str) -> list[str]:
    return [t.strip().lower() for t in re.split(r"[,/]", s or "") if t.strip()]


@lru_cache(maxsize=1)
def load_roster() -> list[dict]:
    """Read backend/data/engineer_roster.xlsx -> list of engineer dicts.
    Returns [] (never raises) if the file is missing or malformed, so a
    missing roster degrades to "no assignment" rather than breaking the case."""
    try:
        wb = openpyxl.load_workbook(ROSTER_PATH, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    except Exception:
        return []
    if not rows:
        return []
    header = [str(h or "").strip().lower() for h in rows[0]]

    def col(name: str):
        return header.index(name) if name in header else None

    idx = {
        "name": col("name"), "email": col("email"), "region": col("region"),
        "timezone": col("timezone"), "shift_hours": col("shift hours"),
        "specialty": col("specialty"), "skills": col("k8s skills"),
        "seniority": col("seniority"), "capacity": col("capacity"),
        "load": col("load"), "on_call": col("on-call"),
    }
    out = []
    for r in rows[1:]:
        if idx["name"] is None or not r[idx["name"]]:
            continue

        def get(key, default=None):
            i = idx[key]
            return r[i] if i is not None and i < len(r) else default

        out.append({
            "name": get("name", ""),
            "email": get("email", ""),
            "region": get("region", ""),
            "timezone": get("timezone", "") or "",
            "shift_hours": get("shift_hours", "") or "",
            "specialty": get("specialty", "") or "",
            "skills": _split_tags(get("skills", "")),
            "seniority": get("seniority", "") or "",
            "capacity": int(get("capacity", 0) or 0),
            "load": int(get("load", 0) or 0),
            "on_call": str(get("on_call", "")).strip().lower() == "yes",
        })
    return out


def _parse_minutes(hhmm: str) -> Optional[int]:
    m = re.match(r"^(\d{1,2}):(\d{2})$", hhmm.strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def is_on_shift(engineer: dict, now_utc: Optional[datetime] = None) -> bool:
    """True if `now_utc` falls within the engineer's shift window, computed in
    THEIR OWN timezone (not the customer's). Unparsable timezone/hours fail
    open as "unknown" (False) rather than crashing the assignment."""
    tz_name, hours = engineer.get("timezone"), engineer.get("shift_hours")
    if not tz_name or not hours or "-" not in hours:
        return False
    try:
        local_now = (now_utc or datetime.now(dt_timezone.utc)).astimezone(ZoneInfo(tz_name))
    except Exception:
        return False
    start_s, end_s = hours.split("-", 1)
    start, end = _parse_minutes(start_s), _parse_minutes(end_s)
    if start is None or end is None:
        return False
    now_min = local_now.hour * 60 + local_now.minute
    if start <= end:
        return start <= now_min < end
    return now_min >= start or now_min < end  # overnight shift (e.g. 22:00-06:00)


def _score(engineer: dict, team: str, text: str) -> tuple[int, int]:
    """(team_score, text_score) -- separated so the reason shown to the
    engineer reflects what actually matched."""
    keywords = [team.lower()] + [k.lower() for k in _TEAM_ALIASES.get(team, [])]
    haystack = (engineer["specialty"] + " " + " ".join(engineer["skills"])).lower()
    team_score = sum(1 for k in keywords if k and k in haystack)
    text_score = 0
    if text:
        text_l = text.lower()
        text_score = sum(1 for tag in engineer["skills"] if tag and tag in text_l)
    return team_score, text_score


def _best_match(roster: list[dict], team: str, text: str) -> tuple[list[dict], int, bool]:
    """Within `roster`, return (engineers tied for the best skill match,
    their team_score, whether anyone matched at all). Falls back to the
    whole pool (unmatched=False) if nobody's specialty/skills match."""
    scored = [(_score(e, team, text), e) for e in roster]
    best_total = max(t + x for (t, x), _ in scored)
    if best_total <= 0:
        return roster, 0, False
    matched = [e for (t, x), e in scored if t + x == best_total]
    best_team_score = max(t for (t, x), e in scored if e in matched)
    return matched, best_team_score, True


def assign_engineer(
    team: str, title: str = "", description: str = "", now_utc: Optional[datetime] = None,
) -> Optional[dict]:
    """Pick the best engineer for `team`, available NOW.

    An SLA clock runs against the assignee's wall clock, not the customer's --
    so candidates are tiered by real-time availability FIRST, skill match
    second:
      1. on-shift right now AND a specialty/skill match
      2. on-call right now (covers off-shift) AND a specialty/skill match
      3. on-shift right now, any specialty (best-effort cross-skill)
      4. on-call right now, any specialty
      5. last resort: least-loaded engineer regardless of availability,
         flagged as an SLA risk so it's visible on the case.
    Returns None only if the roster itself is empty."""
    roster = load_roster()
    if not roster:
        return None

    text = f"{title} {description}"
    on_shift = [e for e in roster if is_on_shift(e, now_utc)]
    on_call = [e for e in roster if e["on_call"]]

    shift_result = _best_match(on_shift, team, text) if on_shift else (None, 0, False)
    call_result = _best_match(on_call, team, text) if on_call else (None, 0, False)

    sla_risk = False
    if shift_result[2]:                              # tier 1: on-shift + real skill match
        candidates, team_score, matched = shift_result
        availability = "on shift right now"
    elif call_result[2]:                              # tier 2: on-call + real skill match
        candidates, team_score, matched = call_result
        availability = "off-shift, reached via on-call"
    elif on_shift:                                     # tier 3: on-shift, best-effort (no match anywhere)
        candidates, team_score, matched = shift_result
        availability = "on shift right now"
    elif on_call:                                      # tier 4: on-call, best-effort
        candidates, team_score, matched = call_result
        availability = "off-shift, reached via on-call"
    else:                                              # tier 5: nobody on-shift or on-call at all
        candidates, team_score, matched = _best_match(roster, team, text)
        availability = "no on-shift or on-call coverage found"
        sla_risk = True

    def spare(e):
        return e["capacity"] - e["load"]

    candidates.sort(key=lambda e: (-spare(e), not e["on_call"], -{"L3": 3, "L2": 2, "L1": 1}.get(e["seniority"], 0)))
    chosen = candidates[0]

    if team_score > 0:
        reason = f"Specialty match for '{team}'"
    elif matched:
        reason = "Skill-tag match against the case text"
    else:
        reason = f"No specialist found for '{team}'"
    reason += f"; {availability}"
    reason += f"; spare capacity {spare(chosen)} ({chosen['load']}/{chosen['capacity']})"
    if sla_risk:
        reason += " · ⚠ SLA RISK — no specialist currently working or on-call"

    return {
        "name": chosen["name"], "email": chosen["email"], "region": chosen["region"],
        "specialty": chosen["specialty"], "reason": reason, "sla_risk": sla_risk,
    }
