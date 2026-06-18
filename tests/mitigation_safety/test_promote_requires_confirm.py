"""Promote requires `confirm=true` when `confirm_to_promote[category]` is True."""

import pytest

from app.mitigation_safety.config import default_store
from app.mitigation_safety.domain.errors import ConfirmRequired


def test_promote_without_confirm_raises(service_bundle, make_action):
    s = service_bundle
    action = make_action(state="APPROVED")
    # Force confirm-to-promote ON (MVP default).
    default_store().override(
        confirm_to_promote={"_default": True, "capacity_quota": True}
    )
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
    s["validation"].evaluate_now(result.validation_id)
    s["db"].commit()

    with pytest.raises(ConfirmRequired):
        s["promotion"].promote(
            action_id=action.action_id, confirm=False, actor="human:42"
        )


def test_promote_with_confirm_succeeds(service_bundle, make_action):
    s = service_bundle
    action = make_action(state="APPROVED")
    default_store().override(
        confirm_to_promote={"_default": True, "capacity_quota": True}
    )
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
    s["validation"].evaluate_now(result.validation_id)
    s["db"].commit()

    out = s["promotion"].promote(
        action_id=action.action_id, confirm=True, actor="human:42"
    )
    s["db"].commit()
    assert out.state == "PROMOTED"
