"""
Sub-agents the supervisor dispatches to.

RoutingAgent and DiagnosisAgent are REAL (gpt-4o), grounded ONLY in a fixed set
of reference tickets. RecommendationAgent is still a stub. Each agent only needs
``run(context) -> dict``; the supervisor is unchanged.

  * Routing   -> is the assigned team correct? (minimal: team + confidence)
  * Diagnosis -> why / root cause + which reference ticket (+ link)
"""

import os
from typing import Callable, Optional, Protocol

from app.orchestrator.llm import chat_json, llm_available
from app.orchestrator.prevention import (
    ROOT_CAUSE_KEYS,
    get_prevention,
    normalize_root_cause_type,
    requires_change_mgmt,
)
from app.orchestrator.trusted_sources import is_trusted


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
    '\n\nRespond ONLY as a JSON object with key: '
    '"recommended_team" (team of the best-matching reference ticket).'
)


class RoutingAgent:
    name = "routing"

    def run(self, context: dict) -> dict:
        title, desc, assigned = _ticket_fields(context)
        result = chat_json(_ROUTING_SYSTEM, f"NEW ticket title: {title}\nDescription: {desc}")
        if not result or "recommended_team" not in result:
            return {"assigned_team": assigned, "assignment_correct": None,
                    "recommended_team": "Unknown"}
        rec = str(result.get("recommended_team", "Unknown")).strip()
        return {
            "assigned_team": assigned,
            "assignment_correct": assigned.strip().lower() == rec.lower(),
            "recommended_team": rec,
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
# Recommendation Agent (UC3 reactivation) -- REAL.  WBS tasks R-03..R-06.
#
# Given a REOPENED ticket, it: (1) computes the delta against the PREVIOUS
# resolution (why the last fix didn't hold), (2) produces a two-track
# recommendation -- immediate (20-30 min) + durable (4-6 hr) with a Change
# Management flag, (3) classifies the root cause into one of 12 keys and attaches
# the deterministic prevention from PREVENTION_LIBRARY, (4) returns one flat
# advisory dict (logged to ai_audit_log by the orchestrator).
#
# Grounded ONLY in the reference tickets + new ticket + optional diagnosis output
# + the prior resolution.  The LLM never emits URLs; all links are attached in
# code from the library and the ServiceNow reference link.
# ---------------------------------------------------------------------------
_RECOMMENDATION_SYSTEM = (
    "You are an IT support RECOMMENDATION assistant handling a REACTIVATED (reopened) "
    "ticket. The ticket was closed before but the problem came back. Using ONLY the "
    "reference tickets below, the new ticket, any diagnosis notes, and the PRIOR "
    "RESOLUTION provided, produce a two-track recommendation and explain why the last "
    "fix did not hold.\n\nREFERENCE TICKETS:\n" + _REF_BLOCK +
    "\n\nClassify the root cause into EXACTLY ONE of these root_cause_type keys:\n" +
    ", ".join(ROOT_CAUSE_KEYS) +
    "\n\nRules:\n"
    "- The IMMEDIATE action restores service fast (target 20-30 minutes).\n"
    "- The DURABLE fix is the permanent fix (target 4-6 hours).\n"
    "- Explain prior_fix_gap EXPLICITLY: what gap in the previous fix let the issue recur. "
    "If no prior resolution is provided, say so plainly.\n"
    "- Do NOT output any URLs or links anywhere; links are added separately.\n"
    "- Never invent ticket numbers; reference must be one of the reference tickets.\n"
    '\nRespond ONLY as a JSON object with EXACTLY these keys: '
    '"reference" (matched reference ticket number, e.g. INC0010724), '
    '"root_cause" (one short sentence), '
    '"root_cause_type" (one of the keys above), '
    '"delta" (object: "what_changed","prior_fix_summary","prior_fix_gap",'
    '"original_fix_held" (boolean),"recurrence_pattern","delta_severity" ("low"|"medium"|"high")), '
    '"immediate_action" (object: "summary","steps" (array of strings),"eta_minutes" (number)), '
    '"durable_fix" (object: "summary","steps" (array of strings),"eta_hours" (number),'
    '"requires_change_mgmt" (boolean),"cm_justification"), '
    '"reasoning" (one short sentence, no ticket numbers), '
    '"confidence" (number between 0 and 1).'
)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _prior_resolution_summary(prior: Optional[dict]) -> str:
    if not prior:
        return "No prior resolution on record for this ticket."
    text = (prior.get("resolution_text") or "").strip()
    rc = (prior.get("root_cause") or "").strip()
    parts = []
    if rc:
        parts.append(f"prior root cause: {rc}")
    if text:
        parts.append(f"prior resolution: {text}")
    return "; ".join(parts) or "Prior resolution exists but had no text."


class RecommendationAgent:
    name = "recommendation"

    def __init__(
        self,
        prior_resolution_fetcher: Optional[Callable[[str], Optional[dict]]] = None,
        feedback_stats: Optional[Callable[[str], tuple]] = None,
    ) -> None:
        # Both optional and DB-free by default so the demo/tests never touch a DB.
        # The live app injects DB-backed callables where default_agents() is composed.
        self.prior_resolution_fetcher = prior_resolution_fetcher
        self.feedback_stats = feedback_stats

    # -- helpers ----------------------------------------------------------
    def _ticket_id(self, context: dict) -> Optional[str]:
        payload = (context.get("event", {}) or {}).get("payload", {}) or {}
        return payload.get("ticket_id") or (context.get("ticket", {}) or {}).get("ticket_id")

    def _load_prior(self, context: dict) -> Optional[dict]:
        # Prefer a prior resolution already on the context; otherwise use the
        # injected fetcher (kept off the orchestrator per the DB-free design).
        prior = context.get("prior_resolution")
        if prior is not None:
            return prior
        if self.prior_resolution_fetcher is not None:
            tid = self._ticket_id(context)
            if tid:
                try:
                    return self.prior_resolution_fetcher(tid)
                except Exception:
                    return None
        return None

    def _adjust_confidence(self, base: float, root_cause_type: str) -> float:
        if self.feedback_stats is None:
            return base
        try:
            likes, dislikes = self.feedback_stats(root_cause_type)
        except Exception:
            return base
        total = (likes or 0) + (dislikes or 0)
        if total < 3:
            return base
        return _clamp(base * (0.8 + 0.4 * (likes / total)), 0.0, 1.0)

    def _fallback(self, context: dict, prior: Optional[dict]) -> dict:
        """Deterministic advisory when the LLM is unavailable -- never crashes."""
        rct = "config_drift"
        entry = get_prevention(rct)
        gap = ("Previous fix addressed symptoms but not the underlying configuration drift, "
               "so the issue recurred.") if prior else "No prior resolution on record; treating as first recurrence."
        immediate = {"summary": "Restore service using the last known-good configuration.",
                     "steps": ["Re-apply the baseline configuration", "Confirm the service responds"],
                     "eta_minutes": 25}
        durable = {"summary": "Enforce desired-state configuration to stop drift recurring.",
                   "steps": ["Apply DSC/baseline policy", "Add drift monitoring"],
                   "eta_hours": 5, "requires_change_mgmt": requires_change_mgmt(rct),
                   "cm_justification": "Configuration policy change requires change control."}
        delta = {"what_changed": "Unknown (LLM not configured).",
                 "prior_fix_summary": _prior_resolution_summary(prior),
                 "prior_fix_gap": gap, "original_fix_held": False,
                 "recurrence_pattern": "unknown", "delta_severity": "medium"}
        return self._assemble(
            reference="", root_cause="LLM not configured; deterministic fallback.",
            root_cause_type=rct, delta=delta, immediate=immediate, durable=durable,
            prevention_entry=entry, reasoning="LLM not configured.", base_confidence=0.4,
        )

    def _assemble(self, *, reference, root_cause, root_cause_type, delta, immediate,
                  durable, prevention_entry, reasoning, base_confidence) -> dict:
        rct = normalize_root_cause_type(root_cause_type)
        # Deterministic CM backstop for high-impact root-cause types.
        if requires_change_mgmt(rct):
            durable["requires_change_mgmt"] = True
            if not durable.get("cm_justification"):
                durable["cm_justification"] = f"Change Management required for {rct}."
        else:
            durable["requires_change_mgmt"] = bool(durable.get("requires_change_mgmt", False))

        trusted_links = [l for l in prevention_entry.get("trusted_links", []) if is_trusted(l.get("url", ""))]
        prevention = {
            "root_cause_type": rct,
            "actions": list(prevention_entry.get("prevention_actions", [])),
            "monitoring_rule": prevention_entry.get("monitoring_rule", ""),
        }
        confidence = self._adjust_confidence(_clamp(float(base_confidence), 0.0, 1.0), rct)

        resolution_text = (
            f"Why it recurred: {delta.get('prior_fix_gap', '')}\n"
            f"Immediate (~{immediate.get('eta_minutes', '?')} min): {immediate.get('summary', '')}\n"
            f"Durable (~{durable.get('eta_hours', '?')} hr): {durable.get('summary', '')}"
            f"{' [Change Management required]' if durable.get('requires_change_mgmt') else ''}\n"
            f"Prevention: {prevention['monitoring_rule']}"
        )
        outcome = [{
            "reference": reference,
            "immediate": immediate.get("summary", ""),
            "durable": durable.get("summary", ""),
            "result": "pending",
        }]
        return {
            "title": "Two-track recommendation",
            "delta": delta,
            "immediate_action": immediate,
            "durable_fix": durable,
            "prevention": prevention,
            "trusted_links": trusted_links,
            "reference": reference,
            "reference_link": _ref_link(reference),
            "resolution_text": resolution_text,
            "root_cause": root_cause,
            "outcome": outcome,
            "reasoning": reasoning,
            "confidence": confidence,
        }

    # -- entry point ------------------------------------------------------
    def run(self, context: dict) -> dict:
        title, desc, _ = _ticket_fields(context)
        prior = self._load_prior(context)
        diagnosis = context.get("diagnosis") or {}

        user = (
            f"NEW ticket title: {title}\nDescription: {desc}\n"
            f"Diagnosis notes: {diagnosis.get('root_cause', '') or 'none'}\n"
            f"PRIOR RESOLUTION: {_prior_resolution_summary(prior)}"
        )
        result = chat_json(_RECOMMENDATION_SYSTEM, user, max_tokens=700)
        if not result or "immediate_action" not in result or "durable_fix" not in result:
            return self._fallback(context, prior)

        delta = result.get("delta") or {}
        if not prior and not delta.get("prior_fix_gap"):
            delta.setdefault("prior_fix_summary", _prior_resolution_summary(prior))
            delta["prior_fix_gap"] = "No prior resolution on record; treating as first recurrence."
            delta.setdefault("original_fix_held", False)
        rct = normalize_root_cause_type(result.get("root_cause_type"))
        return self._assemble(
            reference=str(result.get("reference", "")).strip(),
            root_cause=result.get("root_cause", ""),
            root_cause_type=rct,
            delta=delta,
            immediate=result.get("immediate_action") or {},
            durable=result.get("durable_fix") or {},
            prevention_entry=get_prevention(rct),
            reasoning=result.get("reasoning", ""),
            base_confidence=result.get("confidence", 0.6),
        )


def recommendation_to_resolution_payload(advisory: dict, ticket_id=None) -> dict:
    """Map a recommendation advisory dict -> POST /log-resolution fields, so the
    frontend/MCP can persist it in one call on engineer ACCEPT (WBS R-06).

    The two tracks + prevention are serialized into ``recommendedsteps``; the
    agent itself never writes to the DB (engineer-in-the-loop).
    """
    recommendedsteps = [
        {"track": "immediate", **(advisory.get("immediate_action") or {})},
        {"track": "durable", **(advisory.get("durable_fix") or {})},
        {"track": "prevention", **(advisory.get("prevention") or {})},
    ]
    payload = {
        "resolution_text": advisory.get("resolution_text", ""),
        "root_cause": advisory.get("root_cause", ""),
        "outcome": advisory.get("outcome"),
        "confidence": advisory.get("confidence"),
        "reasoning": advisory.get("reasoning", ""),
        "recommendedsteps": recommendedsteps,
    }
    if ticket_id is not None:
        payload["ticket_id"] = ticket_id
    return payload


def default_agents(
    prior_resolution_fetcher: Optional[Callable[[str], Optional[dict]]] = None,
    feedback_stats: Optional[Callable[[str], tuple]] = None,
) -> dict[str, Agent]:
    return {
        "routing": RoutingAgent(),          # REAL (gpt-4o)
        "diagnosis": DiagnosisAgent(),      # REAL (gpt-4o)
        "recommendation": RecommendationAgent(  # REAL (gpt-4o), UC3
            prior_resolution_fetcher=prior_resolution_fetcher,
            feedback_stats=feedback_stats,
        ),
    }


def routing_is_live() -> bool:
    return llm_available()
