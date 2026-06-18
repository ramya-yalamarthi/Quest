"""MS-19: ConfigStore reloads from file mtime, without code deploy (#34)."""

import json
import os
import time

from app.mitigation_safety.config import ConfigStore


def test_config_reloads_on_mtime_change(tmp_path):
    cfg_path = tmp_path / "ms.json"
    cfg_path.write_text(
        json.dumps({"validation_window_seconds": 60, "rollback_window_seconds": 60})
    )

    store = ConfigStore(path=str(cfg_path))
    assert store.get().validation_window_seconds == 60

    # Bump mtime explicitly so any same-second-resolution filesystem still
    # registers a change (HFS+ has 1s resolution on macOS).
    time.sleep(1.1)
    cfg_path.write_text(
        json.dumps(
            {"validation_window_seconds": 120, "rollback_window_seconds": 60}
        )
    )
    os.utime(cfg_path, None)

    snap = store.get()
    assert snap.validation_window_seconds == 120


def test_config_override_for_tests():
    """ConfigStore.override is the test escape-hatch documented in the README."""
    store = ConfigStore()
    snap = store.override(validation_window_seconds=999)
    assert snap.validation_window_seconds == 999
    # And the next get() returns the overridden value.
    assert store.get().validation_window_seconds == 999
