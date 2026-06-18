"""Mitigation Safety & Staged Rollout module (MS-01..MS-26).

No approved mitigation reaches production directly. Every action is staged,
held in a 24h validation window, promoted only on PASS, reversible in one
action, with default-on Safe Mode that suspends autonomy.

Public entry points used by backend/app/main.py:

    from app.mitigation_safety import register_router, on_startup, on_shutdown

    app.include_router(register_router())
    app.add_event_handler("startup",  on_startup)
    app.add_event_handler("shutdown", on_shutdown)

The functions are imported lazily so that pulling `app.mitigation_safety` for
its sub-packages (domain / audit / etc.) in tests does NOT eagerly drag in
the FastAPI router + sqlalchemy session.
"""

from __future__ import annotations


def register_router():
    from app.mitigation_safety.api.router import register_router as _impl

    return _impl()


def on_startup() -> None:
    from app.mitigation_safety.startup import on_startup as _impl

    _impl()


def on_shutdown() -> None:
    from app.mitigation_safety.startup import on_shutdown as _impl

    _impl()


__all__ = ["register_router", "on_startup", "on_shutdown"]
