"""FastAPI startup/shutdown hooks for the mitigation_safety module.

`on_startup`:
  1. Applies the append-only audit immutability. Failure -> enter system
     Safe Mode (#26) so the API serves with autonomy suspended rather than
     with unprotected audit writes.
  2. Ensures Safe Mode is ON for system + every configured category
     (MS-15, MS-23, invariant 5).
  3. Builds the durable APScheduler with SQLAlchemyJobStore and re-arms
     every in-flight validation window. Failure -> enter system Safe Mode
     (#25) so invariants 2/3 are not silently disabled.

`on_shutdown`:
  - Stops the scheduler. Jobs persist in Postgres and get re-armed next boot.

Outside `APP_ENV in {dev, development, local, test}` boot failures also
re-raise so an orchestrator (k8s readiness probe) restarts the pod instead
of serving a half-broken API.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from app.db.session import SessionLocal, engine
from app.mitigation_safety.audit.service import MitigationAuditLogger
from app.mitigation_safety.config import default_store
from app.mitigation_safety.db.grants import apply_immutability
from app.mitigation_safety.safemode.boot import ensure_default_on
from app.mitigation_safety.safemode.controller import (
    SYSTEM_SCOPE,
    SafeModeController,
)
from app.mitigation_safety.worker import boot as worker_boot
from app.mitigation_safety.worker import scheduler as scheduler_module

logger = logging.getLogger("mitigation_safety.startup")


_SCHEDULER = None


def _in_dev() -> bool:
    env = (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "dev").lower()
    return env in ("dev", "development", "local", "test")


def _force_system_safe_mode(reason: str) -> None:
    """Enter system-scope Safe Mode using its own isolated session.

    Used by the fail-loud boot paths so that even if `apply_immutability`
    or the scheduler init failed, the API still cannot auto-promote.
    """
    db = SessionLocal()
    try:
        ctrl = SafeModeController(db, MitigationAuditLogger(db))
        ctrl.enter(
            scope=SYSTEM_SCOPE,
            entered_by="guard:boot_failure",
            reason=reason,
        )
        db.commit()
    except Exception as exc:
        logger.exception("failed to force system Safe Mode: %s", exc)
        db.rollback()
    finally:
        db.close()


def on_startup() -> None:
    global _SCHEDULER

    # 1. Apply DB-level append-only protection. Failure here means the audit
    # immutability invariant (MS-18) is not in force — refuse to serve
    # outside dev. Inside dev: log + flip system Safe Mode so the visible
    # signal is correct, and continue (so the test suite can boot the app
    # against SQLite without the trigger).
    try:
        with engine.begin() as conn:
            apply_immutability(conn)
    except Exception as exc:
        logger.error("apply_immutability failed: %s", type(exc).__name__)
        _force_system_safe_mode(
            reason=f"apply_immutability failed: {type(exc).__name__}"
        )
        if not _in_dev():
            raise

    # 2. Safe Mode default-on (MS-15, MS-23). Failure here is a hard stop
    # outside dev — Safe Mode is THE fail-safe posture.
    db = SessionLocal()
    try:
        cfg = default_store().get()
        ensure_default_on(db, cfg=cfg)
    except Exception as exc:
        logger.exception("ensure_default_on failed: %s", exc)
        db.rollback()
        if not _in_dev():
            raise
    finally:
        db.close()

    # 3. Durable scheduler + rearm. #25 + #39: if either build_scheduler or
    # on_startup_rearm fails we flip system Safe Mode and refuse to set
    # _SCHEDULER (so on_shutdown is a no-op rather than calling shutdown on
    # a partially-constructed scheduler). Outside dev we re-raise.
    sched = None
    try:
        sched = scheduler_module.build_scheduler(durable=True)
    except Exception as exc:
        logger.error("scheduler build failed: %s", type(exc).__name__)
        _force_system_safe_mode(
            reason=f"scheduler build failed: {type(exc).__name__}"
        )
        if not _in_dev():
            raise
        return

    db = SessionLocal()
    try:
        worker_boot.on_startup_rearm(db, sched)
    except Exception as exc:
        logger.exception("on_startup_rearm failed")
        db.rollback()
        _force_system_safe_mode(
            reason=f"on_startup_rearm failed: {type(exc).__name__}"
        )
        if not _in_dev():
            raise
        return
    finally:
        db.close()

    try:
        sched.start()
    except Exception as exc:
        logger.exception("scheduler.start() failed")
        _force_system_safe_mode(
            reason=f"scheduler.start failed: {type(exc).__name__}"
        )
        if not _in_dev():
            raise
        return

    _SCHEDULER = sched  # only set on full success — #39
    logger.info("mitigation_safety scheduler started")


def on_shutdown() -> None:
    global _SCHEDULER
    if _SCHEDULER is not None:
        try:
            _SCHEDULER.shutdown(wait=False)
        except Exception:
            logger.exception("scheduler shutdown failed")
        _SCHEDULER = None


def get_scheduler() -> Optional[object]:
    return _SCHEDULER
