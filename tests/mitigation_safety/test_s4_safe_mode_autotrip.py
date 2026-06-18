"""S4 — Safe Mode auto-trip.

Validation-failure rate exceeds threshold -> Safe Mode (MS-20). In-flight
validations require manual promote (MS-21). Operator clears with explicit
human action (MS-22); audit row records `exited_by` starting with `human:`.
No code path auto-exits Safe Mode (invariant 5).
"""

import pytest

from app.mitigation_safety.domain.errors import (
    ConfirmRequired,
    SafeModeHeld,
    SafeModeHumanRequired,
)
from app.mitigation_safety.safemode.controller import (
    SYSTEM_SCOPE,
    category_scope,
)


def test_s4_autotrip_in_flight_needs_human_promote_and_human_exit(
    service_bundle, make_action
):
    s = service_bundle

    # Drive the validation-failure rate over the threshold.
    for _ in range(3):
        s["rolling"].record(signal="attempt", category="capacity_quota")
        s["rolling"].record(signal="validation_failed", category="capacity_quota")
    s["db"].commit()

    # An in-flight action whose validation has PASSed.
    in_flight = make_action(state="APPROVED", category="capacity_quota", type="config")
    s["mock_ci"].set_default("success")
    stage = s["staging"].stage(
        action_id=in_flight.action_id,
        type="config",
        target="staging-quota",
        artifacts_ref="cfg",
        expected_outcome={"component": "x"},
        revert_handle_ref="rh-quota-restart",
        actor="human:42",
    )
    s["db"].commit()
    s["validation"].evaluate_now(stage.validation_id)
    s["db"].commit()

    # Trip Safe Mode.
    verdict = s["guard"].evaluate("capacity_quota")
    s["db"].commit()
    assert verdict.safe_mode_entered is True

    # In-flight (or new) actions in this category CANNOT be promoted without
    # an explicit confirm AND the Safe Mode hold says human-only. Even with
    # `confirm=False` we get a SafeModeHeld / ConfirmRequired.
    new_action = make_action(state="APPROVED", category="capacity_quota", type="config")
    stage2 = s["staging"].stage(
        action_id=new_action.action_id,
        type="config",
        target="staging-quota-2",
        artifacts_ref="cfg2",
        expected_outcome={"component": "x"},
        revert_handle_ref="rh-quota-restart",
        actor="human:42",
    )
    s["db"].commit()
    s["validation"].evaluate_now(stage2.validation_id)
    s["db"].commit()
    with pytest.raises((SafeModeHeld, ConfirmRequired)):
        s["promotion"].promote(
            action_id=new_action.action_id, confirm=False, actor="human:42"
        )

    # Auto-exit attempts must fail (MS-22).
    with pytest.raises(SafeModeHumanRequired):
        s["safe_mode"].exit(
            scope=category_scope("capacity_quota"),
            exited_by="guard:cleared_by_other_system",
            reason="auto",
        )

    # Operator (human) clears it.
    entry = s["safe_mode"].exit(
        scope=category_scope("capacity_quota"),
        exited_by="human:ops-lead",
        reason="post-incident review done",
    )
    s["db"].commit()
    assert entry.active is False
    assert entry.exited_by == "human:ops-lead"

    # Audit row for the exit exists and is human-authored.
    from app.mitigation_safety.audit.reconstruct import by_action_id
    rows = by_action_id(s["db"], "00000000-0000-0000-0000-000000000000")
    safe_mode_rows = [r for r in rows if r.transition_type == "safe_mode"]
    assert safe_mode_rows
    cleared = [r for r in safe_mode_rows if r.to_state == "CLEARED"]
    assert cleared and cleared[-1].actor.startswith("human:")
