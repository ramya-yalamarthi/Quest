# Mitigation Safety — End-to-End Review Remediation

**Created:** 2026-06-17
**Workflow ID:** ms-review-remediation-2026-06-17
**Status:** In Progress
**Source:** Code-review report from `History/mitigation-safety-staged-rollout-2026-06-17.md` (Phase F10) + workflow `wf_8c8f3f52-c62`
**Total findings:** 48 (after adversarial verification) — 7 critical, 33 medium, ~4 nits

## Remediation Phases

### F11: Deploy + Bootstrap (#5, #6)
- **Status:** In Progress
- **Description:** Make a greenfield deploy actually possible.
- **Breakdown:**
  - Add a legacy-tables baseline Alembic revision so `alembic upgrade head` works on an empty DB
  - Update Dockerfile (or add new one) that installs `requirements.txt` and runs `app.main:app`
  - Add `ms_apscheduler_jobs` to Alembic so autogenerate doesn't propose dropping it (#24)

### F12: Critical safety holes (#1, #2, #3, #4, #7)
- **Status:** In Progress
- **Description:** Restore the three silently-dead invariants and close the auth-bypass.
- **Breakdown:**
  - Harden `ScopeIsolationVerifier` against NFKC, whitespace, alphanum suffix, soft-hyphen (#1)
  - Emit `signal='attempt'` at validation-window open + on every promotion (#2)
  - Worker `_build_runtime` uses `_pick_ci`/`_pick_telemetry` not mocks (#3)
  - Worker callbacks mirror `rolling.record(...)` like api/container (#4)
  - `require_human` rejects tokens with no identity claim (#7)

### F13: Service-layer concurrency + transaction hygiene (#8-#15, #23, #40)
- **Status:** Not Started
- **Description:** Stop committing inside services on the error path; lock for update; promote-by-vr.deployment_id; treat NULL rollback window as elapsed; bound telemetry by promoted_at.
- **Breakdown:**
  - Remove `db.commit()` from `stage()`/`promote()` exception handlers
  - Validate before mutating `revert_handle_ref`
  - `with_for_update()` on BotActionLog in stage/promote
  - PromotionService uses `vr.deployment_id`
  - `_rollback_promoted` treats NULL window as elapsed
  - `evaluate_post_promotion` bounds by `vr.promoted_at`
  - Guard threshold>0 short-circuit fixed
  - `ValidationNotPassed(validation_id=vr.validation_id)` (#40)

### F14: Input/output surface tightening (#17-#22, #27)
- **Status:** Not Started
- **Description:** SSRF / KQL injection / log injection / unbounded strings.
- **Breakdown:**
  - `max_length` on every Pydantic str
  - `q.component` validated against `^[A-Za-z0-9_.-]{1,64}$`
  - `GITHUB_API_BASE` + `NOTIFY_WEBHOOK_URL` host allowlist
  - Redact exception bodies in logs + `TelemetryResult.detail`
  - JWT_SECRET: refuse to boot if default + not in dev
  - `POST /mitigation/safe-mode` rejects unknown scopes

### F15: Fail-loud boot (#25, #26, #39)
- **Status:** Not Started
- **Description:** API refuses to serve (or system Safe Mode ON) when scheduler / immutability fail.
- **Breakdown:**
  - `apply_immutability` failure → enter system Safe Mode (and re-raise outside dev)
  - Scheduler build/start failure → enter system Safe Mode
  - Fix `_SCHEDULER` set-only-on-success ordering

### F16: Tests — fill the gaps (#28-#37)
- **Status:** Not Started
- **Description:** HTTP-level tests through real routers; concurrency tests; MS-19/MS-23 path tests; pydantic schema tests; deeper audit immutability test.
- **Breakdown:**
  - HTTP TestClient through `tickets_routes.py` + `safemode_routes.py`
  - `test_worker_jobs.py` invoking the three job entrypoints end-to-end
  - Concurrency race test (stage twice)
  - MS-19 hot-reload test
  - MS-23 unhandled-execution-error test
  - S1 audit-row metric assertion
  - S3 routed through `expiry_poller`

### F17: Nits + polish + scope check
- **Status:** Not Started
- **Breakdown:**
  - `open_window` audit uses `_aware()` for ISO serialization
  - Audit count assertion in `test_idempotent_re_enter`

### F18: Verify (final test sweep + cross-check)
- **Status:** Not Started
- **Description:** Re-run all 61+ tests. Re-run the verifier workflow against the patched code to confirm survivors == 0 or only deferred items.

## Execution Log
| Date | Phase | Action | Status |
|------|-------|--------|--------|
| 2026-06-17 | F11 | Alembic baseline + Dockerfile.app + ms_apscheduler_jobs table | ✓ |
| 2026-06-17 | F12 | Scope isolation hardened, MS-20 attempt signal wired, worker uses container.services(), require_human rejects anon | ✓ |
| 2026-06-17 | F13 | Service exception handlers no longer commit; with_for_update on stage+promote; promote by vr.deployment_id; null rollback window treated as elapsed; CLOSED returned not raised; telemetry windowed by vr.promoted_at; guard threshold<=0 disabled; ValidationNotPassed carries id | ✓ |
| 2026-06-17 | F14 | Pydantic max_length everywhere; KQL component regex; GITHUB_API_BASE allowlist; webhook URL safety + redacted logs; JWT_SECRET refuse-to-boot outside dev; POST /safe-mode unknown-scope 400 | ✓ |
| 2026-06-17 | F15 | apply_immutability + scheduler build/start/rearm failures all _force_system_safe_mode + re-raise outside dev; _SCHEDULER only set on full success | ✓ |
| 2026-06-17 | F16 | HTTP TestClient suite; test_worker_jobs invoking real entrypoints; MS-19 hot-reload; MS-23 unhandled-exec-error; raw-SQL audit no-mutation source-grep; concurrency stage-twice; S1 audit metric+value+reason; S3 routed through expiry_poller | ✓ |
| 2026-06-17 | F17 | Audit-row count assertion in test_idempotent_re_enter; open_window ISO uses _aware() | ✓ |
| 2026-06-17 | F18 | Adversarial re-verify (133 agents, 3-lens majority) — 43/44 fully fixed, 1 partial (#22 aud/iss); closed inline | ✓ |
| 2026-06-17 | F18 | Added aud+iss claims to create_access_token; decode_token enforces require_aud/require_iss + belt-and-braces equality check; test_jwt_claims covers presence/mismatch | ✓ |

**Final test count: 92 passing (was 61 + 31 new tests, all green).**

### Outstanding items (no follow-up needed unless requirements change)
- The deferred-list from the original plan (encrypted revert-handle payloads at rest; real `apply_to_production` runbook impls; dashboard `/mitigation/health` aggregation endpoint; full MSAL/Azure-AD bearer swap) — these need `.env` secrets / external integration work and were explicitly out-of-scope for this remediation pass.
- Integration test against real Postgres + Alembic upgrade head — recommended as a CI job (catches the FK to `tickets` baseline and the immutability trigger end-to-end); not added here because it requires a running database in CI.
