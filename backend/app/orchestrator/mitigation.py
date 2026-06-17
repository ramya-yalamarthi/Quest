"""
Mitigation agent (Approach #2) -- the auto-remediation stage. This is the one
thing Copilot doesn't do: it EXECUTES a known fix, not just suggests one.

It runs AFTER Diagnosis as a new pipeline stage:

    match a runbook (signature) -> pass the safety gate -> execute -> verify
    -> (caller) resolve + close the Case

Only a small, fixed set of well-known problems have runbooks. A Case is
auto-remediated ONLY when it CLEARLY matches one of them AND clears the gate --
otherwise the pipeline falls back to suggest-only (the normal recommendation
note) and a human handles it. That gate is the honest answer to "isn't auto-
fixing dangerous?": it only acts when it has seen the pattern before, the fix is
deterministic, and the action is reversible.

Pure logic / network-free: the EXTERNAL runbook step is simulated here (clearly
labelled) behind a stable shape, so a real connector (Graph / SQL / Defender)
slots in for production. The one genuinely real action -- resolving the Case in
Dynamics -- is done by the caller (the poller) via DataverseClient.close_incident.
"""

from __future__ import annotations

# --- Safety gate thresholds --------------------------------------------------
# Auto-execute (Tier A) requires BOTH signals high -- not just their average --
# AND a reversible runbook. A novel incident with no close precedent drops below
# the gate and falls to suggest-only, exactly like Copilot.
CONF_MIN = 0.85       # blended confidence (model + precedent)
MATCH_MIN = 0.80      # calibrated relevance of the closest past case


# --- The runbook registry (the "recipe book") --------------------------------
# Each recipe: how to RECOGNISE it (signature keywords), the fixed STEPS, its
# safety TIER, and whether it is REVERSIBLE. Same workflow every time; only the
# target (which user / service / email) comes from the ticket.
RECIPES = [
    {
        "key": "account_lockout",
        "name": "Account Lockout",
        "tier": "A",
        "reversible": True,
        # signature: any of these phrases in the case text
        "signals": ["locked out", "lockout", "account locked", "account is locked",
                    "password reset", "can't sign in", "cannot sign in", "can't log in",
                    "mfa", "multi-factor", "unlock"],
        "steps": ["Unlock the account",
                  "Re-trigger MFA registration",
                  "Verify sign-in succeeds"],
        "verify": "Sign-in health check passed",
    },
    {
        "key": "hung_service",
        "name": "Hung Service Restart",
        "tier": "A",
        "reversible": True,
        "signals": ["license server", "licence server", "lmgrd", "flexnet", "port 27000",
                    "won't start", "wont start", "refusing to start", "unreachable",
                    "dns resolution", "dns server", "resolution slow", "service hung",
                    "service stuck", "service unresponsive", "timing out"],
        "steps": ["Restart the affected service (not the host)",
                  "Wait for warm-up",
                  "Re-test reachability / response time"],
        "verify": "Service responds; reachability restored",
    },
    {
        "key": "phishing_containment",
        "name": "Phishing Containment",
        "tier": "A",
        "reversible": True,
        "signals": ["phishing", "phish", "credential harvest", "credential-harvest",
                    "spoof", "malicious email", "malicious link", "reported email",
                    "impersonating"],
        "steps": ["Purge the message tenant-wide",
                  "Block the sender + URL",
                  "Force password reset for confirmed clickers",
                  "Compile the exposure report onto the case"],
        "verify": "Campaign purged; sender/URL blocked",
    },
]

_RECIPE_BY_KEY = {r["key"]: r for r in RECIPES}


def _case_text(case: dict) -> str:
    return f"{case.get('title', '')} {case.get('description', '')}".lower()


def match_recipe(case: dict) -> dict | None:
    """Return the first runbook whose signature appears in the case text, else
    None. Deterministic keyword match -- a clear, explainable rule."""
    text = _case_text(case)
    for r in RECIPES:
        if any(sig in text for sig in r["signals"]):
            return r
    return None


def execution_trace(recipe: dict) -> list[str]:
    """The simulated execution result -- each fixed step marked done. In
    production the executor calls the real system (Graph / SQL / Defender); here
    the step is simulated so the demo runs without those connectors."""
    return [f"{step} ✓" for step in recipe["steps"]]


def assess(case: dict, similar: list, confidence: float) -> dict:
    """Decide whether this Case can be auto-remediated.

    Returns a mitigation dict the runner attaches to the advisory. `gate_passed`
    True means: a runbook matched, the closest precedent is strong, confidence is
    high, the tier is auto, and the fix is reversible -> safe to execute + close.
    """
    recipe = match_recipe(case)
    top = (similar[0] if similar else {}) or {}
    top_match = float(top.get("display_score") or 0.0)

    if not recipe:
        return {"matched": False, "gate_passed": False,
                "gate_reason": "no runbook matches this case (suggest-only)"}

    reasons = []
    if confidence < CONF_MIN:
        reasons.append(f"confidence {confidence:.0%} < {CONF_MIN:.0%}")
    if top_match < MATCH_MIN:
        reasons.append(f"precedent match {top_match:.0%} < {MATCH_MIN:.0%} (novel)")
    if recipe["tier"] != "A":
        reasons.append(f"tier {recipe['tier']} needs human approval")
    if not recipe["reversible"]:
        reasons.append("runbook is not reversible")
    gate_passed = not reasons

    return {
        "matched": True,
        "recipe_key": recipe["key"],
        "recipe_name": recipe["name"],
        "tier": recipe["tier"],
        "reversible": recipe["reversible"],
        "recipe_match": 1.0,                       # signature match is categorical
        "confidence": round(confidence, 2),
        "precedent_ticket": top.get("ticket_number"),
        "precedent_match": round(top_match, 2),
        "steps": recipe["steps"],
        "executed": execution_trace(recipe) if gate_passed else [],
        "verify": recipe["verify"],
        "gate_passed": gate_passed,
        "gate_reason": "all checks passed" if gate_passed else "; ".join(reasons),
        "resolution_text": _resolution_text(recipe, confidence, top),
    }


def _resolution_text(recipe: dict, confidence: float, top: dict) -> str:
    """Plain-text summary written into the D365 incident resolution on close."""
    steps = " -> ".join(recipe["steps"])
    prec = top.get("ticket_number")
    prec_s = f" (precedent {prec})" if prec else ""
    return (f"Auto-remediated by AI agent via the {recipe['name']} runbook"
            f"{prec_s}, confidence {confidence:.0%}. Executed: {steps}. "
            f"Verified: {recipe['verify']}.")
