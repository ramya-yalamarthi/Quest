"""
Sub-agents the supervisor dispatches to -- grounded in the REAL case + the
similar past cases (no hard-coded reference tickets). Each agent only needs
``run(context) -> dict``.

  * Routing        -> which support team/queue should handle this?
                      (+ whether the current assignment is correct, if any)
  * Diagnosis      -> root cause (the similar past incidents are attached by the
                      runner with clickable links + match %)
  * Recommendation -> Hot Fix + Ultimate Fix + matching public reference links
"""

from typing import Callable, Optional, Protocol

from app.orchestrator.llm import chat_json, llm_available
from app.orchestrator.trusted_sources import is_trusted


class Agent(Protocol):
    name: str
    def run(self, context: dict) -> dict: ...


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------
def _ticket_fields(context: dict):
    ticket = context.get("ticket", {}) or {}
    payload = (context.get("event", {}) or {}).get("payload", {}) or {}
    title = payload.get("title") or ticket.get("title") or ""
    desc = payload.get("description") or ticket.get("description") or ""
    assigned = payload.get("assigned_team") or ticket.get("assigned_team") or ""
    return title, desc, assigned


def _similar_cases(context: dict) -> list:
    """Real similar cases the runner attached to context (top level or payload)."""
    payload = (context.get("event", {}) or {}).get("payload", {}) or {}
    return context.get("similar") or payload.get("similar") or []


def _format_similar(similar: list, limit: int = 5) -> str:
    lines = []
    for s in similar[:limit]:
        num = s.get("ticket_number") or s.get("id") or "?"
        title = (s.get("title") or "").strip()
        body = (s.get("description") or s.get("resolution_text") or "").strip().replace("\n", " ")
        lines.append(f"- {num}: {title} :: {body[:200]}")
    return "\n".join(lines)


def _feedback_note(context: dict) -> str:
    """If the engineer marked the previous answer NOT helpful and left a comment,
    return a prompt suffix telling the agent to correct its answer accordingly."""
    fb = (context.get("feedback") or "").strip()
    if not fb:
        return ""
    return ("\n\nENGINEER FEEDBACK: the previous AI answer was marked NOT helpful. "
            "The engineer said:\n\"" + fb + "\"\n"
            "Produce a corrected, more accurate answer that directly addresses this "
            "feedback. Do not repeat the earlier answer verbatim.")


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# Routing Agent -- which team/queue should own this case?
# ---------------------------------------------------------------------------
_ROUTING_SYSTEM = (
    "You are a support TRIAGE assistant. Classify the case into EXACTLY ONE of these five "
    "categories, based ONLY on the case content -- choose the single best fit:\n"
    "- Software: applications, OS, Office/Outlook/Teams, licensing, updates, crashes, SaaS apps\n"
    "- Hardware: laptops, desktops, peripherals, printers, monitors, docking, physical devices\n"
    "- Network: connectivity, VPN, Wi-Fi, DNS, firewall, switches, ISP, routing, packet loss\n"
    "- Database: SQL/Dataverse data, queries, backups, replication, data loss, deadlocks, jobs\n"
    "- General: accounts/access, password/MFA/lockouts, onboarding/offboarding, email/DLs, "
    "phishing, purchase/access requests, and anything not clearly in the four above\n"
    "Use ONLY one of: Software, Hardware, Network, Database, General. "
    'Respond ONLY as JSON: {"recommended_team": "Network"}.'
)


class RoutingAgent:
    name = "routing"

    def run(self, context: dict) -> dict:
        title, desc, assigned = _ticket_fields(context)
        result = chat_json(_ROUTING_SYSTEM,
                           f"Case title: {title}\nDescription: {desc}" + _feedback_note(context))
        rec = str((result or {}).get("recommended_team", "")).strip() or "General"
        assigned_norm = (assigned or "").strip()
        correct = None
        if assigned_norm and assigned_norm.lower() not in ("unassigned", "unknown", ""):
            correct = assigned_norm.lower() == rec.lower()
        return {
            "assigned_team": assigned_norm or "Unassigned",
            "assignment_correct": correct,            # True / False / None (no team yet)
            "recommended_team": rec,
        }


