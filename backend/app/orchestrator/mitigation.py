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

import os

from app.orchestrator.appconfig import load_json, env_float

# --- Safety gate thresholds (externalised; override via env) -----------------
# Auto-execute (Tier A) requires BOTH signals high -- not just their average --
# AND a reversible runbook. A novel incident with no close precedent drops below
# the gate and falls to suggest-only, exactly like Copilot.
CONF_MIN = env_float("MITIGATION_CONF_MIN", 0.85)    # blended confidence
MATCH_MIN = env_float("MITIGATION_MATCH_MIN", 0.80)  # calibrated precedent match


# --- The runbook registry (the "recipe book") --------------------------------
# Loaded from backend/config/runbooks.json so support can add/edit runbooks
# WITHOUT a code change; the in-code list below is the fallback default.
# Each recipe: how to RECOGNISE it (signature keywords), the fixed STEPS, its
# safety TIER, and whether it is REVERSIBLE.
_DEFAULT_RECIPES = [
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
        "revert_steps": ["Re-lock the account to its prior state",
                         "Cancel the MFA re-registration"],
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
        "revert_steps": ["Stop the restarted service",
                         "Restore the previous service state / failover"],
    },
]

# Config file overrides the defaults (falls back to _DEFAULT_RECIPES if missing).
RECIPES = load_json("runbooks.json", _DEFAULT_RECIPES)

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
    """The runbook's steps. NOT marked done -- the external actions are not
    executed in this POC (a real Graph/SQL/Defender connector runs them in
    production), so we never show a misleading 'completed' tick."""
    return list(recipe["steps"])


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
    return (f"Auto-resolved by AI agent via the {recipe['name']} runbook"
            f"{prec_s}, confidence {confidence:.0%}. Runbook: {steps}. "
            "(External remediation steps run via a connector in production; "
            "the Dynamics resolve/close is live.)")


# --- Safety net on the AUTO path: verify -> revert -> kill switch -------------
# Even a gated auto-fix can be wrong, so we apply -> verify -> revert-on-failure
# (each runbook carries a revert handle) and trip a kill switch after repeated
# failures. Lightweight for this DB-free / D365 flow: no validation window, no
# Postgres -- the audit is the D365 case note, the kill switch is in-memory
# (see auto_safety.py).

def verify_runbook(recipe: dict, case: dict) -> bool:
    """Did the auto-fix actually work? POC: verify PASSES (a real connector runs
    the check in production). Two demo triggers force a FAILURE so the revert /
    escalate / kill-switch path can be shown on command:
      * the case text contains '[demo-fail]'
      * env MITIGATION_FORCE_VERIFY_FAIL=1
    """
    if "[demo-fail]" in _case_text(case):
        return False
    if os.getenv("MITIGATION_FORCE_VERIFY_FAIL", "0") == "1":
        return False
    return True


def revert_trace(recipe: dict) -> list[str]:
    """The runbook's undo steps (simulated, like the forward steps)."""
    return list(recipe.get("revert_steps") or ["Restore the prior state"])


def finalize_mitigation(mit: dict, case: dict) -> dict:
    """Wrap the AUTO path in a safety net: check the kill switch, then apply ->
    verify -> (revert on failure). Adds outcome fields that the note and the
    caller read; never raises; leaves suggest-only cases untouched.

    auto_outcome is one of:
      suggest_only        gate failed (no runbook / low conf) -> human, as before
      auto_off            gate passed but auto mode is OFF (kill switch) -> human
      auto_resolved       applied + verified -> caller closes the Case
      reverted_escalated  applied, verify FAILED, change reverted -> human

    should_close is True ONLY for auto_resolved.
    """
    if not mit.get("gate_passed"):
        mit["auto_outcome"] = "suggest_only"
        mit["should_close"] = False
        return mit

    from app.orchestrator import auto_safety   # lazy import (avoids import cycle)
    if not auto_safety.is_enabled():
        mit["auto_enabled"] = False
        mit["auto_outcome"] = "auto_off"
        mit["should_close"] = False
        return mit

    mit["auto_enabled"] = True
    recipe = _RECIPE_BY_KEY.get(mit.get("recipe_key"), {})
    if verify_runbook(recipe, case):
        mit["verify_passed"] = True
        mit["auto_outcome"] = "auto_resolved"
        mit["should_close"] = True
    else:
        mit["verify_passed"] = False
        mit["reverted"] = True
        mit["revert_executed"] = revert_trace(recipe)
        mit["auto_outcome"] = "reverted_escalated"
        mit["should_close"] = False
        auto_safety.record_failure(case.get("id"))
    return mit
