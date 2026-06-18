"""Worker job entry points.

Each job opens a fresh DB session, does its work, commits, and returns. They
must be idempotent — APScheduler can fire late after a misfire window
expires, and we re-arm them on startup.

The worker reuses `api.container.services(db)` so the scheduler runs through
EXACTLY the same code paths a synchronous request would (#3 + #4). Previously
this function had a separate `_build_runtime` that hard-coded MockCIRunner /
MockTelemetrySource regardless of the env selectors — and forgot to wire the
`on_attempt` / `validation_failed` rolling-window events, leaving MS-20 dead
on the scheduler path.
"""

from __future__ import annotations

import logging
import uuid
from typing import Callable, Optional

from app.mitigation_safety.config import default_store
from app.mitigation_safety.notifications.sink import Notification

logger = logging.getLogger("mitigation_safety.worker.jobs")


# Test seam: a callable that returns a fresh Session. When unset, the jobs
# lazy-import `app.db.session.SessionLocal`. Tests can register a
# `sessionmaker` bound to an in-memory SQLite engine here and invoke the
# job entrypoints directly (#31).
_session_factory_override: Optional[Callable[[], object]] = None


def set_session_factory(factory: Optional[Callable[[], object]]) -> None:
    """Override the SessionLocal used by every job. Pass None to reset."""
    global _session_factory_override
    _session_factory_override = factory


def _open_session():
    if _session_factory_override is not None:
        return _session_factory_override()
    from app.db.session import SessionLocal  # lazy: real engine

    return SessionLocal()


# ---- jobs ------------------------------------------------------------------

def window_evaluator(validation_id: str) -> None:
    """Re-evaluate checks for one validation window."""
    from app.mitigation_safety.api.container import services

    db = _open_session()
    try:
        svc = services(db)
        svc.validation.evaluate_now(uuid.UUID(validation_id))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("window_evaluator failed for %s", validation_id)
    finally:
        db.close()


def expiry_poller(validation_id: str) -> None:
    """Force-expire a validation window past window_end."""
    from app.mitigation_safety.api.container import services
    from app.mitigation_safety.db.models import (
        BotActionLog,
        StagingDeployment,
        ValidationResult,
    )
    from app.mitigation_safety.notifications.sink import default_sink

    db = _open_session()
    try:
        svc = services(db)
        vr = svc.validation.mark_expired(uuid.UUID(validation_id))
        # MS-26 notification for expiry. We re-resolve the action so the
        # downstream consumer has the full identifying context.
        if vr.overall_status == "EXPIRED":
            deployment = db.get(StagingDeployment, vr.deployment_id)
            action = (
                db.query(BotActionLog)
                .filter(BotActionLog.action_id == deployment.action_id)
                .one_or_none()
                if deployment is not None
                else None
            )
            default_sink().emit(
                Notification(
                    kind="window_expired",
                    action_id=str(action.action_id) if action else None,
                    ticket_id=(
                        str(action.ticket_id)
                        if action and action.ticket_id
                        else None
                    ),
                    triggering="validation_window_expired",
                    resulting_state="REVERTED",
                    detail={"validation_id": str(vr.validation_id)},
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("expiry_poller failed for %s", validation_id)
    finally:
        db.close()


def guard_sweeper() -> None:
    """Walk every configured category, evaluate guards, and run the
    post-promotion telemetry sweep."""
    from app.mitigation_safety.api.container import services

    db = _open_session()
    try:
        svc = services(db)
        cfg = default_store().get()
        for cat in cfg.categories:
            svc.guard.evaluate(cat)
            svc.guard.evaluate_post_promotion(cat)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("guard_sweeper failed")
    finally:
        db.close()
