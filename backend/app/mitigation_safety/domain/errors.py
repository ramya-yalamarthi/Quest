"""Typed errors raised by the domain + service layers.

These are mapped to HTTP status codes by the API layer:
  IllegalTransition / RevertHandleMissing / ScopeIsolationViolation / NotEligible
    / ValidationNotPassed                                                -> 409
  ConfirmRequired / SafeModeHeld                                         -> 423
  SafeModeHumanRequired                                                  -> 403
"""

from __future__ import annotations


class MitigationSafetyError(Exception):
    """Base class — never raised directly."""


class IllegalTransition(MitigationSafetyError):
    def __init__(self, frm, to):
        super().__init__(f"illegal transition {frm} -> {to}")
        self.frm = frm
        self.to = to


class NotEligible(MitigationSafetyError):
    """The upstream eligibility gate said `eligible=False` (MS-08 input)."""


class RevertHandleMissing(MitigationSafetyError):
    """No tested revert handle is registered (MS-08, invariant 4)."""

    def __init__(self, action_id, handle_ref: str | None = None):
        super().__init__(
            f"tested revert handle required for action {action_id} "
            f"(handle_ref={handle_ref!r})"
        )
        self.action_id = action_id
        self.handle_ref = handle_ref


class ScopeIsolationViolation(MitigationSafetyError):
    """Staging target resolves to a production scope (MS-11, invariant 7)."""


class ValidationNotPassed(MitigationSafetyError):
    """Promotion attempted when overall_status != PASS (invariant 1)."""

    def __init__(self, validation_id, overall_status: str):
        super().__init__(
            f"validation {validation_id} status={overall_status} (PASS required)"
        )
        self.validation_id = validation_id
        self.overall_status = overall_status


class ConfirmRequired(MitigationSafetyError):
    """Promotion requires explicit human confirm (MS-10 / Safe Mode hold)."""

    def __init__(self, reason: str = "confirm-to-promote required"):
        super().__init__(reason)


class SafeModeHeld(MitigationSafetyError):
    """A write is blocked because the relevant scope is in Safe Mode (MS-21)."""


class SafeModeHumanRequired(MitigationSafetyError):
    """Safe Mode exit attempted by a non-human actor (MS-22)."""
