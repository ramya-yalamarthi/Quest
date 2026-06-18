"""MS-05: illegal transitions are rejected at the domain layer."""

import pytest

from app.mitigation_safety.domain.errors import IllegalTransition
from app.mitigation_safety.domain.states import (
    LEGAL_TRANSITIONS,
    MitigationState,
    is_terminal,
)
from app.mitigation_safety.domain.transitions import assert_legal


def test_legal_transitions_round_trip_via_assert_legal():
    for frm, allowed in LEGAL_TRANSITIONS.items():
        for to in allowed:
            assert_legal(frm, to)  # no raise


def test_terminals_have_no_outgoing_edges():
    for term in (
        MitigationState.REJECTED,
        MitigationState.REVERTED,
        MitigationState.ROLLEDBACK,
        MitigationState.CLOSED,
    ):
        assert LEGAL_TRANSITIONS[term] == frozenset()
        assert is_terminal(term)


def test_drafted_cannot_jump_to_promoted():
    with pytest.raises(IllegalTransition):
        assert_legal(MitigationState.DRAFTED, MitigationState.PROMOTED)


def test_validating_cannot_skip_to_rolledback():
    with pytest.raises(IllegalTransition):
        assert_legal(MitigationState.VALIDATING, MitigationState.ROLLEDBACK)


def test_failed_cannot_return_to_validating():
    with pytest.raises(IllegalTransition):
        assert_legal(MitigationState.FAILED, MitigationState.VALIDATING)


def test_promoted_can_close_or_rollback_only():
    legal = LEGAL_TRANSITIONS[MitigationState.PROMOTED]
    assert legal == frozenset(
        {MitigationState.ROLLEDBACK, MitigationState.CLOSED}
    )


def test_string_inputs_accepted():
    assert_legal("APPROVED", "STAGED")
    with pytest.raises(IllegalTransition):
        assert_legal("APPROVED", "PROMOTED")
