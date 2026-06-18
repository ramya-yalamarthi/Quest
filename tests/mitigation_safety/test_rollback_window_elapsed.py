"""Edge case: rollback window elapsed -> revert returns CLOSED cleanly,
no rollback handle is invoked, transition committed atomically.

Behavior change (#11, #12): previously the service flushed CLOSED then
raised IllegalTransition. On the caller's rollback-on-exception, the
CLOSED state was discarded — a follow-up call saw PROMOTED again and
re-triggered the same code path indefinitely. We now RETURN CLOSED.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.mitigation_safety.db.models import BotActionLog


def test_revert_after_rollback_window_elapses_returns_closed(
    service_bundle, make_action
):
    s = service_bundle
    action = make_action(state="APPROVED", category="capacity_quota", type="config")
    s["mock_ci"].set_default("success")

    stage = s["staging"].stage(
        action_id=action.action_id,
        type="config",
        target="staging-x",
        artifacts_ref="cfg",
        expected_outcome={"component": "x"},
        revert_handle_ref="rh-quota-restart",
        actor="human:42",
    )
    s["db"].commit()
    s["validation"].evaluate_now(stage.validation_id)
    s["db"].commit()
    s["promotion"].promote(action_id=action.action_id, confirm=True, actor="human:42")
    s["db"].commit()

    # Force the rollback window into the past.
    refreshed = s["db"].get(BotActionLog, action.action_id)
    refreshed.rollback_window_end = datetime.now(timezone.utc) - timedelta(seconds=1)
    s["db"].add(refreshed)
    s["db"].commit()

    result = s["revert"].revert(
        action_id=action.action_id, reason="too late", actor="human:42"
    )
    s["db"].commit()

    assert result.state == "CLOSED"
    assert result.idempotent is False
    # The revert handle MUST NOT have been invoked.
    assert s["revert_registry"].test_calls["n"] == 0

    after = s["db"].get(BotActionLog, action.action_id)
    assert after.state == "CLOSED"


def test_revert_with_null_rollback_window_is_treated_as_elapsed(
    service_bundle, make_action
):
    """#11: NULL rollback_window_end must be ELAPSED, not unbounded."""
    s = service_bundle
    action = make_action(state="APPROVED", category="capacity_quota", type="config")
    s["mock_ci"].set_default("success")

    stage = s["staging"].stage(
        action_id=action.action_id,
        type="config",
        target="staging-x",
        artifacts_ref="cfg",
        expected_outcome={"component": "x"},
        revert_handle_ref="rh-quota-restart",
        actor="human:42",
    )
    s["db"].commit()
    s["validation"].evaluate_now(stage.validation_id)
    s["db"].commit()
    s["promotion"].promote(action_id=action.action_id, confirm=True, actor="human:42")
    s["db"].commit()

    # Wipe the rollback window — simulates a row that got into PROMOTED
    # without a window (e.g. legacy data, migration drift).
    refreshed = s["db"].get(BotActionLog, action.action_id)
    refreshed.rollback_window_end = None
    s["db"].add(refreshed)
    s["db"].commit()

    result = s["revert"].revert(
        action_id=action.action_id, reason="ops decision", actor="human:42"
    )
    s["db"].commit()
    assert result.state == "CLOSED"
    assert s["revert_registry"].test_calls["n"] == 0
