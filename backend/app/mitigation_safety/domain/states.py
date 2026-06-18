"""Mitigation Action state machine (MS-01, MS-05).

Promoted is reachable only through Staged -> Validating. The transitions
table below is the single source of truth; the service layer must consult
`LEGAL_TRANSITIONS` via `assert_legal` before any state write.
"""

from __future__ import annotations

from enum import Enum


class MitigationState(str, Enum):
    DRAFTED = "DRAFTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    STAGED = "STAGED"
    VALIDATING = "VALIDATING"
    PROMOTED = "PROMOTED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    REVERTED = "REVERTED"
    ROLLEDBACK = "ROLLEDBACK"
    CLOSED = "CLOSED"


TERMINAL_STATES = frozenset(
    {
        MitigationState.REJECTED,
        MitigationState.REVERTED,
        MitigationState.ROLLEDBACK,
        MitigationState.CLOSED,
    }
)


# Legal transitions per the SRS state machine. The service layer guards
# additional conditions (revert handle, eligibility, Safe Mode hold,
# confirm-to-promote) on top of these.
LEGAL_TRANSITIONS: dict[MitigationState, frozenset[MitigationState]] = {
    MitigationState.DRAFTED: frozenset(
        {MitigationState.APPROVED, MitigationState.REJECTED}
    ),
    MitigationState.APPROVED: frozenset({MitigationState.STAGED}),
    MitigationState.STAGED: frozenset(
        {MitigationState.VALIDATING, MitigationState.REVERTED}
    ),
    MitigationState.VALIDATING: frozenset(
        {
            MitigationState.PROMOTED,
            MitigationState.FAILED,
            MitigationState.EXPIRED,
        }
    ),
    MitigationState.FAILED: frozenset({MitigationState.REVERTED}),
    MitigationState.EXPIRED: frozenset({MitigationState.REVERTED}),
    MitigationState.PROMOTED: frozenset(
        {MitigationState.ROLLEDBACK, MitigationState.CLOSED}
    ),
    # Terminal states have no outgoing edges.
    MitigationState.REJECTED: frozenset(),
    MitigationState.REVERTED: frozenset(),
    MitigationState.ROLLEDBACK: frozenset(),
    MitigationState.CLOSED: frozenset(),
}


def is_terminal(state: MitigationState | str) -> bool:
    if isinstance(state, str):
        state = MitigationState(state)
    return state in TERMINAL_STATES
