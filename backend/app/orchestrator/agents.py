"""
Sub-agent stubs (stand-ins for Days 5-8).

The supervisor only needs each agent to expose ``run(context) -> dict``.  These
stubs return realistic-looking advisories so the pipeline runs end-to-end.
Replace each one with the real Routing / Diagnosis / Recommendation agent when
it's built -- the supervisor doesn't change as long as the interface holds.
"""

from typing import Protocol


class Agent(Protocol):
    name: str
    def run(self, context: dict) -> dict: ...


class RoutingAgentStub:
    """Day 5-6 Routing Agent placeholder: which team should own this ticket?"""
    name = "routing"

    def run(self, context: dict) -> dict:
        ticket = context.get("ticket", {})
        return {
            "title": "Team routing advisory",
            "assigned_team": ticket.get("assigned_team", "Unknown"),
            "recommended_team": "Storage",
            "mismatch": ticket.get("assigned_team") not in (None, "Storage"),
            "confidence": 0.89,
            "evidence": "2 highly-similar past tickets resolved by Storage.",
        }


class DiagnosisAgentStub:
    """Day 7 Diagnosis Agent placeholder: what is the root cause?"""
    name = "diagnosis"

    def run(self, context: dict) -> dict:
        return {
            "title": "Root-cause diagnosis",
            "root_cause": "Storage throttling under burst load",
            "evidence_summary": "p99 latency 1840ms, error_rate 7% in last hour.",
            "runbook_ref": "RB-STORAGE-014",
            "ttm_estimate_minutes": 95,
            "confidence": 0.82,
        }


class RecommendationAgentStub:
    """Day 8 Recommendation Agent placeholder: durable fix for a reactivation?"""
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
        "routing": RoutingAgentStub(),
        "diagnosis": DiagnosisAgentStub(),
        "recommendation": RecommendationAgentStub(),
    }
