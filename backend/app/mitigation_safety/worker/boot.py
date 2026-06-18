"""Re-arm in-flight validation windows on every process start.

MS-15 / invariant 6: a process restart MUST NOT lose in-flight windows nor
silently extend them. On boot:
  - every ms_validation_result with overall_status=PENDING is inspected.
  - rows with window_end <= now: fire expiry IMMEDIATELY.
  - rows with window_end > now: schedule (a) periodic re-eval and (b) the
    single-shot expiry poller at window_end.
  - the periodic guard sweeper is also registered.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.mitigation_safety.db.models import ValidationResult
from app.mitigation_safety.worker import jobs

logger = logging.getLogger("mitigation_safety.worker.boot")


def on_startup_rearm(db: Session, scheduler) -> None:
    if scheduler is None:
        logger.info("no scheduler — skipping rearm")
        return

    now = datetime.now(timezone.utc)
    pending = (
        db.query(ValidationResult)
        .filter(ValidationResult.overall_status == "PENDING")
        .all()
    )
    logger.info("rearming %d in-flight validation window(s)", len(pending))

    from app.mitigation_safety.domain.ids import aware_utc

    for vr in pending:
        vid = str(vr.validation_id)
        window_end = aware_utc(vr.window_end)
        if window_end <= now:
            scheduler.add_job(
                jobs.expiry_poller,
                args=[vid],
                id=f"expire:{vid}",
                replace_existing=True,
                next_run_time=now,
            )
        else:
            scheduler.add_job(
                jobs.window_evaluator,
                args=[vid],
                id=f"eval:{vid}",
                replace_existing=True,
                trigger="interval",
                seconds=60,
                next_run_time=now,
            )
            scheduler.add_job(
                jobs.expiry_poller,
                args=[vid],
                id=f"expire:{vid}",
                replace_existing=True,
                run_date=window_end,
            )

    scheduler.add_job(
        jobs.guard_sweeper,
        id="guard_sweeper",
        trigger="interval",
        seconds=60,
        replace_existing=True,
        next_run_time=now,
    )
