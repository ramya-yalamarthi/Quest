"""Promote on a non-PASS validation must raise ValidationNotPassed (409)."""

import pytest

from app.mitigation_safety.db.models import ValidationResult
from app.mitigation_safety.domain.errors import ValidationNotPassed


def test_promote_blocked_when_pending(service_bundle, make_action):
    s = service_bundle
    action = make_action(state="APPROVED")
    s["mock_ci"].set_default("success")
    result = s["staging"].stage(
        action_id=action.action_id,
        type="code",
        target="sentinel/x",
        artifacts_ref="diff",
        expected_outcome={"component": "x"},
        revert_handle_ref="rh-code-revert",
        actor="human:42",
    )
    s["db"].commit()
    # Don't evaluate — leave PENDING.
    with pytest.raises(ValidationNotPassed):
        s["promotion"].promote(
            action_id=action.action_id, confirm=True, actor="human:42"
        )
