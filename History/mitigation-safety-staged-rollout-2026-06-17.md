# Sentinel — Mitigation Safety & Staged Rollout

**Created:** 2026-06-17
**Workflow ID:** mitigation-safety-msrf-2026-06-17
**Status:** Active (Implementation complete, Verification pending)
**Source Spec:** `/Users/isaachernandez/Documents/GitHub/Quest/SRS.md`
**Plan Doc:** `/Users/isaachernandez/.claude/plans/sequential-spinning-yeti.md`
**Module README:** `backend/app/mitigation_safety/README.md`

## Plan Overview

Implement the Mitigation Safety & Staged Rollout module so no approved
mitigation reaches production directly: every action is staged, held in a
24-hour validation window, promoted only on PASS, reversible in one action,
with default-on Safe Mode. Server-enforced fail-safe defaults, append-only
audit, durable validation worker, and a small React panel for ops.

## Phases

### F1: Domain + Data Model + Alembic migration
- **Status:** Completed
- **Description:** State machine, transition guards, 6 SQLAlchemy models, Alembic baseline + revision creating ms_* tables, indices, immutability trigger + REVOKE grants.
- **Breakdown:**
  - MitigationState enum + LEGAL_TRANSITIONS table (MS-05)
  - assert_legal / assert_can_stage / assert_can_promote (MS-08, MS-10, invariant 4)
  - ms_staging_deployment / ms_validation_result / ms_safe_mode_state / ms_bot_action_log / ms_audit_log / ms_guard_event
  - Alembic env.py, script template, 20260617_0001 revision
  - apply_immutability() trigger + REVOKE (MS-18, invariant 9)

### F2: Audit + Safe Mode + Configuration
- **Status:** Completed
- **Description:** Append-only audit logger, by_action/by_ticket reconstructors, Safe Mode controller with human-only exit, boot-time default-ON, hot-reloadable config.
- **Breakdown:**
  - MitigationAuditLogger (insert-only)
  - by_action_id / by_ticket_id (single-query reconstruction)
  - SafeModeController.enter / exit / is_held / snapshot (MS-22)
  - ensure_default_on (MS-15, MS-23)
  - ConfigStore w/ mtime-based hot reload (MS-19)

### F3: Validation engine + Checks + CI/Telemetry backends
- **Status:** Completed
- **Description:** ValidationService.open_window / evaluate_now / mark_expired; five MS-09 checks (a–e); CIRunner + TelemetrySource protocols with Mock impls + real GitHubActionsCIRunner + AzureMonitorTelemetrySource.
- **Breakdown:**
  - Check protocol + CheckResult (deadline-bounded run)
  - GeneratedTestsCheck, RegressionSuiteCheck, TelemetryBoundsCheck, CorrelatedIncidentsCheck, HumanSignoffCheck
  - MockCIRunner, GitHubActionsCIRunner (workflow_dispatch + poll)
  - MockTelemetrySource, AzureMonitorTelemetrySource (KQL via azure-monitor-query)
  - ValidationService with auto-revert callbacks

### F4: Staging + Promotion + Revert services
- **Status:** Completed
- **Description:** StagingService (scope isolation + revert handle gate + Approved→Staged→Validating); PromotionService (single production-effect call site); RevertService (idempotent).
- **Breakdown:**
  - ScopeIsolationVerifier (regex prod-pattern blocklist, MS-11, invariant 7)
  - RevertHandleRegistry.has_tested / execute
  - CodeStagingRunner + NoopCodeStagingRunner + ConfigStagingRunner
  - StagingService.stage()
  - PromotionService.promote() — only apply_to_production caller
  - RevertService.revert() — Staged→Reverted vs Promoted→RolledBack, idempotent terminal short-circuit

### F5: Guards + Notifications + Durable Worker
- **Status:** Completed
- **Description:** Rolling-window guard evaluator backed by ms_guard_event, AutoRevertTrigger, notification sink, APScheduler-based durable worker with on_startup_rearm.
- **Breakdown:**
  - RollingWindowStore.record / count / rate
  - GuardEvaluator.evaluate (rolling rates) + evaluate_post_promotion (telemetry breach)
  - AutoRevertTrigger.fire
  - NotificationSink (Logging / Webhook / InMemory)
  - APScheduler factory w/ SQLAlchemyJobStore
  - window_evaluator / expiry_poller / guard_sweeper jobs
  - on_startup_rearm: re-arms PENDING windows on restart, fires past-due expiry immediately

### F6: API + require_human + 410 shims + main.py wiring
- **Status:** Completed
- **Description:** Six FastAPI routes (stage, validation, promote, revert, get/post safe-mode), require_human dep, two 410 Gone shims, container.services() factory, startup/shutdown hooks.
- **Breakdown:**
  - api/schemas.py (Pydantic models)
  - api/deps.py: require_human(scopes=[...]) returning HumanActor with `human:<id>` prefix
  - api/container.py: services(db) factory; backend selectors via env
  - tickets_routes.py (5 routes) + safemode_routes.py (2 routes) + shim_routes.py (2 x 410)
  - Wired into backend/app/main.py: include_router + startup/shutdown event handlers

