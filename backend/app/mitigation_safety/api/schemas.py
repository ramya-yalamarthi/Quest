"""Pydantic request / response models for the 6 mitigation-safety routes.

All string fields carry an explicit `max_length` (#19) so a malformed or
hostile payload can't push unbounded text into logs, the audit table, or
the JSONB blobs. The limits are deliberately generous (4 KiB for free-text
reasons, 256 chars for identifiers) — they only exist as a backstop, not
as a UX constraint.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# Reusable constraints
_IDENT_MAX = 256        # category, target, revert_handle_ref
_REF_MAX = 1024         # artifacts_ref (could include URLs / SHAs)
_REASON_MAX = 4096      # free-text reason fields
_SCOPE_MAX = 128        # scope name (`system` or `category:<name>`)


# ---- /tickets/{id}/mitigate/stage ------------------------------------------

class StageRequest(BaseModel):
    action_id: uuid.UUID
    type: Literal["code", "config"]
    artifacts_ref: str = Field(..., min_length=1, max_length=_REF_MAX)
    expected_outcome: dict = Field(default_factory=dict)
    revert_handle_ref: str = Field(..., min_length=1, max_length=_IDENT_MAX)
    category: str = Field(..., min_length=1, max_length=_IDENT_MAX)
    target: Optional[str] = Field(
        default=None,
        max_length=_IDENT_MAX,
        description="Staging target (branch name or scope). Auto-generated for "
                    "code-type when omitted.",
    )


class StageResponse(BaseModel):
    deployment_id: uuid.UUID
    validation_id: uuid.UUID
    window_start: datetime
    window_end: datetime
    status: Literal["PENDING"]


# ---- /tickets/{id}/mitigate/validation -------------------------------------

class CheckResultOut(BaseModel):
    name: str = Field(..., max_length=_IDENT_MAX)
    status: Literal["PENDING", "PASS", "FAIL"]
    detail: Optional[str] = Field(default=None, max_length=_REASON_MAX)
    evaluated_at: Optional[str] = Field(default=None, max_length=64)


class ValidationOut(BaseModel):
    validation_id: uuid.UUID
    overall_status: Literal["PENDING", "PASS", "FAIL", "EXPIRED"]
    checks: list[CheckResultOut] = []
    elapsed_seconds: int
    time_remaining_seconds: int
    window_start: datetime
    window_end: datetime


# ---- /tickets/{id}/mitigate/promote ----------------------------------------

class PromoteRequest(BaseModel):
    action_id: uuid.UUID
    confirm: bool = False


class PromoteResponse(BaseModel):
    action_id: uuid.UUID
    state: Literal["PROMOTED"]
    rollback_window_end: datetime


# ---- /tickets/{id}/mitigate/revert -----------------------------------------

class RevertRequest(BaseModel):
    action_id: uuid.UUID
    reason: str = Field(..., min_length=1, max_length=_REASON_MAX)


class RevertResponse(BaseModel):
    action_id: uuid.UUID
    # CLOSED is returned when the caller tried to revert a Promoted action
    # AFTER the rollback window elapsed (or the window was never set). The
    # service auto-closes the action and returns the new terminal state so
    # the caller can show a clear "too late to roll back" UX (#11, #12).
    state: Literal["REVERTED", "ROLLEDBACK", "CLOSED"]
    idempotent: bool


# ---- /mitigation/safe-mode -------------------------------------------------

class SafeModeEntryOut(BaseModel):
    scope: str = Field(..., max_length=_SCOPE_MAX)
    active: bool
    entered_at: Optional[datetime] = None
    entered_by: Optional[str] = Field(default=None, max_length=_IDENT_MAX)
    exited_at: Optional[datetime] = None
    exited_by: Optional[str] = Field(default=None, max_length=_IDENT_MAX)
    reason: Optional[str] = Field(default=None, max_length=_REASON_MAX)


class SafeModeView(BaseModel):
    system: SafeModeEntryOut
    categories: dict[str, SafeModeEntryOut]


class SafeModeMutateRequest(BaseModel):
    scope: str = Field(..., min_length=1, max_length=_SCOPE_MAX)
    active: bool
    reason: str = Field(..., min_length=1, max_length=_REASON_MAX)