# ---------------------------------------------------------------------------
# Diagnosis Agent -- root cause, grounded in the case + similar cases.
# ---------------------------------------------------------------------------
_DIAGNOSIS_SYSTEM = (
    "You are a support DIAGNOSIS assistant. Given a support case and a list of similar "
    "past cases, state the single most likely ROOT CAUSE in one crisp sentence, grounded "
    "ONLY in what the case and the cited similar cases actually say. Do NOT invent specifics "
    "(software versions, file types, dates, error codes, components) that are not present in "
    "the text. If the cause is not directly supported by the evidence, HEDGE: begin with "
    "'Likely' and end with 'confirm via <a quick check> before any disruptive action'. Set "
    '"grounded" false when the root cause relies on assumptions not stated in the case or the '
    "similar cases; true only when it is directly supported. No ticket numbers. "
    'Respond ONLY as JSON: {"root_cause": "<one sentence>", "grounded": true}.'
)


class DiagnosisAgent:
    name = "diagnosis"

    def run(self, context: dict) -> dict:
        title, desc, _ = _ticket_fields(context)
        similar = _similar_cases(context)
        user = f"Case title: {title}\nDescription: {desc}"
        if similar:
            user += "\n\nSIMILAR PAST CASES:\n" + _format_similar(similar)
        user += _feedback_note(context)
        result = chat_json(_DIAGNOSIS_SYSTEM, user)
        rc = str((result or {}).get("root_cause", "")).strip()
        grounded = bool((result or {}).get("grounded", True))
        return {"root_cause": rc or "Root cause could not be determined automatically.",
                "grounded": grounded}


# ---------------------------------------------------------------------------
# Recommendation Agent -- Hot Fix + Ultimate Fix + matching public links.
# ---------------------------------------------------------------------------
_RECOMMENDATION_SYSTEM = (
    "You are a support RESOLUTION assistant. Given a support case, its diagnosed root "
    "cause, and similar past cases, produce a concise resolution -- only what is actually "
    "needed, no filler.\n"
    "- HOT FIX: the fastest action to restore service now. If the root cause is UNCONFIRMED, "
    "make the FIRST step a quick confirmation, and flag any DISRUPTIVE action (rollback, "
    "reinstall, reboot, data change) as 'only after confirming <X>'. NEVER recommend a "
    "disruptive fix for an unconfirmed cause. If the fix ITSELF could destroy data (e.g. an "
    "in-place point-in-time restore that DISCARDS later writes), do NOT recommend it -- prefer "
    "the NON-DESTRUCTIVE recovery: restore to a SIDE copy, extract ONLY the affected records, "
    "and merge them back, stating the data-loss tradeoff explicitly. If a cited similar case "
    "describes a safe recovery method, FOLLOW it.\n"
    "- ULTIMATE FIX: the permanent fix; set requires_change_mgmt=true ONLY if it needs "
    "change control, with a short justification.\n"
    "- REFERENCE LINKS: at most 2 links, each an OFFICIAL PRODUCT-DOCUMENTATION page for the "
    "EXACT product, platform and error in THIS case. ONLY canonical docs (Microsoft Learn doc "
    "pages, PostgreSQL.org/docs, Cisco/Dell/HP/Adobe official support docs). DO NOT use Q&A, "
    "forum, community-answer ('Microsoft Q&A', Stack Overflow, Reddit), blog, or Tech Community "
    "pages. Match the platform precisely (no Office-for-Mac for a Windows issue) and the "
    "audience (end-user, not developer/add-in docs unless the case is about development). If "
    "there is NO official doc for the exact product/problem, return an EMPTY list -- NEVER "
    "substitute a loosely-related or wrong-product page. Real, specific, stable doc URLs only.\n"
    "- Keep every summary to ONE short, crisp sentence -- main pointer only, no filler.\n"
    "- Give a rough eta for each fix (hot fix in minutes, ultimate fix in hours).\n"
    'Respond ONLY as JSON: {"hot_fix": {"summary": "...", "steps": ["..."], "eta": "~20 min"}, '
    '"ultimate_fix": {"summary": "...", "steps": ["..."], "eta": "~4 hr", '
    '"requires_change_mgmt": false, "cm_justification": "..."}, '
    '"reference_links": [{"title": "...", "url": "...", "source": "..."}], "confidence": 0.0}.'
)


