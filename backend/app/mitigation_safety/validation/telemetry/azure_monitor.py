"""Real TelemetrySource backed by Azure Monitor Logs (Kusto / KQL).

Env vars:
  AZURE_TENANT_ID
  AZURE_CLIENT_ID
  AZURE_CLIENT_SECRET
  AZURE_MONITOR_WORKSPACE_ID
  AZURE_MONITOR_TIMEOUT_SECONDS (default 30)

Sends one KQL query per (component, metric) configured in the run-time guard
bounds. If the workspace returns no rows, the result is marked insufficient
so the validation check fails toward 'require human' (invariant 6).
"""

from __future__ import annotations

import logging
import os
import re
from datetime import timezone

try:
    from azure.identity import ClientSecretCredential  # type: ignore
    from azure.monitor.query import LogsQueryClient, LogsQueryStatus  # type: ignore
except ImportError:  # pragma: no cover
    ClientSecretCredential = None  # type: ignore
    LogsQueryClient = None  # type: ignore
    LogsQueryStatus = None  # type: ignore

from app.mitigation_safety.validation.telemetry.interface import (
    TelemetryQuery,
    TelemetryResult,
)

logger = logging.getLogger("mitigation_safety.telemetry.azure")


# #18: `component` is interpolated into a KQL query. Restrict to a strict
# allowlist of characters so a malicious value can't terminate a string
# literal and inject arbitrary Kusto. The regex matches the same shape
# operators use elsewhere in the module (lowercase identifiers, digits,
# hyphens, underscores, dots).
_COMPONENT_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")


# Default KQL: AppMetrics for a given component over [window_start, window_end].
# Operators can override per deployment via env or future config layer.
DEFAULT_KQL = """
AppMetrics
| where TimeGenerated between (datetime({start}) .. datetime({end}))
| where AppRoleName == '{component}' or Name has '{component}'
| summarize value=avg(Sum) by Name
"""


class AzureMonitorTelemetrySource:
    def __init__(
        self,
        *,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        workspace_id: str | None = None,
        timeout_s: int | None = None,
    ) -> None:
        self.workspace_id = workspace_id or os.getenv("AZURE_MONITOR_WORKSPACE_ID") or ""
        self.timeout_s = int(timeout_s or os.getenv("AZURE_MONITOR_TIMEOUT_SECONDS") or 30)
        if ClientSecretCredential is None or LogsQueryClient is None:
            self._client = None
            return
        cred = ClientSecretCredential(
            tenant_id=tenant_id or os.getenv("AZURE_TENANT_ID") or "",
            client_id=client_id or os.getenv("AZURE_CLIENT_ID") or "",
            client_secret=client_secret or os.getenv("AZURE_CLIENT_SECRET") or "",
        )
        self._client = LogsQueryClient(cred)

    def query(self, q: TelemetryQuery) -> TelemetryResult:
        if self._client is None or not self.workspace_id:
            return TelemetryResult(
                component=q.component,
                metrics={},
                insufficient=True,
                detail="azure monitor client not configured",
            )
        # #18: validate `component` against a strict allowlist BEFORE
        # interpolation. Anything outside `[A-Za-z0-9_.-]{1,64}` is rejected
        # — it cannot terminate the KQL string literal, but we still refuse
        # so the failure mode is explicit rather than "query returns nothing".
        if not _COMPONENT_RE.match(q.component or ""):
            return TelemetryResult(
                component=q.component,
                metrics={},
                insufficient=True,
                detail="invalid component name",
            )
        kql = DEFAULT_KQL.format(
            start=q.window_start.astimezone(timezone.utc).isoformat(),
            end=q.window_end.astimezone(timezone.utc).isoformat(),
            component=q.component,
        )
        try:
            resp = self._client.query_workspace(
                workspace_id=self.workspace_id,
                query=kql,
                timespan=None,  # explicit datetimes in KQL
                server_timeout=self.timeout_s,
            )
        except Exception as exc:
            # #21: don't echo the raw exception (it can contain tenant /
            # workspace / request-id details). Log the type only; the user-
            # facing detail is generic.
            logger.warning("AzureMonitor query failed: %s", type(exc).__name__)
            return TelemetryResult(
                component=q.component,
                metrics={},
                insufficient=True,
                detail="query error",
            )
        if LogsQueryStatus is not None and resp.status != LogsQueryStatus.SUCCESS:
            return TelemetryResult(
                component=q.component,
                metrics={},
                insufficient=True,
                detail="non-success status",
            )
        metrics: dict[str, float] = {}
        for table in getattr(resp, "tables", []) or []:
            for row in table.rows:
                # row order = columns: name, value
                if len(row) >= 2:
                    metrics[str(row[0])] = float(row[1])
        if not metrics:
            return TelemetryResult(
                component=q.component,
                metrics={},
                insufficient=True,
                detail="no rows returned",
            )
        return TelemetryResult(component=q.component, metrics=metrics)
