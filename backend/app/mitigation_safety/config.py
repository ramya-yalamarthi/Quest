"""Hot-reloadable configuration for the Mitigation Safety module (MS-19).

Keys are loaded from a JSON file at `MITIGATION_SAFETY_CONFIG_PATH` (env);
falling back to safe defaults that match the SRS table. `ConfigStore.reload()`
checks the file's mtime and re-parses on change without a code deploy.

All getters return immutable frozen dataclass snapshots so callers can hold
the value across a transaction without surprises.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GuardThresholds:
    """MS-14, MS-16, MS-20."""

    validation_failure_rate: float = 0.20  # share of FAIL/(FAIL+PASS) over window
    rollback_rate: float = 0.10  # share of ROLLEDBACK / PROMOTED over window
    decline_rate: float = 0.25  # share of human declines over window
    rolling_window_seconds: int = 3600
    min_samples: int = 5  # ignore tiny denominators
    # telemetry_bounds: {component: {metric: {"min": float, "max": float}}}
    telemetry_bounds: dict[str, dict[str, dict[str, float]]] = field(default_factory=dict)


@dataclass(frozen=True)
class MitigationConfig:
    """Top-level snapshot. Per-category overrides are layered in `for_category`."""

    validation_window_seconds: int = 86400  # MS-08 default 24h
    rollback_window_seconds: int = 86400  # MS-15 default 24h
    # Per-category overrides. The special key "_default" applies when a category
    # has no explicit entry. MVP: confirm-to-promote ON.
    confirm_to_promote: dict[str, bool] = field(
        default_factory=lambda: {"_default": True}
    )
    # Per-category window overrides.
    validation_window_overrides: dict[str, int] = field(default_factory=dict)
    rollback_window_overrides: dict[str, int] = field(default_factory=dict)
    guards: GuardThresholds = field(default_factory=GuardThresholds)
    safe_mode_default_on_start: bool = True
    allow_listed_categories: tuple[str, ...] = ("capacity_quota",)
    # Categories the module knows about. MS-26 notifications iterate this.
    categories: tuple[str, ...] = ("capacity_quota", "software_defect")
    # Check execution timeouts (MS-13).
    check_deadline_seconds: int = 600
    ci_deadline_seconds: int = 1800

    def confirm_required_for(self, category: str) -> bool:
        if category in self.confirm_to_promote:
            return bool(self.confirm_to_promote[category])
        return bool(self.confirm_to_promote.get("_default", True))

    def validation_window_for(self, category: str) -> int:
        return int(
            self.validation_window_overrides.get(
                category, self.validation_window_seconds
            )
        )

    def rollback_window_for(self, category: str) -> int:
        return int(
            self.rollback_window_overrides.get(
                category, self.rollback_window_seconds
            )
        )


def _from_dict(data: dict[str, Any]) -> MitigationConfig:
    g = data.get("guards", {}) or {}
    guards = GuardThresholds(
        validation_failure_rate=float(g.get("validation_failure_rate", 0.20)),
        rollback_rate=float(g.get("rollback_rate", 0.10)),
        decline_rate=float(g.get("decline_rate", 0.25)),
        rolling_window_seconds=int(g.get("rolling_window_seconds", 3600)),
        min_samples=int(g.get("min_samples", 5)),
        telemetry_bounds=g.get("telemetry_bounds", {}) or {},
    )
    return MitigationConfig(
        validation_window_seconds=int(
            data.get("validation_window_seconds", 86400)
        ),
        rollback_window_seconds=int(data.get("rollback_window_seconds", 86400)),
        confirm_to_promote=dict(
            data.get("confirm_to_promote", {"_default": True})
        ),
        validation_window_overrides=dict(
            data.get("validation_window_overrides", {})
        ),
        rollback_window_overrides=dict(
            data.get("rollback_window_overrides", {})
        ),
        guards=guards,
        safe_mode_default_on_start=bool(
            data.get("safe_mode_default_on_start", True)
        ),
        allow_listed_categories=tuple(
            data.get("allow_listed_categories", ["capacity_quota"])
        ),
        categories=tuple(
            data.get("categories", ["capacity_quota", "software_defect"])
        ),
        check_deadline_seconds=int(data.get("check_deadline_seconds", 600)),
        ci_deadline_seconds=int(data.get("ci_deadline_seconds", 1800)),
    )


class ConfigStore:
    """File-backed config snapshot with mtime-based hot reload (MS-19)."""

    def __init__(self, path: str | None = None) -> None:
        self._path = path or os.getenv("MITIGATION_SAFETY_CONFIG_PATH")
        self._lock = threading.Lock()
        self._mtime: float | None = None
        self._cfg: MitigationConfig = MitigationConfig()
        if self._path and Path(self._path).exists():
            self.reload(force=True)

    def get(self) -> MitigationConfig:
        if self._path and Path(self._path).exists():
            try:
                cur = os.stat(self._path).st_mtime
                if self._mtime is None or cur > self._mtime:
                    self.reload(force=True)
            except FileNotFoundError:
                pass
        return self._cfg

    def reload(self, *, force: bool = False) -> MitigationConfig:
        with self._lock:
            if not self._path:
                self._cfg = MitigationConfig()
                return self._cfg
            try:
                stat = os.stat(self._path)
            except FileNotFoundError:
                self._cfg = MitigationConfig()
                self._mtime = None
                return self._cfg
            if not force and self._mtime is not None and stat.st_mtime <= self._mtime:
                return self._cfg
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._cfg = _from_dict(data)
            self._mtime = stat.st_mtime
            return self._cfg

    def override(self, **kwargs) -> MitigationConfig:
        """Test-only convenience: replace fields on the current snapshot."""
        with self._lock:
            self._cfg = replace(self._cfg, **kwargs)
            return self._cfg


_DEFAULT_STORE: ConfigStore | None = None


def default_store() -> ConfigStore:
    """Process-wide singleton — replaced in tests via dependency override."""
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = ConfigStore()
    return _DEFAULT_STORE
