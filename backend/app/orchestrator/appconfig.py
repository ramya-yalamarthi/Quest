"""
Externalised configuration loader ("don't hardcode").

Business rules and tunables live OUTSIDE the code:
  * structured rules (trusted domains) -> JSON files in backend/config/
  * scalar tunables (thresholds, calibration)    -> environment variables

Every getter takes a DEFAULT, so the system still runs if a file/var is missing
or malformed (it falls back to the baked-in default). Override the config dir
with the CONFIG_DIR env var.
"""

from __future__ import annotations

import json
import os

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONFIG_DIR = os.getenv("CONFIG_DIR") or os.path.join(_BACKEND, "config")


def load_json(name: str, default):
    """Load backend/config/<name>; return `default` if missing or invalid."""
    try:
        with open(os.path.join(_CONFIG_DIR, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, ""))
    except (TypeError, ValueError):
        return float(default)


def env_list(name: str, default: list) -> list:
    """Comma-separated env var -> list; `default` if unset."""
    v = os.getenv(name)
    if not v:
        return default
    return [x.strip() for x in v.split(",") if x.strip()]
