"""MS-08, invariant 4: cannot leave Approved without a tested revert handle."""

import pytest

from app.mitigation_safety.domain.errors import (
    IllegalTransition,
    NotEligible,
    RevertHandleMissing,
)
from app.mitigation_safety.domain.transitions import assert_can_stage


class _FakeRegistry:
    def __init__(self, known: set[str]):
        self._known = known

    def has_tested(self, ref):
        return ref in self._known


def test_stage_blocked_without_handle_ref(make_action):
    action = make_action(revert_handle_ref=None)
    reg = _FakeRegistry({"rh-known"})
    with pytest.raises(RevertHandleMissing):
        assert_can_stage(action, reg)


def test_stage_blocked_with_unknown_handle(make_action):
    action = make_action(revert_handle_ref="rh-unknown")
    reg = _FakeRegistry({"rh-known"})
    with pytest.raises(RevertHandleMissing):
        assert_can_stage(action, reg)


def test_stage_blocked_when_not_eligible(make_action):
    action = make_action(eligible=False)
    reg = _FakeRegistry({"rh-quota-restart"})
    with pytest.raises(NotEligible):
        assert_can_stage(action, reg)


def test_stage_blocked_when_not_approved(make_action):
    action = make_action(state="DRAFTED")
    reg = _FakeRegistry({"rh-quota-restart"})
    with pytest.raises(IllegalTransition):
        assert_can_stage(action, reg)


def test_stage_passes_when_eligible_and_handle_tested(make_action):
    action = make_action()
    reg = _FakeRegistry({"rh-quota-restart"})
    # No raise.
    assert_can_stage(action, reg)
