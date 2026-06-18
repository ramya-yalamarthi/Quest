"""mitigation_safety: ms_* tables, immutability trigger, grants.

Revision ID: 20260617_0001
Revises: 20260617_0000
Create Date: 2026-06-17

Creates the six ms_* tables, indices, the append-only audit-log protection
(MS-18, invariant 9), AND the APScheduler durable jobstore table (#24) in a
single transaction. Depends on the legacy_baseline revision which creates
`tickets`, `users`, etc.

Downgrade drops the ms_* tables and removes the immutability trigger but
leaves the legacy schema untouched.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.mitigation_safety.db.grants import apply_immutability, drop_immutability


revision = "20260617_0001"
down_revision = "20260617_0000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- ms_staging_deployment (MS-06, MS-07) -------------------------------
    op.create_table(
        "ms_staging_deployment",
        sa.Column("deployment_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.ticket_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("artifacts_ref", sa.Text(), nullable=False),
        sa.Column(
            "expected_outcome",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # MS-08 invariant 4: revert_handle is mandatory.
        sa.Column("revert_handle", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'OPEN'")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("type IN ('code','config')", name="ms_deploy_type_ck"),
    )
    op.create_index(
        "ms_staging_deployment_action_id_ix",
        "ms_staging_deployment",
        ["action_id"],
    )
    op.create_index(
        "ms_staging_deployment_ticket_id_ix",
        "ms_staging_deployment",
        ["ticket_id"],
    )

    # --- ms_validation_result (MS-08, MS-09) --------------------------------
    op.create_table(
        "ms_validation_result",
        sa.Column("validation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "deployment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ms_staging_deployment.deployment_id"),
            nullable=False,
        ),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "checks",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "overall_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "overall_status IN ('PENDING','PASS','FAIL','EXPIRED')",
            name="ms_vr_status_ck",
        ),
    )
    op.create_index(
        "ms_validation_result_deployment_id_ix",
        "ms_validation_result",
        ["deployment_id"],
    )
    op.create_index(
        "ms_validation_result_window_end_ix",
        "ms_validation_result",
        ["window_end"],
    )

    # --- ms_safe_mode_state (MS-19..MS-23) ----------------------------------
    op.create_table(
        "ms_safe_mode_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column(
            "active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "entered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("entered_by", sa.Text(), nullable=False),
        sa.Column("exited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exited_by", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(active = true AND exited_at IS NULL AND exited_by IS NULL) "
            "OR (active = false AND exited_at IS NOT NULL "
            "    AND exited_by LIKE 'human:%')",
            name="ms_safemode_exit_human_only_ck",
        ),
    )
    op.create_index(
        "ms_safemode_scope_active_ix",
        "ms_safe_mode_state",
        ["scope", "active"],
    )

    # --- ms_bot_action_log (SRS §14 extension) ------------------------------
    op.create_table(
        "ms_bot_action_log",
        sa.Column("action_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.ticket_id"),
            nullable=True,
        ),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column(
            "eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "state",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'DRAFTED'"),
        ),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("revert_handle_ref", sa.Text(), nullable=True),
        sa.Column(
            "state_history",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("validation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "rollback_window_end", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "type IS NULL OR type IN ('code','config')",
            name="ms_action_type_ck",
        ),
    )
    op.create_index(
        "ms_bot_action_log_ticket_id_ix",
        "ms_bot_action_log",
        ["ticket_id"],
    )
    op.create_index(
        "ms_bot_action_log_state_ix",
        "ms_bot_action_log",
        ["state"],
    )

    # --- ms_audit_log (MS-24, append-only) ----------------------------------
    op.create_table(
        "ms_audit_log",
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("transition_type", sa.Text(), nullable=False),
        sa.Column("from_state", sa.Text(), nullable=True),
        sa.Column("to_state", sa.Text(), nullable=True),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index("ms_audit_log_ts_ix", "ms_audit_log", ["ts"])
    op.create_index(
        "ms_audit_log_action_id_ix", "ms_audit_log", ["action_id"]
    )
    op.create_index(
        "ms_audit_log_ticket_id_ix", "ms_audit_log", ["ticket_id"]
    )

    # --- ms_guard_event (MS-20) ---------------------------------------------
    op.create_table(
        "ms_guard_event",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("signal", sa.Text(), nullable=False),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "validation_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("metric_value", sa.Float(), nullable=True),
    )
    op.create_index(
        "ms_guard_event_window_ix",
        "ms_guard_event",
        ["category", "signal", "ts"],
    )

    # --- APScheduler durable jobstore (#24) ---------------------------------
    # APScheduler creates this lazily on first start, but autogenerate would
    # otherwise propose dropping it. We pre-create with the exact schema
    # APScheduler's SQLAlchemyJobStore expects so the migration is the source
    # of truth.
    op.create_table(
        "ms_apscheduler_jobs",
        sa.Column("id", sa.Unicode(191), primary_key=True),
        sa.Column("next_run_time", sa.Float(precision=25), nullable=True),
        sa.Column("job_state", sa.LargeBinary(), nullable=False),
    )
    op.create_index(
        "ms_apscheduler_jobs_next_run_time_ix",
        "ms_apscheduler_jobs",
        ["next_run_time"],
    )

    # --- DB-level append-only enforcement on ms_audit_log -------------------
    apply_immutability(op.get_bind())


def downgrade() -> None:
    drop_immutability(op.get_bind())
    for tbl in [
        "ms_apscheduler_jobs",
        "ms_guard_event",
        "ms_audit_log",
        "ms_bot_action_log",
        "ms_safe_mode_state",
        "ms_validation_result",
        "ms_staging_deployment",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
