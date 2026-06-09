"""
Sub-agents the supervisor dispatches to.

RoutingAgent and DiagnosisAgent are REAL (gpt-4o), grounded ONLY in a fixed set
of reference tickets. RecommendationAgent is still a stub. Each agent only needs
``run(context) -> dict``; the supervisor is unchanged.

  * Routing   -> is the assigned team correct? (minimal: team + confidence)
  * Diagnosis -> why / root cause + which reference ticket (+ link)
"""

import os
from typing import Protocol

from app.orchestrator.llm import chat_json, llm_available


class Agent(Protocol):
    name: str
    def run(self, context: dict) -> dict: ...


# Reference tickets (closed). Both agents match a NEW ticket against ONLY these.
REFERENCE_TICKETS = [
    {"number": "INC0010723", "sys_id": "1199ef76831d8b1044b2c955eeaad33d", "team": "Software",
     "summary": "Windows laptop fails to boot after an OS update; reboots into a recovery loop and never reaches the login screen."},
    {"number": "INC0010724", "sys_id": "9e1da77e831d8b1044b2c955eeaad37b", "team": "Database",
     "summary": "Production MS SQL Server is unresponsive and not accepting new connections; applications return 'connection timeout expired'."},
    {"number": "INC0010725", "sys_id": "80ae2b32835d8b1044b2c955eeaad3e1", "team": "Network",
     "summary": "User cannot connect to corporate VPN; client accepts username/password and MFA but then drops with 'negotiation failed'."},
    {"number": "INC0010726", "sys_id": "f5cfa3f2835d8b1044b2c955eeaad3a2", "team": "Hardware",
     "summary": "Workstation overheating and shutting down under load; CPU pinned at 100% with high temperatures."},
]

# ServiceNow instance for building reference links (overridable via env).
SN_INSTANCE = os.getenv("SN_INSTANCE_URL", "https://dev399415.service-now.com").rstrip("/")

_REF_BY_NUMBER = {t["number"]: t for t in REFERENCE_TICKETS}
_REF_BLOCK = "\n".join(
    f"- {t['number']} [team: {t['team']}]: {t['summary']}" for t in REFERENCE_TICKETS
)
_REF_TEAMS = sorted({t["team"] for t in REFERENCE_TICKETS})


def _ref_link(number: str) -> str:
    t = _REF_BY_NUMBER.get(number)
    return f"{SN_INSTANCE}/incident.do?sys_id={t['sys_id']}" if t else ""


def _ticket_fields(context: dict):
    ticket = context.get("ticket", {}) or {}
    payload = (context.get("event", {}) or {}).get("payload", {}) or {}
    title = payload.get("title") or ticket.get("title") or ""
    desc = payload.get("description") or ticket.get("description") or ""
    assigned = payload.get("assigned_team") or ticket.get("assigned_team") or "Unknown"
    return title, desc, assigned


# ---------------------------------------------------------------------------
# Routing Agent (UC1) -- validates the team assignment. Minimal output.
# ---------------------------------------------------------------------------
_ROUTING_SYSTEM = (
    "You are an IT support ticket ASSIGNMENT VALIDATOR. Classify the NEW ticket by "
    "matching it to the MOST SIMILAR reference ticket below, and recommend that reference "
    "ticket's team. Choose the team ONLY from the reference tickets "
    f"({', '.join(_REF_TEAMS)}); do not invent teams.\n\nREFERENCE TICKETS:\n" + _REF_BLOCK +
    '\n\nRespond ONLY as a JSON object with keys: '
    '"recommended_team" (team of the best-matching reference ticket), '
    '"confidence" (number 0-1).'
)


class RoutingAgent:
    name = "routing"

    def run(self, context: dict) -> dict:
        title, desc, assigned = _ticket_fields(context)
        result = chat_json(_ROUTING_SYSTEM, f"NEW ticket title: {title}\nDescription: {desc}")
        if not result or "recommended_team" not in result:
            return {"assigned_team": assigned, "assignment_correct": None,
                    "recommended_team": "Unknown", "confidence": "0%"}
        rec = str(result.get("recommended_team", "Unknown")).strip()
        try:
            conf = float(result.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            conf = 0.0
        return {
            "assigned_team": assigned,
            "assignment_correct": assigned.strip().lower() == rec.lower(),
            "recommended_team": rec,
            "confidence": f"{int(round(conf * 100))}%",
        }


# ---------------------------------------------------------------------------
# Diagnosis Agent (UC2) -- REAL: root cause + matched reference ticket (+ link).
# ---------------------------------------------------------------------------
_DIAGNOSIS_SYSTEM = (
    "You are an IT diagnosis assistant. Find the MOST SIMILAR reference ticket below to the "
    "NEW ticket and explain the likely root cause based on it.\n\nREFERENCE TICKETS:\n" + _REF_BLOCK +
    '\n\nRespond ONLY as a JSON object with keys: '
    '"reference" (the matched reference ticket number, e.g. INC0010724), '
    '"root_cause" (one short sentence), '
    '"reasoning" (one short sentence describing the matching symptoms only; '
    'do NOT mention any ticket number in the reasoning).'
)


class DiagnosisAgent:
    name = "diagnosis"

    def run(self, context: dict) -> dict:
        title, desc, _ = _ticket_fields(context)
        result = chat_json(_DIAGNOSIS_SYSTEM, f"NEW ticket title: {title}\nDescription: {desc}")
        if not result or "reference" not in result:
            return {"root_cause": "Unknown", "reasoning": "LLM not configured.",
                    "reference": "", "reference_link": ""}
        ref = str(result.get("reference", "")).strip()
        return {
            "root_cause": result.get("root_cause", ""),
            "reasoning": result.get("reasoning", ""),
            "reference": ref,
            "reference_link": _ref_link(ref),
        }


# ---------------------------------------------------------------------------
# Recommendation Agent (UC3) -- STUB (next to build)
# ---------------------------------------------------------------------------
class RecommendationAgentStub:
    name = "recommendation"

    def run(self, context: dict) -> dict:
        return {
            "title": "Two-track recommendation",
            "immediate_action": "Reset throttling rule (runbook RB-STORAGE-014), ~20 min.",
            "durable_fix": "Add autoscale policy for cache tier; raise burst quota (CM required).",
            "prevention": "Add a monitoring rule on p99 > 1500ms for 5 min.",
            "confidence": 0.78,
        }


def default_agents() -> dict[str, Agent]:
    return {
        "routing": RoutingAgent(),          # REAL (gpt-4o)
        "diagnosis": DiagnosisAgent(),      # REAL (gpt-4o)
        "recommendation": RecommendationAgentStub(),  # stub
    }


def routing_is_live() -> bool:
    return llm_available()
