# Mitigation Safety & Staged Rollout

> No approved mitigation reaches production directly. Every action is **staged**,
> held in a **24-hour validation window**, **promoted only on PASS**, reversible
> in **one action**, with default-on **Safe Mode** that suspends autonomy.
> Fail-safe by default.

This module is the executable form of `SRS.md` at the repo root. Every
requirement ID (`MS-01`..`MS-26`) and acceptance scenario (`S1`..`S4`) is
implemented and tested — see the traceability table at the bottom.

---

## The 9 non-negotiable invariants (server-enforced)

| # | Invariant | Where it's enforced |
|---|---|---|
| 1 | No direct-to-prod — production effect ONLY via `Promote` after PASS | `staging/promotion.py::PromotionService.promote` (only call site of `apply_to_production`) |
| 2 | Never auto-promote on timeout — `Expired` → auto-revert | `validation/service.py::mark_expired`, `worker/jobs.py::expiry_poller` |
| 3 | Failed check → auto-revert | `validation/service.py::evaluate_now::_mark_failed` |
| 4 | No execution without a tested revert handle | `domain/transitions.py::assert_can_stage` + `staging/service.py::stage` |
| 5 | Safe Mode default-on, never self-clears | `safemode/boot.py::ensure_default_on`, `safemode/controller.py::exit` |
| 6 | Fail toward human/revert on every timeout/error/ambiguity | `validation/service.py` (per-check deadlines → FAIL), `_pick_ci`/`_pick_telemetry` mock fallback |
| 7 | Staging isolation | `staging/scope_isolation.py::ScopeIsolationVerifier` |
| 8 | Idempotent revert | `staging/revert.py::RevertService.revert` |
| 9 | Immutable audit | `db/grants.py::apply_immutability` (Postgres trigger + REVOKE) |

---

## State machine

```
DRAFTED → APPROVED | REJECTED
APPROVED → STAGED                          (eligible=true AND tested revert handle)
STAGED → VALIDATING | REVERTED
VALIDATING → PROMOTED | FAILED | EXPIRED   (PROMOTED needs PASS + not held + confirm)
FAILED → REVERTED                          (auto, no human path)
EXPIRED → REVERTED                         (auto)
PROMOTED → ROLLEDBACK | CLOSED             (ROLLEDBACK only within rollback window)
REJECTED / REVERTED / ROLLEDBACK / CLOSED  (terminal)
```

`domain/transitions.py::assert_legal` is the single chokepoint every state
write passes through.

---

## API (6 routes + 2 410 shims)

| Method | Path | Behavior |
|---|---|---|
| `POST` | `/tickets/{id}/mitigate/stage` | apply to staging branch/scope, open window. 409 on illegal transition / missing revert handle / scope-isolation. 423 if system Safe Mode held |
| `GET`  | `/tickets/{id}/mitigate/validation` | per-check status, elapsed, time-remaining |
| `POST` | `/tickets/{id}/mitigate/promote` | PASS only (409 else). 423 if Safe Mode active or confirm-to-promote and `confirm=false`. Opens rollback window |
| `POST` | `/tickets/{id}/mitigate/revert`  | idempotent — re-issue returns `idempotent=true` |
| `GET`  | `/mitigation/safe-mode` | system + categories snapshot |
| `POST` | `/mitigation/safe-mode` | enter/exit. Exit by non-human → 403 |
| `POST` | `/mitigate/execute`  | **410 Gone** — pointer to `stage` + `promote` |
| `POST` | `/mitigate/rollback` | **410 Gone** — pointer to `revert` |

All writes require `Depends(require_human(scopes=[...]))`. The `actor_id`
on every audit row is `human:<user_id>` so MS-22 is provable.

---

## Configuration (hot-reloadable, no code deploy — MS-19)

Set `MITIGATION_SAFETY_CONFIG_PATH=/path/to/cfg.json`. Example:

```json
{
  "validation_window_seconds": 86400,
  "rollback_window_seconds": 86400,
  "confirm_to_promote": {"_default": true, "capacity_quota": true},
  "validation_window_overrides": {"capacity_quota": 86400},
  "rollback_window_overrides": {"capacity_quota": 43200},
  "guards": {
    "validation_failure_rate": 0.20,
    "rollback_rate": 0.10,
    "decline_rate": 0.25,
    "rolling_window_seconds": 3600,
    "min_samples": 5,
    "telemetry_bounds": {
      "payments-api": {"error_rate": {"min": 0.0, "max": 0.05}}
    }
  },
  "safe_mode_default_on_start": true,
  "allow_listed_categories": ["capacity_quota"],
  "categories": ["capacity_quota", "software_defect"]
}
```

