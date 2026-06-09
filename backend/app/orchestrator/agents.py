"""
Sub-agents the supervisor dispatches to.

RoutingAgent is REAL (LLM-powered via gpt-4o) with a safe fallback when no LLM
is configured. Diagnosis and Recommendation are still stubs -- next to build.
Each agent only needs ``run(context) -> dict``; the supervisor is unchanged.
"""

from typing import Protocol

from app.orchestrator.llm import chat_json, llm_available


class Agent(Protocol):
    name: str
    def run(self, context: dict) -> dict: ...


# ---------------------------------------------------------------------------
# Routing Agent (UC1) -- REAL: classifies the ticket into a support team.
# ---------------------------------------------------------------------------
# Reference tickets (closed). The classifier matches a NEW ticket against ONLY
# these and assigns it to the best-matching reference ticket's team.
REFERENCE_TICKETS = [
    {"number": "INC0010723", "team": "Software",
     "summary": "Windows laptop fails to boot after an OS update; reboots into a recovery loop and never reaches the login screen."},
    {"number": "INC0010724", "team": "Database",
     "summary": "Production MS SQL Server is unresponsive and not accepting new connections; applications return 'connection timeout expired'."},
    {"number": "INC0010725", "team": "Network",
     "summary": "User cannot connect to corporate VPN; client accepts username/password and MFA but then drops with 'negotiation failed'."},
    {"number": "INC0010726", "team": "Hardware",
     "summary": "Workstation overheating and shutting down under load; CPU pinned at 100% with high temperatures."},
]

_REF_BLOCK = "\n".join(
    f"- {t['number']} [team: {t['team']}]: {t['summary']}" for t in REFERENCE_TICKETS
)
_REF_TEAMS = sorted({t["team"] for t in REFERENCE_TICKETS})

_ROUTING_SYSTEM = (
    "You are an IT support ticket ASSIGNMENT VALIDATOR. Classify the NEW ticket by "
    "matching it to the MOST SIMILAR reference ticket below, and recommend that reference "
    "ticket's team. You MUST choose the team ONLY from the reference tickets "
    f"({', '.join(_REF_TEAMS)}); do not invent or use any other team.\n\n"
    "REFERENCE TICKETS:\n" + _REF_BLOCK +
    '\n\nRespond ONLY as a JSON object with keys: '
    '"recommended_team" (team of the best-matching reference ticket), '
    '"reference" (that reference ticket number), '
    '"confidence" (number 0-1), "reasoning" (one short sentence).'
)


class RoutingAgent:
    """UC1 - validates a ticket's team assignment by matching it against a fixed
    set of reference tickets. LLM-powered (gpt-4o) with a safe fallback."""

    name = "routing"

    def run(self, context: dict) -> dict:
        ticket = context.get("ticket", {}) or {}
        payload = (context.get("event", {}) or {}).get("payload", {}) or {}
        # Prefer the real event payload (from ServiceNow) over the MCP mock.
        title = payload.get("title") or ticket.get("title") or ""
        desc = payload.get("description") or ticket.get("description") or ""
        assigned = payload.get("assigned_team") or ticket.get("assigned_team") or "Unknown"

        result = chat_json(_ROUTING_SYSTEM, f"NEW ticket title: {title}\nDescription: {desc}")

        if not result or "recommended_team" not in result:
            return {
                "assigned_team": assigned,
                "assignment_correct": None,
                "recommended_team": "Unknown",
                "confidence": "0%",
                "reasoning": "LLM not configured - could not validate assignment.",
                "reference": "",
            }

        rec = str(result.get("recommended_team", "Unknown")).strip()
        try:
            conf = float(result.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            conf = 0.0
        is_correct = assigned.strip().lower() == rec.lower()

        return {
            "assigned_team": assigned,
            "assignment_correct": is_correct,
            "recommended_team": rec,
            "confidence": f"{int(round(conf * 100))}%",
            "reasoning": result.get("reasoning", ""),
            "reference": result.get("reference", ""),
        }


# ---------------------------------------------------------------------------
# Diagnosis Agent (UC2) -- STUB (next to build)
# ---------------------------------------------------------------------------
class DiagnosisAgentStub:
    name = "diagnosis"

    def run(self, context: dict) -> dict:
        return {
            "title": "Root-cause diagnosis",
            "root_cause": "Storage throttling under burst load",
            "evidence_summary": "p99 latency 1840ms, error_rate 7% in last hour.",
            "runbook_ref": "RB-STORAGE-014",
            "ttm_estimate_minutes": 95,
            "confidence": 0.82,
            "source": "stub",
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
            "source": "stub",
        }


def default_agents() -> dict[str, Agent]:
    return {
        "routing": RoutingAgent(),               # REAL (gpt-4o)
        "diagnosis": DiagnosisAgentStub(),       # stub
        "recommendation": RecommendationAgentStub(),  # stub
    }


# convenience for callers/health checks
def routing_is_live() -> bool:
    return llm_available()
