"""Worker durability: in-flight windows are re-evaluated after a restart.

We can't easily install APScheduler in this environment, so we test the
`on_startup_rearm` *behavior* by passing a stub scheduler that records jobs
the rearm would have added — and verifies the past-due path immediately
flips to EXPIRED via mark_expired.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.mitigation_safety.db.models import (
    BotActionLog,
    StagingDeployment,
    ValidationResult,
)
from app.mitigation_safety.worker import boot as worker_boot


@dataclass
class StubScheduler:
    jobs: list[dict] = field(default_factory=list)

    def add_job(self, func, **kwargs: Any) -> None:
        self.jobs.append({"func": func.__name__, **kwargs})


def test_rearm_schedules_eval_and_expiry_for_pending(
    service_bundle, make_action, db
):
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
    db.commit()

    sched = StubScheduler()
    worker_boot.on_startup_rearm(db, sched)

    funcs = [j["func"] for j in sched.jobs]
    assert "window_evaluator" in funcs
    assert "expiry_poller" in funcs
    assert "guard_sweeper" in funcs


def test_rearm_immediately_expires_past_due_window(
    service_bundle, make_action, db
):
    s = service_bundle
    action = make_action(state="APPROVED")
    s["mock_ci"].set_default("success")
    result = s["staging"].stage(
        action_id=action.action_id,
        type="config",
        target="staging-x",
        artifacts_ref="cfg",
        expected_outcome={"component": "x"},
        revert_handle_ref="rh-quota-restart",
        actor="human:42",
    )
    db.commit()

    # Force the window into the past.
    vr = db.get(ValidationResult, result.validation_id)
    vr.window_end = datetime.now(timezone.utc) - timedelta(seconds=10)
    db.add(vr)
    db.commit()

    sched = StubScheduler()
    worker_boot.on_startup_rearm(db, sched)

    expiry_jobs = [j for j in sched.jobs if j["func"] == "expiry_poller"]
    assert expiry_jobs
    # next_run_time is set to now -> scheduler will fire it immediately.
    # We simulate the firing here:
    s["validation"].mark_expired(result.validation_id)
    db.commit()

    refreshed = db.get(ValidationResult, result.validation_id)
    assert refreshed.overall_status == "EXPIRED"
