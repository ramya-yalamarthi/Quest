"""AutoRevertTrigger — wires guard breaches to validation auto-revert.

Used by:
- ValidationService (via its on_failed/on_expired callbacks) to drive
  Validating -> Failed/Expired -> Reverted (invariants 2 & 3).
- GuardEvaluator (MS-16) when a post-promotion telemetry breach is
  detected during the rollback window.

The trigger calls `RevertService.revert(action_id, reason)` with
`actor='guard:<signal>'` so the audit row records the system origin.
"""

from __future__ import annotations

import logging
import uuid
from typing import Callable

logger = logging.getLogger("mitigation_safety.guards.auto_revert")


class AutoRevertTrigger:
    def __init__(
        self,
        *,
        revert_callable: Callable[..., None],
    ) -> None:
        """revert_callable signature:
            (action_id: uuid, reason: str, actor: str) -> None
        """
        self._revert = revert_callable

    def fire(
        self,
        *,
        action_id: uuid.UUID | str,
        reason: str,
        signal: str = "auto",
    ) -> None:
        actor = f"guard:{signal}"
        logger.warning(
            "auto-revert action_id=%s actor=%s reason=%s",
            action_id,
            actor,
            reason,
        )
        try:
            self._revert(action_id=action_id, reason=reason, actor=actor)
        except Exception as exc:
            # The revert call MUST be idempotent and never raise to the
            # caller; log here so a failure surfaces without crashing the
            # worker/evaluator.
            logger.exception("auto-revert call failed: %s", exc)
