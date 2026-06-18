"""Pure domain layer: state machine + transition guards.

No DB access, no IO. Importable from anywhere without side effects."""

from app.mitigation_safety.domain.errors import (
    ConfirmRequired,
    IllegalTransition,
    NotEligible,
    RevertHandleMissing,
    SafeModeHeld,
    SafeModeHumanRequired,
    ScopeIsolationViolation,
    ValidationNotPassed,
)
from app.mitigation_safety.domain.states import (
    LEGAL_TRANSITIONS,
    TERMINAL_STATES,
    MitigationState,
)
from app.mitigation_safety.domain.transitions import (
    assert_can_promote,
    assert_can_stage,
    assert_legal,
    record_transition,
)

__all__ = [
    "ConfirmRequired",
    "IllegalTransition",
    "LEGAL_TRANSITIONS",
    "MitigationState",
    "NotEligible",
    "RevertHandleMissing",
    "SafeModeHeld",
    "SafeModeHumanRequired",
    "ScopeIsolationViolation",
    "TERMINAL_STATES",
    "ValidationNotPassed",
    "assert_can_promote",
    "assert_can_stage",
    "assert_legal",
    "record_transition",
]
