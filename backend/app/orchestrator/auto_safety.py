"""
Auto-remediation kill switch ("Safe Mode, lite").

A circuit breaker for the auto-fixer: if too many auto-fixes fail verification
and get reverted in a short window, auto mode turns OFF and EVERY case falls back
to suggest-only (human) until a human re-enables it.

State is IN-MEMORY (per process) by design -- we are DB-free; cases live in D365.
That means the counters reset on a Render restart/redeploy and are not shared
across multiple instances. That's an accepted trade-off for the demo; to make it
durable later, back it with D365 (count recent "reverted" notes) or Redis.

Thresholds are config-driven (env), so they change without a code edit:
    AUTO_KILL_THRESHOLD   reverts that trip the switch  (default 3)
    AUTO_KILL_WINDOW_SEC  the rolling window in seconds (default 3600 = 1h)
"""

from __future__ import annotations

import threading
import time

from app.orchestrator.appconfig import env_float

THRESHOLD = int(env_float("AUTO_KILL_THRESHOLD", 3))
WINDOW_SEC = env_float("AUTO_KILL_WINDOW_SEC", 3600.0)

_LOCK = threading.Lock()
_failures: list[float] = []     # timestamps of recent auto-fix reverts
_manual_off = False             # set True when a human turns auto OFF


def _recent(now: float) -> list[float]:
    cutoff = now - WINDOW_SEC
    return [t for t in _failures if t >= cutoff]


def _tripped(now: float) -> bool:
    return len(_recent(now)) >= THRESHOLD


def record_failure(case_id: str | None = None) -> None:
    """Call when an auto-fix failed verification and was reverted."""
    now = time.time()
    with _LOCK:
        _failures.append(now)
        n = len(_recent(now))
    print(f"[auto-safety] revert recorded (case {case_id}); "
          f"{n}/{THRESHOLD} in the last {int(WINDOW_SEC)}s"
          + (" -- AUTO MODE TRIPPED OFF" if n >= THRESHOLD else ""))


def is_enabled() -> bool:
    """True if the auto-fixer may execute (not manually off and not tripped)."""
    now = time.time()
    with _LOCK:
        return (not _manual_off) and (not _tripped(now))


def set_enabled(on: bool) -> dict:
    """Human toggle. Re-enabling clears the failure window (fresh start)."""
    global _manual_off, _failures
    with _LOCK:
        _manual_off = not on
        if on:
            _failures = []
    print(f"[auto-safety] auto mode set {'ON' if on else 'OFF'} by human")
    return status()


def status() -> dict:
    now = time.time()
    with _LOCK:
        recent = len(_recent(now))
        tripped = _tripped(now)
        return {
            "enabled": (not _manual_off) and (not tripped),
            "manual_off": _manual_off,
            "tripped": tripped,
            "recent_failures": recent,
            "threshold": THRESHOLD,
            "window_seconds": int(WINDOW_SEC),
        }