The store watches the file's mtime and reloads on change.

---

## Backends (real impls + fallbacks)

| Selector env | Values | Real impl env | Fallback |
|---|---|---|---|
| `MITIGATION_SAFETY_CI_BACKEND` | `github`, `mock` | `GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_WORKFLOW_FILE`, `GITHUB_CI_REF` (default `main`), `GITHUB_CI_TIMEOUT_SECONDS` (default 1800) | If env incomplete → MockCIRunner (Safe Mode stays ON) |
| `MITIGATION_SAFETY_TELEMETRY_BACKEND` | `azure`, `mock` | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_MONITOR_WORKSPACE_ID`, `AZURE_MONITOR_TIMEOUT_SECONDS` (default 30) | If env incomplete → MockTelemetrySource |

---

## Run locally

```bash
# 1. Postgres + Redis (already in compose):
docker compose up -d pgvector redis

# 2. install deps:
cd backend && pip install -r requirements.txt

# 3. apply migrations:
alembic upgrade head

# 4. start the API:
uvicorn app.main:app --reload

# 5. frontend (in a separate terminal):
cd frontend && npm install && npm run dev
# open http://localhost:5173

# 6. tests:
pytest tests/mitigation_safety -q
```

Tests run with SQLite + mocks and DO NOT require Postgres. The DB-level
append-only trigger is exercised in production via the Alembic migration;
in the test environment a SQLAlchemy `before_flush` listener emulates it
(see `tests/mitigation_safety/conftest.py`).

---

## MS-xx → code / test traceability map

| Req | Implemented in | Verified by |
|---|---|---|
| MS-01 explicit state machine | `domain/states.py`, `domain/transitions.py` | `test_domain_transitions.py` |
| MS-02 no direct-to-prod | `staging/promotion.py::PromotionService` (only `apply_to_production` site) | `test_promote_requires_pass.py`, `test_s3_window_expiry.py` |
| MS-03 type chosen at draft drives staging path | `staging/service.py`, `staging/runners/*` | `test_s2_backend_defect.py` (code), `test_s1_quota_happy_and_revert.py` (config) |
| MS-04 code → isolated staging branch + CI | `staging/runners/code_runner.py::branch_name`, `validation/ci/github_actions.py` | `test_s2_backend_defect.py` |
| MS-05 config → validation hold w/ revert handle first | `domain/transitions.py::assert_can_stage`, `staging/runners/config_runner.py` | `test_revert_handle_required.py`, `test_s1_quota_happy_and_revert.py` |
| MS-06 staging record w/ required fields | `db/models.py::StagingDeployment` (revert_handle NOT NULL) | enforced at DB level + `test_revert_handle_required.py` |
| MS-07 staging isolation | `staging/scope_isolation.py::ScopeIsolationVerifier` | `test_staging_scope_isolation.py` |
| MS-08 24h validation window, configurable | `validation/service.py::open_window` + `config.py::validation_window_for` | `test_validation_pass.py` |
| MS-09 inspectable checklist with per-check breakdown | `validation/checks/*` + `ValidationResult.checks` JSONB | `test_validation_pass.py`, `test_validation_fail_autorevert.py` |
| MS-10 expiry → auto-revert, never auto-promote | `validation/service.py::mark_expired`, `worker/jobs.py::expiry_poller` | `test_window_expiry_autorevert.py`, `test_s3_window_expiry.py` |
| MS-11 validation status queryable | `api/tickets_routes.py::get_validation` | covered by `test_validation_pass.py` (exercises `ValidationService.get`) |
| MS-12 confirm-to-promote per category | `domain/transitions.py::assert_can_promote` + `config.py::confirm_required_for` | `test_promote_requires_confirm.py` |
| MS-13 one-click revert (staged + promoted) | `api/tickets_routes.py::revert`, `staging/revert.py` | `test_revert_idempotent.py`, `test_s1_quota_happy_and_revert.py` |
| MS-14 tested rollback path required before execute | `staging/revert_handles.py`, `domain/transitions.py::assert_can_stage` | `test_revert_handle_required.py` |
| MS-15 post-promotion rollback window | `staging/promotion.py::promote` (sets `rollback_window_end`), `staging/revert.py::_rollback_promoted` | `test_revert_idempotent.py` |
| MS-16 guard-triggered auto-revert on telemetry breach | `guards/evaluator.py::evaluate_post_promotion` + `guards/auto_revert.py` | `test_s1_quota_happy_and_revert.py` (negative), `test_guard_autotrip.py` |
| MS-17 idempotent revert | `staging/revert.py::RevertService.revert` (terminal short-circuit) | `test_revert_idempotent.py` |
| MS-18 immutable audit | `db/grants.py::apply_immutability` + `audit/service.py` insert-only | `test_audit_immutability.py` |
| MS-19 system + per-category Safe Mode toggle | `safemode/controller.py::enter/exit`, `api/safemode_routes.py` | `test_safe_mode_human_exit.py` |
| MS-20 Safe Mode auto-enter on tripped guards | `guards/evaluator.py::evaluate` | `test_guard_autotrip.py`, `test_s4_safe_mode_autotrip.py` |
| MS-21 in-flight windows still need manual promote in Safe Mode | `staging/promotion.py::assert_can_promote` (Safe Mode hold) | `test_s4_safe_mode_autotrip.py` |
| MS-22 human-only Safe Mode exit | `safemode/controller.py::exit` (raises `SafeModeHumanRequired`) | `test_safe_mode_human_exit.py`, `test_s4_safe_mode_autotrip.py` |
| MS-23 default-on at start/restart & after unhandled error | `safemode/boot.py::ensure_default_on`, `safemode/controller.py::on_unhandled_execution_error` | `test_safe_mode_boot.py` |
| MS-24 append-only audit w/ single-query reconstruction | `audit/service.py`, `audit/reconstruct.py` | `test_audit_immutability.py` |
| MS-25 dashboard surfaces health metrics | `frontend/src/components/MitigationSafetyPanel.tsx` + `StateCounts`, `PerCheckStatus`, `TimeRemaining`, `RollbackRate`, `SafeModeBanner` | manual: `npm run dev` |
| MS-26 notify engineer + lead on FAIL / expiry / guard-rollback / Safe Mode entry | `notifications/sink.py` + emit sites in `validation/service.py`, `guards/evaluator.py`, `worker/jobs.py` | `test_guard_autotrip.py` asserts notifications emitted |
| **S1** quota happy + guard-revert | end-to-end | `test_s1_quota_happy_and_revert.py` |
| **S2** backend defect happy + negative | end-to-end | `test_s2_backend_defect.py` |
| **S3** window expiry, no production effect | end-to-end | `test_s3_window_expiry.py` |
| **S4** Safe Mode auto-trip + human-only exit | end-to-end | `test_s4_safe_mode_autotrip.py` |

---

## Deferred items (Should / Could not yet shipped)

These are explicitly named so they don't get lost:

1. **Encrypted revert-handle payloads at rest.** The `RevertHandleRegistry` is
   in-memory and stores a Python callable. Production needs a serialized,
   encrypted payload (KMS/Key Vault) so a revert procedure survives across
   restarts and isn't held in process memory.
2. **Real `apply_to_production` wiring.** `PromotionService` calls the
   pluggable `apply_to_production(action, deployment, validation)`; the
   default `noop_apply_to_production` only logs. The runbook owner per
   category supplies the concrete impl (PR merge, config promote, etc.).
3. **Dashboard endpoint feeding `MS-25` counts directly.** The frontend
   currently derives counts from the in-flight validation only; a future
   `GET /mitigation/health` endpoint should return aggregate state counts +
   pass/fail rate + mean time-in-validation + rollback rate from the DB.
4. **Azure AD bearer validation.** `api/deps.py::require_human` today wraps
   the existing JWT validator. The function signature is fixed; swap the
   internals for MSAL + JWKS when the AD app registration is in place.
5. **Test runs against real Postgres.** Unit tests use SQLite for speed and
   portability; an integration job that runs `alembic upgrade head` against
   the compose Postgres and re-runs the same test suite is the next step.

---

## Auth scopes (required claims in the bearer token)

| Endpoint | Scope |
|---|---|
| `POST /tickets/{id}/mitigate/stage` | `mitigation:write` |
| `GET /tickets/{id}/mitigate/validation` | `mitigation:read` |
| `POST /tickets/{id}/mitigate/promote` | `mitigation:promote` |
| `POST /tickets/{id}/mitigate/revert` | `mitigation:revert` |
| `GET /mitigation/safe-mode` | `mitigation:read` |
| `POST /mitigation/safe-mode` | `mitigation:safemode` |

Missing scope → `403 {error: "missing scopes", missing: [...]}`.
