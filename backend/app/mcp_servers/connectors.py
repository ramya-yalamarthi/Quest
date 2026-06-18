"""
Phase 3 — remediation connectors (governed, least-privilege, pluggable).

Each runbook ACTION maps to a connector that, in production, calls the real
system (Microsoft Graph / SQL / Microsoft Defender). Today every connector is
SIMULATED. Making it real = registering a real implementation here; nothing else
in the agent changes.

Two governance properties are built in:
  * LEAST PRIVILEGE — each connector declares the MINIMAL permission it needs
    (not blanket admin), and every call records the scope it used.
  * APPROVAL TIERS  — Tier A auto-executes (reversible/low-risk); Tier B prepares
    the actions and waits for one-click human approval; Tier C is human-only.

This is the seam where, together, you wire the real connectors when Microsoft
grants the scoped (least-privilege) access.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Connector:
    action: str
    scope: str               # least-privilege permission this action requires
    impl: Callable[[dict], str]
    simulated: bool = True


_REGISTRY: dict[str, Connector] = {}


def register(action: str, scope: str, impl: Callable[[dict], str], simulated: bool = True) -> None:
    _REGISTRY[action] = Connector(action, scope, impl, simulated)


def execute(action: str, params: dict | None = None) -> dict:
    """Run one action through its connector. Returns an audit record."""
    c = _REGISTRY.get(action)
    if not c:
        return {"action": action, "status": "no_connector"}
    detail = c.impl(params or {})
    return {"action": action, "status": "ok", "scope": c.scope,
            "simulated": c.simulated, "detail": detail}


# --- simulated implementations (swap for real Graph / SQL / Defender calls) ---
def _sim(label: str) -> Callable[[dict], str]:
    return lambda params: f"[simulated] {label}"


# action  ->  (least-privilege scope, simulated implementation)
register("unlock_account",  "User-Account.Unlock (single user, unlock only)", _sim("unlocked the account"))
register("reset_mfa",       "UserAuthMethod.ReadWrite (target user only)",    _sim("re-triggered MFA registration"))
register("restart_service", "Service.Restart (named service, scoped host)",   _sim("restarted the service"))
register("purge_message",   "ThreatHunting.Purge (Defender, this campaign)",  _sim("purged the message tenant-wide"))
register("block_sender",    "ThreatPolicy.Block (sender + URL)",              _sim("blocked the sender and URL"))
register("verify_health",   "(read-only health probe)",                       _sim("health check passed"))


# Which connector actions each runbook performs (maps the human steps to actions).
RUNBOOK_ACTIONS = {
    "account_lockout": ["unlock_account", "reset_mfa", "verify_health"],
    "hung_service":    ["restart_service", "verify_health"],
}


def execute_runbook(key: str, tier: str = "A") -> dict:
    """Governed execution. Tier A auto-executes via the connectors; Tier B
    prepares the actions and requires human approval; Tier C is human-only.
    Returns the audit trail (each action + the scope it used)."""
    actions = RUNBOOK_ACTIONS.get(key)
    if not actions:
        return {"status": "no_runbook", "key": key}
    if tier == "C":
        return {"status": "human_only", "key": key, "actions": actions}
    if tier == "B":
        return {"status": "requires_approval", "key": key,
                "prepared": [{"action": a, "scope": _REGISTRY[a].scope} for a in actions]}
    # Tier A -> auto-execute
    audit = [execute(a) for a in actions]
    return {"status": "executed", "key": key, "tier": "A", "audit": audit,
            "note": "external actions simulated; register real connectors to go live"}
