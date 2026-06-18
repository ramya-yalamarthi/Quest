"""Test scaffolding for the Mitigation Safety module.

Strategy
--------
We need a fresh DB per test that:
  - exercises every ms_* model
  - lets us assert the append-only invariant on ms_audit_log
  - does NOT require running Postgres in CI

We use SQLite in-memory. The legacy app models depend on pgvector (which is
not installed in the unit-test environment); we avoid importing them and
create ONLY the mitigation_safety tables for the test schema. The FK from
`ms_bot_action_log` to `tickets(ticket_id)` is dropped at create-time so the
test schema is self-contained.

The Postgres BEFORE UPDATE/DELETE trigger on ms_audit_log is emulated by a
SQLAlchemy `before_flush` listener that raises identically — invariant 9 is
tested through that listener.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest

# Set required env BEFORE any app imports.
os.environ.setdefault(
    "DATABASE_URL", "postgresql://test:test@localhost:5432/test"
)
os.environ.setdefault("JWT_SECRET", "test_only")

THIS = os.path.dirname(__file__)
BACKEND = os.path.abspath(os.path.join(THIS, "..", "..", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


# ---- Build an isolated Base/metadata for the ms_* models only ----------------
#
# We re-declare the ms_* tables inline against a fresh Base so the test schema
# does NOT drag in the legacy models that require pgvector. The runtime
# models remain unchanged; this is purely a test-side compatibility shim.

import sqlalchemy as sa
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Index,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy import event
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.sql import func


class UuidStr(TypeDecorator):
    """SQLite-safe UUID column.

    Runtime code passes ``uuid.UUID`` instances into filters; the production
    column type ``UUID(as_uuid=True)`` accepts both UUID and str. SQLite's
    ``String(36)`` does not, so without this TypeDecorator a query like
    ``action_id == uuid.UUID(...)`` would silently fail to match the stored
    string form. The decorator coerces both ways at bind time.
    """

    impl = String(36)
    cache_ok = True

    @property
    def python_type(self):  # type: ignore[override]
        # The reconstruct helper inspects this to decide whether to pass a
        # `uuid.UUID` or a `str` to a filter. Tell it we store strings.
        return str

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(value)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        return value  # keep as str — runtime code accepts both


TestBase = declarative_base()


class StagingDeployment(TestBase):
    __tablename__ = "ms_staging_deployment"
    deployment_id = Column(UuidStr(), primary_key=True, default=lambda: str(uuid.uuid4()))
    action_id = Column(UuidStr(), nullable=False, index=True)
    ticket_id = Column(UuidStr(), nullable=True, index=True)
    type = Column(Text, nullable=False)
    target = Column(Text, nullable=False)
    artifacts_ref = Column(Text, nullable=False)
    expected_outcome = Column(JSON, nullable=False, default=dict)
    revert_handle = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="OPEN")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (CheckConstraint("type IN ('code','config')", name="ms_deploy_type_ck"),)


class ValidationResult(TestBase):
    __tablename__ = "ms_validation_result"
    validation_id = Column(UuidStr(), primary_key=True, default=lambda: str(uuid.uuid4()))
    deployment_id = Column(UuidStr(), nullable=False, index=True)
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False, index=True)
    checks = Column(JSON, nullable=False, default=list)
    overall_status = Column(Text, nullable=False, default="PENDING")
    promoted_at = Column(DateTime(timezone=True), nullable=True)
    reverted_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint(
            "overall_status IN ('PENDING','PASS','FAIL','EXPIRED')",
            name="ms_vr_status_ck",
        ),
    )


class SafeModeState(TestBase):
    __tablename__ = "ms_safe_mode_state"
    id = Column(UuidStr(), primary_key=True, default=lambda: str(uuid.uuid4()))
    scope = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    entered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    entered_by = Column(Text, nullable=False)
    exited_at = Column(DateTime(timezone=True), nullable=True)
    exited_by = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    __table_args__ = (
        Index("ms_safemode_scope_active_ix", "scope", "active"),
        CheckConstraint(
            "(active = 1 AND exited_at IS NULL AND exited_by IS NULL) "
            "OR (active = 0 AND exited_at IS NOT NULL "
            "    AND exited_by LIKE 'human:%')",
            name="ms_safemode_exit_human_only_ck",
        ),
    )


class BotActionLog(TestBase):
    __tablename__ = "ms_bot_action_log"
    action_id = Column(UuidStr(), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id = Column(UuidStr(), nullable=True, index=True)
    category = Column(Text, nullable=False)
    eligible = Column(Boolean, nullable=False, default=False)
    state = Column(Text, nullable=False, default="DRAFTED", index=True)
    type = Column(Text, nullable=True)
    revert_handle_ref = Column(Text, nullable=True)
    state_history = Column(JSON, nullable=False, default=list)
    validation_id = Column(UuidStr(), nullable=True)
    rollback_window_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MitigationAuditLog(TestBase):
    __tablename__ = "ms_audit_log"
    audit_id = Column(UuidStr(), primary_key=True, default=lambda: str(uuid.uuid4()))
    ts = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    action_id = Column(UuidStr(), nullable=False, index=True)
    ticket_id = Column(UuidStr(), nullable=True, index=True)
    actor = Column(Text, nullable=False)
    transition_type = Column(Text, nullable=False)
    from_state = Column(Text, nullable=True)
    to_state = Column(Text, nullable=True)
    detail = Column(JSON, nullable=False, default=dict)


class GuardEvent(TestBase):
    __tablename__ = "ms_guard_event"
    event_id = Column(UuidStr(), primary_key=True, default=lambda: str(uuid.uuid4()))
    ts = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    category = Column(Text, nullable=False)
    signal = Column(Text, nullable=False)
    action_id = Column(UuidStr(), nullable=True)
    validation_id = Column(UuidStr(), nullable=True)
    metric_value = Column(Float, nullable=True)
    __table_args__ = (
        Index("ms_guard_event_window_ix", "category", "signal", "ts"),
    )


# --- Monkey-patch the runtime models module so production code reads/writes
# the same table objects we just created. The test_base classes inherit from
# the shared `declarative_base()` so SQLAlchemy can map them.
import app.mitigation_safety.db.models as _runtime_models
_runtime_models.StagingDeployment = StagingDeployment
_runtime_models.ValidationResult = ValidationResult
_runtime_models.SafeModeState = SafeModeState
_runtime_models.BotActionLog = BotActionLog
_runtime_models.MitigationAuditLog = MitigationAuditLog
_runtime_models.GuardEvent = GuardEvent

# Replace symbols inside the modules that already imported them.
import app.mitigation_safety.audit.service as _audit_service
_audit_service.MitigationAuditLog = MitigationAuditLog
import app.mitigation_safety.audit.reconstruct as _audit_reconstruct
_audit_reconstruct.MitigationAuditLog = MitigationAuditLog
import app.mitigation_safety.safemode.controller as _safemode_ctrl
_safemode_ctrl.SafeModeState = SafeModeState
import app.mitigation_safety.guards.rolling_window as _rolling
_rolling.GuardEvent = GuardEvent
import app.mitigation_safety.guards.evaluator as _guard_eval
_guard_eval.BotActionLog = BotActionLog
_guard_eval.StagingDeployment = StagingDeployment
_guard_eval.ValidationResult = ValidationResult
import app.mitigation_safety.staging.service as _stg_service
_stg_service.BotActionLog = BotActionLog
_stg_service.StagingDeployment = StagingDeployment
_stg_service.ValidationResult = ValidationResult
import app.mitigation_safety.staging.promotion as _promote
_promote.BotActionLog = BotActionLog
_promote.StagingDeployment = StagingDeployment
_promote.ValidationResult = ValidationResult
import app.mitigation_safety.staging.revert as _revert_mod
_revert_mod.BotActionLog = BotActionLog
_revert_mod.StagingDeployment = StagingDeployment
_revert_mod.ValidationResult = ValidationResult
import app.mitigation_safety.validation.service as _val_service
_val_service.BotActionLog = BotActionLog
_val_service.StagingDeployment = StagingDeployment
_val_service.ValidationResult = ValidationResult


# ---- SQLite immutability listener (emulates the PG trigger) -----------------
def _install_audit_immutability() -> None:
    @event.listens_for(Session, "before_flush")
    def _before_flush(session, flush_context, instances):  # noqa: ANN001
        for obj in list(session.dirty):
            if isinstance(obj, MitigationAuditLog):
                # Only block if the row already had a PK (i.e. it's a real UPDATE).
                state = sa.inspect(obj)
                if state.has_identity:
                    raise sa.exc.IntegrityError(
                        "ms_audit_log is append-only (MS-18)",
                        params={},
                        orig=Exception("append-only"),
                    )
        for obj in list(session.deleted):
            if isinstance(obj, MitigationAuditLog):
                raise sa.exc.IntegrityError(
                    "ms_audit_log is append-only (MS-18)",
                    params={},
                    orig=Exception("append-only"),
                )


_install_audit_immutability()


# ---- SQLite UUID adapter ----------------------------------------------------
# Runtime code constructs uuid.UUID (Postgres-native). On SQLite our
# String(36) columns need a sqlite3-level adapter to accept them.
import sqlite3 as _sqlite3
_sqlite3.register_adapter(uuid.UUID, lambda u: str(u))


# ---- Fixtures ---------------------------------------------------------------

@pytest.fixture
def engine():
    # `StaticPool` keeps a single connection alive for the lifetime of the
    # engine, which is required for in-memory SQLite — each new connection
    # would otherwise get its own (empty) database. This matters when a
    # FastAPI route opens a fresh session via dependency-override.
    from sqlalchemy.pool import StaticPool

    eng = sa.create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Enable SQLite CHECK constraint enforcement (default in 3.x).
    @event.listens_for(eng, "connect")
    def _on_connect(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    TestBase.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def SessionMaker(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture
def db(SessionMaker) -> Iterator[Session]:
    s = SessionMaker()
    try:
        yield s
    finally:
        s.close()


# ---- Factories --------------------------------------------------------------

@pytest.fixture
def make_action(db):
    def _factory(
        *,
        category: str = "capacity_quota",
        eligible: bool = True,
        revert_handle_ref: str | None = "rh-quota-restart",
        state: str = "APPROVED",
        type: str | None = None,
        ticket_id: str | None = None,
    ) -> BotActionLog:
        a = BotActionLog(
            action_id=str(uuid.uuid4()),
            ticket_id=ticket_id,
            category=category,
            eligible=eligible,
            state=state,
            type=type,
            revert_handle_ref=revert_handle_ref,
            state_history=[],
        )
        db.add(a)
        db.flush()
        return a

    return _factory


@pytest.fixture
def revert_registry():
    from app.mitigation_safety.staging.revert_handles import RevertHandleRegistry

    reg = RevertHandleRegistry()
    calls = {"n": 0}

    def proc(payload):
        calls["n"] += 1
        return {"ok": True, "calls": calls["n"], "payload": payload}

    reg.register(ref="rh-quota-restart", description="t", procedure_name="p", fn=proc)
    reg.register(ref="rh-code-revert", description="t", procedure_name="p", fn=proc)
    reg.test_calls = calls  # type: ignore[attr-defined]
    return reg


@pytest.fixture
def mock_ci():
    from app.mitigation_safety.validation.ci.mock import MockCIRunner
    return MockCIRunner().set_default("success")


@pytest.fixture
def mock_telemetry():
    from app.mitigation_safety.validation.telemetry.mock import MockTelemetrySource
    return MockTelemetrySource()


@pytest.fixture
def incidents_source():
    from app.mitigation_safety.validation.checks.correlated_incidents import (
        StaticCorrelatedIncidentsSource,
    )
    return StaticCorrelatedIncidentsSource()


@pytest.fixture
def signoff_source():
    from app.mitigation_safety.validation.checks.human_signoff import (
        StaticHumanSignoffSource,
    )
    return StaticHumanSignoffSource()


@pytest.fixture
def cfg():
    from app.mitigation_safety.config import ConfigStore, default_store
    store = default_store()
    return store.override(validation_window_seconds=3600, rollback_window_seconds=3600)


@pytest.fixture
def notifier():
    from app.mitigation_safety.notifications.sink import InMemoryNotificationSink
    return InMemoryNotificationSink()


@pytest.fixture
def service_bundle(
    db, revert_registry, mock_ci, mock_telemetry, incidents_source,
    signoff_source, cfg, notifier,
):
    from app.mitigation_safety.audit.service import MitigationAuditLogger
    from app.mitigation_safety.guards.auto_revert import AutoRevertTrigger
    from app.mitigation_safety.guards.evaluator import GuardEvaluator
    from app.mitigation_safety.guards.rolling_window import RollingWindowStore
    from app.mitigation_safety.safemode.controller import SafeModeController
    from app.mitigation_safety.staging.promotion import (
        PromotionService, noop_apply_to_production,
    )
    from app.mitigation_safety.staging.revert import RevertService
    from app.mitigation_safety.staging.runners.code_runner import NoopCodeStagingRunner
    from app.mitigation_safety.staging.runners.config_runner import ConfigStagingRunner
    from app.mitigation_safety.staging.scope_isolation import ScopeIsolationVerifier
    from app.mitigation_safety.staging.service import StagingService
    from app.mitigation_safety.validation.checks import default_checks
    from app.mitigation_safety.validation.service import ValidationService

    audit = MitigationAuditLogger(db)
    safe_mode = SafeModeController(db, audit)
    runners = {"code": NoopCodeStagingRunner(), "config": ConfigStagingRunner()}
    revert_service = RevertService(
        db, audit, revert_registry=revert_registry, runners=runners
    )

    def _revert_callable(action_id, reason, actor):
        revert_service.revert(action_id=action_id, reason=reason, actor=actor)

    auto_revert = AutoRevertTrigger(revert_callable=_revert_callable)
    rolling = RollingWindowStore(db, min_samples=1)

    checks = default_checks(
        ci=mock_ci, telemetry=mock_telemetry,
        incidents=incidents_source, signoff=signoff_source,
    )

    def _on_failed(vid, reason):
        rolling.record(signal="validation_failed", category=_cat(db, vid))
        auto_revert.fire(
            action_id=_action(db, vid), reason=reason, signal="validation_failed"
        )

    def _on_expired(vid):
        rolling.record(signal="validation_failed", category=_cat(db, vid))
        auto_revert.fire(
            action_id=_action(db, vid), reason="window expired",
            signal="window_expired",
        )

    validation_svc = ValidationService(
        db, audit, checks=checks, cfg=cfg,
        on_failed=_on_failed, on_expired=_on_expired,
    )
    staging_svc = StagingService(
        db, audit, cfg=cfg, runners=runners,
        scope_verifier=ScopeIsolationVerifier(),
        revert_registry=revert_registry, safe_mode=safe_mode,
        validation_svc=validation_svc,
    )
    promotion_svc = PromotionService(
        db, audit, cfg=cfg, safe_mode=safe_mode, notifier=notifier,
        apply_to_production=noop_apply_to_production,
    )
    guard_eval = GuardEvaluator(
        db, audit, cfg=cfg, rolling=rolling, safe_mode=safe_mode,
        auto_revert=auto_revert, telemetry=mock_telemetry, notifier=notifier,
    )
    return {
        "db": db, "audit": audit, "safe_mode": safe_mode,
        "staging": staging_svc, "validation": validation_svc,
        "promotion": promotion_svc, "revert": revert_service,
        "guard": guard_eval, "rolling": rolling, "cfg": cfg,
        "notifier": notifier, "mock_ci": mock_ci,
        "mock_telemetry": mock_telemetry,
        "incidents_source": incidents_source,
        "signoff_source": signoff_source,
        "revert_registry": revert_registry,
        "auto_revert": auto_revert,
    }


def _cat(db, vid) -> str:
    vr = db.get(ValidationResult, str(vid))
    if vr is None:
        return "unknown"
    d = db.get(StagingDeployment, vr.deployment_id)
    if d is None:
        return "unknown"
    a = db.query(BotActionLog).filter(BotActionLog.action_id == d.action_id).one_or_none()
    return a.category if a else "unknown"


def _action(db, vid):
    vr = db.get(ValidationResult, str(vid))
    if vr is None:
        return str(uuid.uuid4())
    d = db.get(StagingDeployment, vr.deployment_id)
    if d is None:
        return str(uuid.uuid4())
    a = db.query(BotActionLog).filter(BotActionLog.action_id == d.action_id).one_or_none()
    return a.action_id if a else str(uuid.uuid4())


@pytest.fixture
def utcnow():
    return datetime.now(timezone.utc)


@pytest.fixture
def future_time(utcnow):
    return utcnow + timedelta(hours=1)


@pytest.fixture
def past_time(utcnow):
    return utcnow - timedelta(hours=1)
