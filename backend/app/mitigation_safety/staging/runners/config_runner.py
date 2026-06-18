"""Config staging runner — pluggable applier for config/infrastructure mitigations.

For MVP it is a pass-through: it records the target scope and artifacts_ref
on the StagingDeployment row and trusts the runbook owner to have wired a
non-production scope OR a validation hold backed by a tested revert handle
(MS-05).
"""

from __future__ import annotations

import logging

from app.mitigation_safety.staging.runners.base import StagingRunnerResult

logger = logging.getLogger("mitigation_safety.staging.config")


class ConfigStagingRunner:
    type = "config"

    def apply(
        self,
        *,
        action_id: str,
        ticket_id: str | None,
        target: str,
        artifacts_ref: str,
        expected_outcome: dict,
    ) -> StagingRunnerResult:
        logger.info(
            "config staging apply scope=%s artifacts=%s", target, artifacts_ref
        )
        return StagingRunnerResult(
            target=target,
            external_ref=artifacts_ref,
            detail=f"config validation hold on scope {target}",
        )

    def discard(self, *, target: str) -> None:
        logger.info("config staging discard scope=%s", target)
        return
