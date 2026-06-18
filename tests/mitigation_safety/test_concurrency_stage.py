"""Concurrent stage() race (#35).

SQLite doesn't enforce `with_for_update`, so we can't reproduce the actual
deadlock-style race here. Instead we verify the orthogonal correctness
guarantee that exists even WITHOUT a lock: a second stage() on an action
that is already STAGED/VALIDATING raises IllegalTransition. This is what
the lock+state check buys us — when running against Postgres the lock
serializes; on every backend the state check rejects the duplicate.
"""

import pytest

from app.mitigation_safety.domain.errors import IllegalTransition


def test_second_stage_on_validating_action_raises(service_bundle, make_action):
    s = service_bundle
    action = make_action(state="APPROVED", category="capacity_quota", type="config")
    s["mock_ci"].set_default("success")

    s["staging"].stage(
        action_id=action.action_id,
        type="config",
        target="staging-x",
        artifacts_ref="cfg",
        expected_outcome={},
        revert_handle_ref="rh-quota-restart",
        actor="human:42",
    )
    s["db"].commit()

    # action.state is now VALIDATING. A second stage() must NOT pass.
    with pytest.raises(IllegalTransition):
        s["staging"].stage(
            action_id=action.action_id,
            type="config",
            target="staging-y",
            artifacts_ref="cfg",
            expected_outcome={},
            revert_handle_ref="rh-quota-restart",
            actor="human:42",
        )
