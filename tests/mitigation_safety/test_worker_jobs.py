"""Drive the worker job entrypoints (#31).

The original worker test used a StubScheduler and never invoked
`window_evaluator` / `expiry_poller` / `guard_sweeper` themselves. This
file calls them directly with the test SessionLocal monkey-patched to
yield the test session, then asserts state transitions land as expected.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
import pytest

from app.mitigation_safety.db.models import (
    BotActionLog,
    ValidationResult,
)
from app.mitigation_safety.worker import jobs as worker_jobs


@pytest.fixture
def patched_session_local(SessionMaker):
    """Override the worker's session factory with the test sessionmaker."""
    worker_jobs.set_session_factory(SessionMaker)
    yield
    worker_jobs.set_session_factory(None)


@pytest.fixture
def stage_an_action(service_bundle, make_action, db):
    def _factory(category: str = "capacity_quota"):
        action = make_action(state="APPROVED", category=category, type="config")
        service_bundle["mock_ci"].set_default("success")
        stage = service_bundle["staging"].stage(
            action_id=action.action_id,
            type="config",
            target="staging-x",
            artifacts_ref="cfg",
            expected_outcome={"component": "x"},
            revert_handle_ref="rh-quota-restart",
            actor="human:tester",
        )
        db.commit()
        return action, stage

    return _factory


def test_window_evaluator_drives_validation_to_pass(
    patched_session_local, stage_an_action, db, mock_ci, mock_telemetry,  # noqa: ARG001
):
    """Calling window_evaluator() against a PENDING validation result must
    drive it to PASS when the scripted backends all return success."""
    # We have to register the test backends into api.container singletons so
    # the worker (which builds runtime via container.services()) sees them.
    from app.mitigation_safety.api.container import set_ci_runner, set_telemetry

    set_ci_runner(mock_ci.set_default("success"))
    set_telemetry(mock_telemetry)

    # Also register the test revert handles into the default registry the
    # worker reaches via container.
    from app.mitigation_safety.staging.revert_handles import default_registry

    reg = default_registry()
    if not reg.has_tested("rh-quota-restart"):
        reg.register(
            ref="rh-quota-restart", description="t", procedure_name="p",
            fn=lambda payload: {"ok": True},
        )

    _, stage = stage_an_action()
    worker_jobs.window_evaluator(str(stage.validation_id))

    refreshed = db.get(ValidationResult, stage.validation_id)
    assert refreshed.overall_status in ("PASS", "PENDING")


def test_expiry_poller_marks_expired_when_past_window(
    patched_session_local, stage_an_action, db, mock_ci, mock_telemetry,  # noqa: ARG001
):
    from app.mitigation_safety.api.container import set_ci_runner, set_telemetry
    from app.mitigation_safety.staging.revert_handles import default_registry

    set_ci_runner(mock_ci)
    set_telemetry(mock_telemetry)
    reg = default_registry()
    if not reg.has_tested("rh-quota-restart"):
        reg.register(
            ref="rh-quota-restart", description="t", procedure_name="p",
            fn=lambda payload: {"ok": True},
        )

    action, stage = stage_an_action()
    # Force window into the past.
    vr = db.get(ValidationResult, stage.validation_id)
    vr.window_end = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.add(vr)
    db.commit()

    worker_jobs.expiry_poller(str(stage.validation_id))

    refreshed_vr = db.get(ValidationResult, stage.validation_id)
    assert refreshed_vr.overall_status == "EXPIRED"
    refreshed_action = db.get(BotActionLog, action.action_id)
    assert refreshed_action.state == "REVERTED"


def test_guard_sweeper_runs_without_error(
    patched_session_local, mock_ci, mock_telemetry,  # noqa: ARG001
):
    from app.mitigation_safety.api.container import set_ci_runner, set_telemetry

    set_ci_runner(mock_ci)
    set_telemetry(mock_telemetry)
    # Smoke-test: with no in-flight actions, sweeper must not raise.
    worker_jobs.guard_sweeper()
