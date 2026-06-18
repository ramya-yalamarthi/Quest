"""MS-15: Safe Mode is the default posture at start/restart.

`ensure_default_on(db, cfg)` is idempotent and never overwrites an existing
operator-set state.
"""

import pytest

from app.mitigation_safety.config import default_store
from app.mitigation_safety.safemode.boot import ensure_default_on
from app.mitigation_safety.safemode.controller import (
    SYSTEM_SCOPE,
    SafeModeController,
    category_scope,
)
from app.mitigation_safety.audit.service import MitigationAuditLogger


def test_boot_turns_safe_mode_on_for_system_and_each_category(db):
    cfg = default_store().override(
        categories=("capacity_quota", "software_defect"),
        safe_mode_default_on_start=True,
    )
    ensure_default_on(db, cfg=cfg)

    ctrl = SafeModeController(db, MitigationAuditLogger(db))
    assert ctrl.is_active(SYSTEM_SCOPE)
    for cat in cfg.categories:
        assert ctrl.is_active(category_scope(cat))


def test_boot_does_not_overwrite_existing_state(db):
    cfg = default_store().override(categories=("capacity_quota",))
    ensure_default_on(db, cfg=cfg)

    ctrl = SafeModeController(db, MitigationAuditLogger(db))
    entry_before = ctrl.get(SYSTEM_SCOPE)
    assert entry_before.entered_by == "guard:boot"

    # Second invocation must not produce a second row.
    ensure_default_on(db, cfg=cfg)
    entry_after = ctrl.get(SYSTEM_SCOPE)
    assert entry_after.entered_at == entry_before.entered_at


def test_boot_respects_disabled_config(db):
    cfg = default_store().override(safe_mode_default_on_start=False)
    ensure_default_on(db, cfg=cfg)

    ctrl = SafeModeController(db, MitigationAuditLogger(db))
    assert not ctrl.is_active(SYSTEM_SCOPE)
