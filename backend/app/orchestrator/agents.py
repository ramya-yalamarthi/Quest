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
TEAMS = {
    "Networking": "connectivity, VPN, DNS, firewall, routing, load balancers, inter-site latency",
    "Storage": "disks/volumes, blob/object storage, IOPS/throughput, storage latency, capacity, backups",
    "Integration": "APIs, webhooks, message queues, ETL/data pipelines, third-party syncs",
    "Identity": "authentication, SSO, login, MFA, RBAC/permissions, account lockouts, tokens/certs",
}

_ROUTING_SYSTEM = (
    "You are an IT support ticket ASSIGNMENT VALIDATOR. A user has created a ticket and "
    "assigned it to a team. Decide which single team SHOULD own the ticket based only on "
    "the issue described. Teams and what they handle: "
    + "; ".join(f"{k} = {v}" for k, v in TEAMS.items())
    + ". Respond ONLY as a JSON object with keys: "
    '"correct_team" (one of Networking, Storage, Integration, Identity), '
    '"confidence" (number 0-1), "reasoning" (one short sentence explaining why).'
)


class RoutingAgent:
    """UC1 - validates whether a ticket is assigned to the right team and, if not,
    recommends the correct team. LLM-powered (gpt-4o) with a safe fallback."""

    name = "routing"

    def run(self, context: dict) -> dict:
        ticket = context.get("ticket", {}) or {}
        payload = (context.get("event", {}) or {}).get("payload", {}) or {}
        title = ticket.get("title") or payload.get("title") or ""
        desc = ticket.get("description") or payload.get("description") or ""
        assigned = ticket.get("assigned_team") or payload.get("assigned_team") or "Unknown"

        result = chat_json(
            _ROUTING_SYSTEM,
            f"Ticket title: {title}\nDescription: {desc}\nUser-assigned team: {assigned}",
        )

        if not result or "correct_team" not in result:
            return {
                "title": "Assignment check",
                "assigned_team": assigned,
                "assignment_correct": None,
                "recommended_team": "Unknown",
                "mismatch": False,
                "confidence": 0.0,
                "reasoning": "LLM not configured - could not validate assignment.",
                "verdict": "Could not validate (no LLM).",
                "source": "fallback",
            }

        correct_team = str(result.get("correct_team", "Unknown")).strip()
        try:
            conf = round(float(result.get("confidence", 0) or 0), 2)
        except (TypeError, ValueError):
            conf = 0.0

        is_correct = assigned.strip().lower() == correct_team.lower()
        if is_correct:
            verdict = f"Assignment to '{assigned}' is CORRECT for this issue."
        else:
            verdict = (f"Assignment looks WRONG: this is a {correct_team} issue, "
                       f"not {assigned}. Recommend reassigning to {correct_team}.")

        return {
            "title": "Assignment validation",
            "assigned_team": assigned,
            "assignment_correct": is_correct,
            "recommended_team": correct_team,        # = assigned when correct
            "mismatch": not is_correct,              # kept for the reassign-on-accept logic
            "confidence": conf,
            "reasoning": result.get("reasoning", ""),
            "verdict": verdict,
            "source": "gpt-4o",
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
