"""
Health-check probe scheduler (WBS task R-08).

After an engineer ACCEPTs a recommendation advisory, we want to check ~15 min
later whether the symptoms actually cleared; if they persist, re-surface the
advisory. This module only handles the *timing* -- the orchestrator supplies the
action and the symptom check.

Everything is injectable so tests run instantly (pass an immediate timer) and the
feature stays fully optional -- a scheduling failure must never break the
pipeline. Uses only the stdlib (threading.Timer); no new dependencies.
"""

from __future__ import annotations

import threading
import time
from typing import Callable


class ProbeScheduler:
    def __init__(
        self,
        delay_seconds: float = 900,                 # 15 minutes
        clock: Callable[[], float] = time.monotonic,
        timer_factory=threading.Timer,
        max_probes: int = 2,                         # one initial + one re-fire
    ) -> None:
        self.delay_seconds = delay_seconds
        self.clock = clock
        self.timer_factory = timer_factory
        self.max_probes = max_probes
        self._counts: dict[str, int] = {}

    def schedule(self, key: str, action: Callable[[], None]) -> bool:
        """Schedule ``action`` to run after the delay. Returns True if scheduled,
        False if the per-key cap is reached or scheduling failed.

        Never raises -- the caller's pipeline must not break because of a probe.
        """
        if self._counts.get(key, 0) >= self.max_probes:
            return False
        self._counts[key] = self._counts.get(key, 0) + 1
        try:
            timer = self.timer_factory(self.delay_seconds, action)
            # daemon so a pending probe never blocks process exit
            try:
                timer.daemon = True
            except Exception:
                pass
            timer.start()
            return True
        except Exception:
            return False
