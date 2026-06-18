"""APScheduler factory.

Uses SQLAlchemyJobStore against the same Postgres DATABASE_URL the app uses,
so jobs survive process restart (MS-15 durability requirement).
"""

from __future__ import annotations

import logging

try:
    from apscheduler.jobstores.memory import MemoryJobStore  # type: ignore
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore  # type: ignore
    from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore
except ImportError:  # pragma: no cover
    BackgroundScheduler = None  # type: ignore
    SQLAlchemyJobStore = None  # type: ignore
    MemoryJobStore = None  # type: ignore

from app.config import DATABASE_URL

logger = logging.getLogger("mitigation_safety.worker.scheduler")


def build_scheduler(*, durable: bool = True):
    """Return a fresh BackgroundScheduler.

    durable=True  -> SQLAlchemyJobStore against DATABASE_URL (production).
    durable=False -> MemoryJobStore (tests, in-process restarts).
    """
    if BackgroundScheduler is None:
        raise RuntimeError("apscheduler is not installed")

    if durable:
        jobstores = {
            "default": SQLAlchemyJobStore(
                url=DATABASE_URL,
                tablename="ms_apscheduler_jobs",
                engine_options={"pool_pre_ping": True},
            )
        }
    else:
        jobstores = {"default": MemoryJobStore()}

    sched = BackgroundScheduler(
        jobstores=jobstores,
        timezone="UTC",
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60},
    )
    return sched
