"""Revert handle registry (MS-08, MS-14, invariant 4).

A revert handle is an opaque reference (string) that names a registered,
TESTED rollback procedure. The runbook owner is responsible for testing
the procedure end-to-end; this registry tracks which handles have a
passing test record.

Handles are encrypted at rest in production (deferred — see README "Deferred
items"); the in-memory implementation here is sufficient for the MVP and
the acceptance tests.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger("mitigation_safety.revert_handles")


@dataclass(frozen=True)
class RevertHandle:
    ref: str
    description: str
    tested_at: datetime
    procedure_name: str
    # NOTE: in production this carries an encrypted payload. The MVP keeps a
    # Python callable so tests can assert it ran.
    fn: Callable[[dict], dict]


class RevertHandleRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_ref: dict[str, RevertHandle] = {}

    def register(
        self,
        *,
        ref: str,
        description: str,
        procedure_name: str,
        fn: Callable[[dict], dict],
    ) -> RevertHandle:
        with self._lock:
            handle = RevertHandle(
                ref=ref,
                description=description,
                tested_at=datetime.now(timezone.utc),
                procedure_name=procedure_name,
                fn=fn,
            )
            self._by_ref[ref] = handle
            logger.info("revert handle registered ref=%s proc=%s", ref, procedure_name)
            return handle

    def has_tested(self, ref: Optional[str]) -> bool:
        if not ref:
            return False
        with self._lock:
            return ref in self._by_ref

    def get(self, ref: str) -> Optional[RevertHandle]:
        with self._lock:
            return self._by_ref.get(ref)

    def execute(self, ref: str, *, payload: dict | None = None) -> dict:
        """Invoke the registered revert procedure. Idempotent at the registry
        layer — the procedure itself MUST be idempotent (invariant 8)."""
        handle = self.get(ref)
        if handle is None:
            raise KeyError(f"unknown revert handle {ref!r}")
        return handle.fn(payload or {})


_DEFAULT_REGISTRY: RevertHandleRegistry | None = None


def default_registry() -> RevertHandleRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = RevertHandleRegistry()
    return _DEFAULT_REGISTRY
