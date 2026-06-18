"""Staging layer: applies an Approved action to staging branch/scope.

Enforces MS-07, MS-08, MS-11, invariants 4 and 7. The only path that
moves an action into Validating runs through `StagingService.stage()`.
"""

from app.mitigation_safety.staging.service import StagingResult, StagingService
from app.mitigation_safety.staging.scope_isolation import ScopeIsolationVerifier
from app.mitigation_safety.staging.revert_handles import (
    RevertHandle,
    RevertHandleRegistry,
)

__all__ = [
    "RevertHandle",
    "RevertHandleRegistry",
    "ScopeIsolationVerifier",
    "StagingResult",
    "StagingService",
]
