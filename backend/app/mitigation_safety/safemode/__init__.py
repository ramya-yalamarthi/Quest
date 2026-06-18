"""Safe Mode controller (MS-19..MS-23, invariant 5)."""

from app.mitigation_safety.safemode.controller import (
    SafeModeController,
    SafeModeEntry,
)
from app.mitigation_safety.safemode.boot import ensure_default_on

__all__ = ["SafeModeController", "SafeModeEntry", "ensure_default_on"]