class RecommendationAgent:
    name = "recommendation"

    def __init__(
        self,
        prior_resolution_fetcher: Optional[Callable[[str], Optional[dict]]] = None,
        feedback_stats: Optional[Callable[[str], tuple]] = None,
    ) -> None:
        # Accepted for wiring compatibility (default_agents / router); the D365
        # resolution flow doesn't use them.
        self.prior_resolution_fetcher = prior_resolution_fetcher
        self.feedback_stats = feedback_stats

    def run(self, context: dict) -> dict:
        title, desc, _ = _ticket_fields(context)
        diagnosis = context.get("diagnosis") or {}
        similar = _similar_cases(context)
        user = (f"Case title: {title}\nDescription: {desc}\n"
                f"Diagnosed root cause: {diagnosis.get('root_cause', '') or 'unknown'}")
        if similar:
            user += "\n\nSIMILAR PAST CASES:\n" + _format_similar(similar)
        user += _feedback_note(context)

        result = chat_json(_RECOMMENDATION_SYSTEM, user, max_tokens=700)
        if not result or "hot_fix" not in result:
            return self._fallback()

        hot = result.get("hot_fix") or {}
        ult = result.get("ultimate_fix") or {}
        ult["requires_change_mgmt"] = bool(ult.get("requires_change_mgmt", False))
        # Option 1: LLM suggests links, we keep only trusted public domains.
        links = [l for l in (result.get("reference_links") or [])
                 if is_trusted(l.get("url", ""))]
        conf = _clamp(float(result.get("confidence", 0.6) or 0.6), 0.0, 1.0)
        return {"hot_fix": hot, "ultimate_fix": ult, "trusted_links": links, "confidence": conf}

    def _fallback(self) -> dict:
        """Deterministic resolution when the LLM is unavailable -- never crashes."""
        return {
            "hot_fix": {"summary": "Restore service from the last known-good state.",
                        "steps": ["Identify the failing component", "Restart or restore it",
                                  "Verify the service responds"]},
            "ultimate_fix": {"summary": "Address the underlying cause and add monitoring.",
                             "steps": ["Root-cause the failure", "Apply a durable fix",
                                       "Add an alert for early warning"],
                             "requires_change_mgmt": False, "cm_justification": ""},
            "trusted_links": [],
            "confidence": 0.4,
        }


def recommendation_to_resolution_payload(advisory: dict, ticket_id=None) -> dict:
    """Map a recommendation advisory -> POST /log-resolution fields (hot/ultimate
    fix serialized into recommendedsteps). Engineer-in-the-loop; no auto-insert."""
    recommendedsteps = [
        {"track": "hot_fix", **(advisory.get("hot_fix") or {})},
        {"track": "ultimate_fix", **(advisory.get("ultimate_fix") or {})},
    ]
    payload = {
        "resolution_text": (advisory.get("hot_fix") or {}).get("summary", ""),
        "confidence": advisory.get("confidence"),
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
        "routing": RoutingAgent(),
        "diagnosis": DiagnosisAgent(),
        "recommendation": RecommendationAgent(
            prior_resolution_fetcher=prior_resolution_fetcher,
            feedback_stats=feedback_stats,
        ),
    }


def routing_is_live() -> bool:
    return llm_available()
