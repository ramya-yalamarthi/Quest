"""SQLAlchemy models for the Mitigation Safety module.

Mirrors the existing repo's conventions (UUID PKs via postgresql.UUID, JSONB
blobs, server_default=func.now()). All tables are prefixed `ms_` so they sit
beside the existing schema without collisions.

Tables:
  ms_staging_deployment   (MS-06, MS-07 staging record + tested revert handle)
  ms_validation_result    (MS-08, MS-09 validation window + per-check breakdown)
  ms_safe_mode_state      (MS-19..MS-23 Safe Mode posture)
  ms_bot_action_log       (extends parent SRS §14 with state_history etc.)
  ms_audit_log            (MS-24 append-only audit; immutability via DB trigger)
  ms_guard_event          (MS-20 rolling-window evidence for guards)
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db.base import Base


# --- MS-06, MS-07 ------------------------------------------------------------
class StagingDeployment(Base):
    __tablename__ = "ms_staging_deployment"

    deployment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    ticket_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tickets.ticket_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    type = Column(Text, nullable=False)  # 'code' | 'config'
    target = Column(Text, nullable=False)  # branch name or config scope
    artifacts_ref = Column(Text, nullable=False)
    expected_outcome = Column(JSONB, nullable=False, default=dict)
    # MS-08, invariant 4: revert_handle is mandatory before Staged. NOT NULL.
    revert_handle = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="OPEN")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("type IN ('code','config')", name="ms_deploy_type_ck"),
    )


# --- MS-08, MS-09 ------------------------------------------------------------
class ValidationResult(Base):
    __tablename__ = "ms_validation_result"

    validation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deployment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ms_staging_deployment.deployment_id"),
        nullable=False,
        index=True,
    )
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False, index=True)
    # checks: [{name, status, detail, evaluated_at}]
    checks = Column(JSONB, nullable=False, default=list)
    overall_status = Column(Text, nullable=False, default="PENDING")
    promoted_at = Column(DateTime(timezone=True), nullable=True)
    reverted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "overall_status IN ('PENDING','PASS','FAIL','EXPIRED')",
            name="ms_vr_status_ck",
        ),
    )


# --- MS-19..MS-23 ------------------------------------------------------------
class SafeModeState(Base):
    """Safe Mode posture, system-wide and per-category.

    Invariant 5 / MS-22: exit MUST be by a human actor. Enforced server-side
    in the controller AND at the DB level by the check constraint below.
    """

    __tablename__ = "ms_safe_mode_state"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope = Column(Text, nullable=False)  # 'system' | 'category:<name>'
    active = Column(Boolean, nullable=False, default=True)
    entered_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    entered_by = Column(Text, nullable=False)  # 'human:<id>' | 'guard:<signal>'
    exited_at = Column(DateTime(timezone=True), nullable=True)
    exited_by = Column(Text, nullable=True)  # ALWAYS 'human:<id>' when set
    reason = Column(Text, nullable=True)

    __table_args__ = (
        Index("ms_safemode_scope_active_ix", "scope", "active"),
        CheckConstraint(
            # active rows: no exit; inactive rows: human exit recorded.
            "(active = true AND exited_at IS NULL AND exited_by IS NULL) "
            "OR (active = false AND exited_at IS NOT NULL "
            "    AND exited_by LIKE 'human:%')",
            name="ms_safemode_exit_human_only_ck",
        ),
    )


# --- bot_action_log extension (SRS §14) --------------------------------------
class BotActionLog(Base):
    """The state-machine record for one mitigation action.

    `state_history` carries every transition with actor + timestamp so we
    can reconstruct the lifecycle without joining the audit log.
    """

    __tablename__ = "ms_bot_action_log"

    action_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tickets.ticket_id"),
        nullable=True,
        index=True,
    )
    category = Column(Text, nullable=False)
    eligible = Column(Boolean, nullable=False, default=False)
    state = Column(Text, nullable=False, default="DRAFTED", index=True)
    type = Column(Text, nullable=True)  # 'code' | 'config' (set at draft)
    revert_handle_ref = Column(Text, nullable=True)
    # state_history: [{transition, actor, timestamp, from, to}]
    state_history = Column(JSONB, nullable=False, default=list)
    validation_id = Column(UUID(as_uuid=True), nullable=True)
    rollback_window_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "type IS NULL OR type IN ('code','config')",
            name="ms_action_type_ck",
        ),
    )


# --- MS-24 -------------------------------------------------------------------
class MitigationAuditLog(Base):
    """Append-only audit log for the Mitigation Safety module.

    Immutability is enforced at the DB level by a BEFORE UPDATE / DELETE
    trigger that raises, plus REVOKE on UPDATE/DELETE/TRUNCATE. See
    `app.mitigation_safety.db.grants.apply_immutability`.
    """

    __tablename__ = "ms_audit_log"

    audit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ts = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    action_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    ticket_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    actor = Column(Text, nullable=False)
    # 'state' | 'safe_mode' | 'guard' | 'config' | 'system'
    transition_type = Column(Text, nullable=False)
    from_state = Column(Text, nullable=True)
    to_state = Column(Text, nullable=True)
    detail = Column(JSONB, nullable=False, default=dict)


# --- MS-20 -------------------------------------------------------------------
class GuardEvent(Base):
    """Evidence rows feeding the rolling-window guard evaluator."""

    __tablename__ = "ms_guard_event"

    event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ts = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    category = Column(Text, nullable=False)
    # 'validation_failed' | 'rolled_back' | 'declined' | 'attempt'
    signal = Column(Text, nullable=False)
    action_id = Column(UUID(as_uuid=True), nullable=True)
    validation_id = Column(UUID(as_uuid=True), nullable=True)
    metric_value = Column(Float, nullable=True)

    __table_args__ = (
        Index("ms_guard_event_window_ix", "category", "signal", "ts"),
    )
