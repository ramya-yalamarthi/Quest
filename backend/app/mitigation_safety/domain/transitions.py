"""Transition guards (MS-05, MS-08, invariants 1, 2, 4).

`assert_legal` is the single chokepoint every state write must pass through.
`assert_can_stage` and `assert_can_promote` layer the additional guards the
SRS requires (eligibility, tested revert handle, validation PASS, Safe Mode,
confirm-to-promote).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from app.mitigation_safety.domain.errors import (
    ConfirmRequired,
    IllegalTransition,
    NotEligible,
    RevertHandleMissing,
    SafeModeHeld,
    ValidationNotPassed,
)
from app.mitigation_safety.domain.states import (
    LEGAL_TRANSITIONS,
    MitigationState,
)


# --- Protocols (pure, no DB) -------------------------------------------------

class _Action(Protocol):
    """The slice of `BotActionLog` the transition guards read."""

    action_id: object
    state: str
    eligible: bool
    revert_handle_ref: str | None
    category: str


class _RevertRegistry(Protocol):
    def has_tested(self, handle_ref: str | None) -> bool: ...


# --- Guards ------------------------------------------------------------------

def assert_legal(frm: MitigationState | str, to: MitigationState | str) -> None:
    """Reject illegal transitions (MS-05)."""
    frm_e = MitigationState(frm) if isinstance(frm, str) else frm
    to_e = MitigationState(to) if isinstance(to, str) else to
    if to_e not in LEGAL_TRANSITIONS.get(frm_e, frozenset()):
        raise IllegalTransition(frm_e.value, to_e.value)


def assert_can_stage(action: _Action, registry: _RevertRegistry) -> None:
    """MS-08 + invariant 4: Approved + eligible + tested revert handle.

    Called from StagingService.stage() before any DB write.
    """
    # The base legal-transitions check is run by the caller; we add domain
    # preconditions on top.
    if action.state != MitigationState.APPROVED.value:
        raise IllegalTransition(action.state, MitigationState.STAGED.value)
    if not action.eligible:
        raise NotEligible(
            f"action {action.action_id} did not clear the upstream eligibility gate"
        )
    if not registry.has_tested(action.revert_handle_ref):
        raise RevertHandleMissing(action.action_id, action.revert_handle_ref)


def assert_can_promote(
    *,
    overall_status: str,
    safe_mode_active: bool,
    confirm_to_promote: bool,
    confirm: bool,
) -> None:
    """MS-02, MS-10, MS-21, invariant 1.

    Caller passes:
      overall_status        — current validation status
      safe_mode_active      — True iff Safe Mode is active for this category
      confirm_to_promote    — config flag for the category
      confirm               — request body field
    """
    if overall_status != "PASS":
        raise ValidationNotPassed(validation_id=None, overall_status=overall_status)
    if (safe_mode_active or confirm_to_promote) and not confirm:
        if safe_mode_active:
            raise SafeModeHeld(
                "Safe Mode is active for this category; explicit human "
                "confirm required to promote"
            )
        raise ConfirmRequired()


# --- State-history helper ----------------------------------------------------

def record_transition(
    history: list[dict] | None,
    *,
    frm: str,
    to: str,
    actor: str,
    detail: str | None = None,
) -> list[dict]:
    """Append one transition entry to a state_history JSONB list.

    Returns the (new) list — does not mutate the input. Each entry carries the
    actor (`human:<id>` or `guard:<signal>`) and a UTC timestamp, satisfying
    MS-01 / MS-24 traceability.
    """
    out = list(history or [])
    out.append(
        {
            "from": frm,
            "to": to,
            "actor": actor,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "detail": detail,
        }
    )
    return out