### F7: Tests (unit + S1-S4 scenarios)
- **Status:** Completed
- **Description:** 60 pytest tests under tests/mitigation_safety/ covering every invariant and scenario.
- **Breakdown:**
  - conftest.py with isolated SQLite schema + UUID adapter + immutability listener
  - 16 unit tests (domain transitions, revert handle gate, scope isolation, audit immutability, Safe Mode boot, Safe Mode human exit, validation pass/fail/expiry, promote 409/423, revert idempotent, guard auto-trip, worker restart, 410 shims, require_human)
  - S1: quota happy path + guard-revert negative (MS-16)
  - S2: backend defect happy + CI-fail negative
  - S3: window expiry, no production effect
  - S4: Safe Mode auto-trip, manual promote required, human-only exit
  - All 60 passing locally

### F8: Frontend MitigationSafetyPanel
- **Status:** Completed
- **Description:** Vite + React + TS app with state counts, per-check status, time-remaining bar, rollback rate card, Safe Mode banner + toggle.
- **Breakdown:**
  - package.json / vite.config.ts / tsconfig.json / index.html / .env.example
  - main.tsx + App.tsx
  - auth/token.ts (MSAL-shaped seam, dev: localStorage JWT)
  - api/mitigation.ts (typed clients for all 6 routes)
  - hooks/useValidation.ts (polling) + useSafeMode.ts (polling)
  - components: MitigationSafetyPanel + StateCounts + PerCheckStatus + TimeRemaining + RollbackRate + SafeModeBanner + SafeModeToggle (with confirm prompt)

### F9: README + MS-xx → code/test traceability map
- **Status:** Completed
- **Description:** Module README at backend/app/mitigation_safety/README.md with invariants, state machine, API matrix, config keys, run instructions, full MS-01..MS-26 + S1..S4 traceability table, deferred items, auth scope matrix.

### F10: Verification sweep
- **Status:** Completed
- **Description:** Independent verifier walked the 9 invariants + state machine + API matrix + test coverage. Result: all 9 invariants PASS, state machine matches SRS §2 (with one justified addition `STAGED → REVERTED` needed for the API revert path).

**Issues found and fixed:**

1. **HIGH** — `RevertResponse.state` Literal included `"CLOSED"` but the only path that reaches CLOSED (`_rollback_promoted` when rollback window has elapsed) raises `IllegalTransition` (→ 409) before constructing the response, so `"CLOSED"` was dead in the union. Tightened to `Literal["REVERTED","ROLLEDBACK"]`. *(File: `backend/app/mitigation_safety/api/schemas.py`.)*
2. **MEDIUM** — Three different naive-vs-aware datetime coercion sites (`validation/service.py`, `staging/revert.py`, `worker/boot.py`). Consolidated into a shared `aware_utc()` helper in `domain/ids.py`; all callers now use it.
3. **LOW** — No edge-case test for rollback-window-elapsed revert. Added `tests/mitigation_safety/test_rollback_window_elapsed.py`: asserts revert raises `IllegalTransition`, the registered revert handle is NOT invoked, action transitions to `CLOSED`.

**Issues acknowledged but not fixed (defensible / deferred):**

- `db.commit()` inside service methods on the `on_unhandled_execution_error → Safe Mode` path. The Safe Mode entry must persist even when the caller is about to rollback its own transaction (otherwise an exec error would auto-undo the Safe Mode trip — invariant 5 violation). Defensible.
- Concurrent re-stage race / concurrent auto-revert vs human revert: not yet covered by tests. Documented as deferred; in practice the per-action state read-then-write under `db.flush()` plus the unique PK prevents the worst outcomes, but a proper integration test against Postgres is the right way to verify this and is on the deferred list.
- Broad `except Exception` in `validation/service.py` on_failed/on_expired callbacks: intentional — invariant 6 says fail toward audit + log, not propagate; the wrapping caller commits the audit row.

**Final test count: 61 passing** (60 from the original plan + 1 new edge-case test).

### Verification Log
| Date | Phase | Action | Status |
|------|-------|--------|--------|
| 2026-06-17 | F10 | Independent verification sweep run | ✓ |
| 2026-06-17 | F10 | RevertResponse Literal narrowed | ✓ |
| 2026-06-17 | F10 | Datetime coercion centralized in domain/ids.py | ✓ |
| 2026-06-17 | F10 | test_rollback_window_elapsed.py added | ✓ |
| 2026-06-17 | F10 | Full suite re-run: 61 passing | ✓ |

## Execution Log
| Date | Phase | Action | Status |
|------|-------|--------|--------|
| 2026-06-17 | F1 | Domain + data model + Alembic migration | ✓ |
| 2026-06-17 | F2 | Audit + Safe Mode + Config | ✓ |
| 2026-06-17 | F3 | Validation engine + checks + CI/telemetry backends | ✓ |
| 2026-06-17 | F4 | Staging + Promotion + Revert | ✓ |
| 2026-06-17 | F5 | Guards + Notifications + Durable Worker | ✓ |
| 2026-06-17 | F6 | API + require_human + 410 shims + main.py wiring | ✓ |
| 2026-06-17 | F7 | Tests (60 passing) | ✓ |
| 2026-06-17 | F8 | Frontend MitigationSafetyPanel | ✓ |
| 2026-06-17 | F9 | README + traceability map | ✓ |
| 2026-06-17 | F10 | Verification sweep | pending |
