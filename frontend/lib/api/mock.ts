/**
 * In-memory mock adapter.
 *
 * Drives the entire dashboard without a backend. Simulates:
 *  - one action progressing Approved → Staged → Validating with a ticking window
 *  - one action that fails a check and auto-reverts
 *  - one window that expires
 *  - one guard trip that enters Safe Mode for a category
 *
 * No localStorage / sessionStorage — all state lives in module-level closures
 * so a hot-reload resets cleanly. The simulated event emitter pushes RTEvent
 * objects through a Set of subscribers; the same Set powers `subscribe()`.
 */

import type {
  Api,
  AuditRow,
  CheckResult,
  GuardStatus,
  KpiSnapshot,
  ListActionsParams,
  ListAuditParams,
  MitigationAction,
  MitigationState,
  PromoteBody,
  RTEvent,
  RevertBody,
  SafeModeEntry,
  SafeModeView,
  SettingsPayload,
  StageBody,
  TelemetrySeries,
  Validation,
} from "./types";
import { CHECK_ORDER } from "./types";

// ---- Helpers ----------------------------------------------------------------
function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  // Fallback for non-crypto environments (tests).
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

const nowIso = () => new Date().toISOString();

// ---- State store ------------------------------------------------------------
interface Store {
  actions: Map<string, MitigationAction>;
  validations: Map<string, Validation>;
  audit: AuditRow[];
  safe: SafeModeView;
  settings: SettingsPayload;
  guardCounters: Map<string, { attempts: number; failures: number; rollbacks: number; declines: number }>;
  telemetry: Map<string, TelemetrySeries>;
}

const store: Store = {
  actions: new Map(),
  validations: new Map(),
  audit: [],
  safe: {
    system: {
      scope: "system",
      active: false,
      entered_at: null,
      entered_by: null,
      exited_at: null,
      exited_by: null,
      reason: null,
    },
    categories: {},
  },
  settings: {
    validation_window_seconds: 86_400,
    rollback_window_seconds: 86_400,
    confirm_to_promote: { _default: true, capacity_quota: true, software_defect: true },
    validation_window_overrides: {},
    rollback_window_overrides: {},
    guards: {
      validation_failure_rate: 0.2,
      rollback_rate: 0.1,
      decline_rate: 0.25,
      rolling_window_seconds: 3600,
      min_samples: 5,
      telemetry_bounds: {
        "payments-api": { error_rate: { min: 0, max: 0.05 } },
        "payments-quota": { error_rate: { min: 0, max: 0.05 } },
      },
    },
    categories: ["capacity_quota", "software_defect"],
    allow_listed_categories: ["capacity_quota"],
  },
  guardCounters: new Map(),
  telemetry: new Map(),
};

// Seed Safe Mode default-on per the backend's MS-15 contract.
function seedSafeModeOn() {
  for (const cat of store.settings.categories) {
    const scope = `category:${cat}`;
    if (!store.safe.categories[scope]) {
      store.safe.categories[scope] = {
        scope,
        active: true,
        entered_at: nowIso(),
        entered_by: "guard:boot",
        exited_at: null,
        exited_by: null,
        reason: "default-on at start (MS-23)",
      };
    }
  }
  store.safe.system = {
    scope: "system",
    active: true,
    entered_at: nowIso(),
    entered_by: "guard:boot",
    exited_at: null,
    exited_by: null,
    reason: "default-on at start (MS-23)",
  };
}

// ---- Subscribers ------------------------------------------------------------
const subscribers = new Set<(e: RTEvent) => void>();
function emit(e: RTEvent) {
  for (const fn of subscribers) {
    try { fn(e); } catch { /* never let a bad subscriber break the simulator */ }
  }
}

// ---- Audit helper -----------------------------------------------------------
function audit(row: Omit<AuditRow, "audit_id" | "ts">) {
  store.audit.unshift({
    audit_id: uuid(),
    ts: nowIso(),
    ...row,
  });
  // Keep audit unbounded but capped at 10k for browser memory.
  if (store.audit.length > 10_000) store.audit.length = 10_000;
}

// ---- Seed actions -----------------------------------------------------------
function makeAction(p: Partial<MitigationAction>): MitigationAction {
  const action_id = p.action_id ?? uuid();
  const ticket_id = p.ticket_id ?? uuid();
  const created = p.created_at ?? new Date(Date.now() - Math.random() * 3600_000 * 4).toISOString();
  return {
    action_id,
    ticket_id,
    category: p.category ?? "capacity_quota",
    type: p.type ?? "config",
    target: p.target ?? "staging-quota-eu",
    artifacts_ref: p.artifacts_ref ?? "quota:eu+200",
    state: p.state ?? "DRAFTED",
    created_at: created,
    actor: p.actor ?? "human:operator-1",
    eligible: p.eligible ?? true,
    revert_handle_ref: p.revert_handle_ref ?? "rh-quota-restart",
    validation_id: p.validation_id ?? null,
    rollback_window_end: p.rollback_window_end ?? null,
    state_history: p.state_history ?? [
      { from: null, to: "DRAFTED", actor: p.actor ?? "system", timestamp: created },
    ],
    expected_outcome: p.expected_outcome ?? { component: "payments-quota" },
  };
}

function transition(a: MitigationAction, to: MitigationState, actor: string, detail?: string) {
  const from = a.state;
  a.state = to;
  a.state_history = [
    ...a.state_history,
    { from, to, actor, timestamp: nowIso(), detail: detail ?? null },
  ];
  audit({
    action_id: a.action_id,
    ticket_id: a.ticket_id,
    actor,
    transition_type: "state",
    from_state: from,
    to_state: to,
    detail: { reason: detail ?? null },
  });
  emit({
    type: "state_transition",
    action_id: a.action_id,
    ticket_id: a.ticket_id,
    from,
    to,
    actor,
    ts: nowIso(),
  });
}

function openValidation(a: MitigationAction, windowSeconds: number): Validation {
  const start = new Date();
  const end = new Date(start.getTime() + windowSeconds * 1000);
  const validation_id = uuid();
  const checks: CheckResult[] = CHECK_ORDER.filter((name) => {
    // generated_tests applies to code-type only.
    if (name === "generated_tests" && a.type !== "code") return false;
    // human_signoff only when the category requires it (capacity_quota does in MVP).
    if (name === "human_signoff" && a.category !== "capacity_quota") return false;
    return true;
  }).map((name) => ({
    name,
    status: "PENDING",
    detail: null,
    evaluated_at: null,
  }));
  const vr: Validation = {
    validation_id,
    overall_status: "PENDING",
    checks,
    elapsed_seconds: 0,
    time_remaining_seconds: windowSeconds,
    window_start: start.toISOString(),
    window_end: end.toISOString(),
  };
  store.validations.set(validation_id, vr);
  a.validation_id = validation_id;
  return vr;
}

function emitValidationUpdate(a: MitigationAction, vr: Validation) {
  emit({
    type: "validation_update",
    validation_id: vr.validation_id,
    action_id: a.action_id,
    overall_status: vr.overall_status,
    checks: vr.checks,
    time_remaining_seconds: vr.time_remaining_seconds,
    ts: nowIso(),
  });
}

function bumpCounter(category: string, key: "attempts" | "failures" | "rollbacks" | "declines") {
  let row = store.guardCounters.get(category);
  if (!row) {
    row = { attempts: 0, failures: 0, rollbacks: 0, declines: 0 };
    store.guardCounters.set(category, row);
  }
  row[key]++;
}

// ---- Seed scenario ----------------------------------------------------------
function seedScenario() {
  // Action A — quota happy path; window ticks down.
  const A = makeAction({
    category: "capacity_quota",
    type: "config",
    target: "staging-quota-eu",
    state: "APPROVED",
    actor: "human:eng-42",
  });
  transition(A, "STAGED", "human:eng-42", "applied to staging scope");
  const aVr = openValidation(A, 86_400); // 24h
  // Pre-evolve so it's an interesting Validating: time_remaining = 21h12m
  aVr.elapsed_seconds = (24 * 3600) - (21 * 3600 + 12 * 60);
  aVr.time_remaining_seconds = 21 * 3600 + 12 * 60;
  // a few checks already pass
  aVr.checks = aVr.checks.map((c) =>
    c.name === "regression_suite" || c.name === "telemetry_bounds" || c.name === "correlated_incidents"
      ? { ...c, status: "PASS", evaluated_at: nowIso(), detail: "ok" }
      : c
  );
  transition(A, "VALIDATING", "system", `validation_id=${aVr.validation_id}`);
  bumpCounter(A.category, "attempts");
  store.actions.set(A.action_id, A);

  // Action B — code defect; PASS — awaiting confirm-to-promote
  const B = makeAction({
    category: "software_defect",
    type: "code",
    target: "sentinel/abc/fix-123",
    artifacts_ref: "diff:fix#123",
    state: "APPROVED",
    actor: "human:eng-17",
    expected_outcome: { component: "payments-api" },
  });
  transition(B, "STAGED", "human:eng-17", "branch pushed; CI green");
  const bVr = openValidation(B, 86_400);
  bVr.elapsed_seconds = 23 * 3600 + 18 * 60;
  bVr.time_remaining_seconds = 42 * 60;
  bVr.checks = bVr.checks.map((c) => ({ ...c, status: "PASS", evaluated_at: nowIso(), detail: "ok" }));
  bVr.overall_status = "PASS";
  transition(B, "VALIDATING", "system");
  bumpCounter(B.category, "attempts");
  store.actions.set(B.action_id, B);

  // Action C — already promoted; in rollback window
  const C = makeAction({
    category: "capacity_quota",
    type: "config",
    target: "staging-quota-apac",
    state: "APPROVED",
    actor: "human:eng-7",
  });
  transition(C, "STAGED", "human:eng-7");
  const cVr = openValidation(C, 86_400);
  cVr.checks = cVr.checks.map((c) => ({ ...c, status: "PASS", evaluated_at: nowIso() }));
  cVr.overall_status = "PASS";
  transition(C, "VALIDATING", "system");
  transition(C, "PROMOTED", "human:eng-7", "engineer confirmed");
  bumpCounter(C.category, "attempts");
  C.rollback_window_end = new Date(Date.now() + 4 * 3600 * 1000).toISOString(); // 4h remaining
  store.actions.set(C.action_id, C);

  // Action D — failed CI → auto-reverted (historic; for the table)
  const D = makeAction({
    category: "software_defect",
    type: "code",
    target: "sentinel/xyz/fail-99",
    state: "APPROVED",
    actor: "human:eng-22",
  });
  transition(D, "STAGED", "human:eng-22");
  const dVr = openValidation(D, 86_400);
  dVr.checks = dVr.checks.map((c) =>
    c.name === "generated_tests"
      ? { ...c, status: "FAIL", evaluated_at: nowIso(), detail: "1 test failed in CI" }
      : { ...c, status: "PASS", evaluated_at: nowIso() }
  );
  dVr.overall_status = "FAIL";
  transition(D, "VALIDATING", "system");
  transition(D, "FAILED", "system", "generated_tests failed");
  transition(D, "REVERTED", "system", "auto-revert from staging");
  bumpCounter(D.category, "attempts");
  bumpCounter(D.category, "failures");
  store.actions.set(D.action_id, D);

  // Action E — expired (historic)
  const E = makeAction({
    category: "capacity_quota",
    type: "config",
    target: "staging-quota-na",
    state: "APPROVED",
    actor: "human:eng-3",
  });
  transition(E, "STAGED", "human:eng-3");
  const eVr = openValidation(E, 86_400);
  eVr.checks = eVr.checks.map((c) => ({ ...c, status: "PENDING", detail: "no telemetry" }));
  eVr.overall_status = "EXPIRED";
  transition(E, "VALIDATING", "system");
  transition(E, "EXPIRED", "system", "telemetry insufficient");
  transition(E, "REVERTED", "system", "auto-revert from staging");
  bumpCounter(E.category, "attempts");
  bumpCounter(E.category, "failures");
  store.actions.set(E.action_id, E);

  // Seed telemetry — one component, one minute granularity, 1h history
  const points = [];
  for (let i = 60; i >= 0; i--) {
    const ts = new Date(Date.now() - i * 60_000).toISOString();
    points.push({
      ts,
      metric: "error_rate",
      // Mostly nominal with a brief excursion near minute -20.
      value: i >= 17 && i <= 23 ? 0.03 + Math.random() * 0.02 : 0.005 + Math.random() * 0.01,
      component: "payments-api",
    });
  }
  store.telemetry.set("payments-api", {
    component: "payments-api",
    metric: "error_rate",
    unit: "rate",
    threshold: { min: 0, max: 0.05 },
    points,
    markers: [
      { ts: new Date(Date.now() - 35 * 60_000).toISOString(), kind: "promoted", action_id: C.action_id },
    ],
  });
}

// ---- Live ticker ------------------------------------------------------------
let tickerInterval: ReturnType<typeof setInterval> | null = null;
function startTicker() {
  if (tickerInterval) return;
  tickerInterval = setInterval(() => {
    const now = Date.now();
    for (const vr of store.validations.values()) {
      if (vr.overall_status !== "PENDING" && vr.overall_status !== "PASS") continue;
      const end = Date.parse(vr.window_end);
      vr.time_remaining_seconds = Math.max(0, Math.floor((end - now) / 1000));
      vr.elapsed_seconds = Math.max(0, Math.floor((now - Date.parse(vr.window_start)) / 1000));
      if (vr.time_remaining_seconds === 0 && vr.overall_status === "PENDING") {
        // Auto-expire.
        vr.overall_status = "EXPIRED";
        const action = [...store.actions.values()].find(
          (a) => a.validation_id === vr.validation_id
        );
        if (action) {
          transition(action, "EXPIRED", "system", "window expired");
          transition(action, "REVERTED", "system", "auto-revert from staging");
          bumpCounter(action.category, "failures");
          emit({
            type: "notification",
            kind: "window_expired",
            action_id: action.action_id,
            ticket_id: action.ticket_id,
            triggering: "validation_window_expired",
            resulting_state: "REVERTED",
            detail: { validation_id: vr.validation_id },
            ts: nowIso(),
          });
        }
      }
      emitValidationUpdate(
        [...store.actions.values()].find((a) => a.validation_id === vr.validation_id) ?? {
          action_id: "",
          ticket_id: "",
          category: "",
        } as MitigationAction,
        vr
      );
    }
    // Add one fresh telemetry point per series.
    for (const s of store.telemetry.values()) {
      s.points.push({
        ts: new Date(now).toISOString(),
        metric: s.metric,
        value: 0.005 + Math.random() * 0.015,
        component: s.component,
      });
      if (s.points.length > 120) s.points.shift();
    }
  }, 1000);
}

// ---- Public API -------------------------------------------------------------
let initialized = false;
function ensureInit() {
  if (initialized) return;
  initialized = true;
  seedSafeModeOn();
  seedScenario();
  startTicker();
}

export const mockApi: Api = {
  async listActions(params: ListActionsParams) {
    ensureInit();
    let rows = [...store.actions.values()];
    if (params.states?.length) rows = rows.filter((a) => params.states!.includes(a.state));
    if (params.categories?.length) rows = rows.filter((a) => params.categories!.includes(a.category));
    if (params.types?.length) rows = rows.filter((a) => params.types!.includes(a.type));
    if (params.q) {
      const q = params.q.toLowerCase();
      rows = rows.filter((a) =>
        a.ticket_id.toLowerCase().includes(q) ||
        a.action_id.toLowerCase().includes(q) ||
        a.target.toLowerCase().includes(q) ||
        a.actor.toLowerCase().includes(q)
      );
    }
    if (params.from) rows = rows.filter((a) => a.created_at >= params.from!);
    if (params.to) rows = rows.filter((a) => a.created_at <= params.to!);
    rows.sort((a, b) => (b.created_at > a.created_at ? 1 : -1));
    return rows.slice(0, params.limit ?? 200);
  },
  async getAction(action_id) {
    ensureInit();
    const a = store.actions.get(action_id);
    if (!a) throw new Error(`no action ${action_id}`);
    return a;
  },
  async getValidation(ticket_id) {
    ensureInit();
    const action = [...store.actions.values()].find((a) => a.ticket_id === ticket_id);
    if (!action?.validation_id) throw new Error("no validation");
    const vr = store.validations.get(action.validation_id);
    if (!vr) throw new Error("no validation");
    return vr;
  },
  async getValidationByActionId(action_id) {
    ensureInit();
    const action = store.actions.get(action_id);
    if (!action?.validation_id) throw new Error("no validation");
    const vr = store.validations.get(action.validation_id);
    if (!vr) throw new Error("no validation");
    return vr;
  },
  async getSafeMode() {
    ensureInit();
    return store.safe;
  },
  async getKpis(windowSeconds) {
    ensureInit();
    // Compute crude rolling rates from counters.
    let attempts = 0, failures = 0, rollbacks = 0, declines = 0;
    for (const c of store.guardCounters.values()) {
      attempts += c.attempts;
      failures += c.failures;
      rollbacks += c.rollbacks;
      declines += c.declines;
    }
    const pass = attempts ? (attempts - failures) / attempts : 1;
    const fail = attempts ? failures / attempts : 0;
    const rb = attempts ? rollbacks / attempts : 0;
    const dec = attempts ? declines / attempts : 0;
    return {
      validation_pass_rate: pass,
      validation_fail_rate: fail,
      rollback_rate: rb,
      decline_rate: dec,
      mean_time_in_validation_seconds: 19 * 3600 + 24 * 60,
      expired_count_in_window: [...store.actions.values()].filter((a) => a.state === "EXPIRED" || (a.state === "REVERTED" && a.state_history.some((h) => h.to === "EXPIRED"))).length,
      auto_reverted_count_in_window: [...store.actions.values()].filter((a) => a.state === "REVERTED").length,
      sparklines: {
        pass: Array.from({ length: 24 }, () => 0.8 + Math.random() * 0.2),
        fail: Array.from({ length: 24 }, () => Math.random() * 0.2),
      },
    };
  },
  async getGuards() {
    ensureInit();
    const out: GuardStatus[] = [];
    const t = store.settings.guards;
    for (const cat of store.settings.categories) {
      const c = store.guardCounters.get(cat) ?? { attempts: 0, failures: 0, rollbacks: 0, declines: 0 };
      const denom = Math.max(c.attempts, t.min_samples);
      out.push({
        category: cat,
        rates: [
          { signal: "validation_failed", rate: c.attempts >= t.min_samples ? c.failures / denom : 0, threshold: t.validation_failure_rate, samples: c.attempts },
          { signal: "rolled_back", rate: c.attempts >= t.min_samples ? c.rollbacks / denom : 0, threshold: t.rollback_rate, samples: c.attempts },
          { signal: "declined", rate: c.attempts >= t.min_samples ? c.declines / denom : 0, threshold: t.decline_rate, samples: c.attempts },
        ],
      });
    }
    return out;
  },
  async listAudit(params) {
    ensureInit();
    let rows = store.audit;
    if (params.action_id) rows = rows.filter((r) => r.action_id === params.action_id);
    if (params.ticket_id) rows = rows.filter((r) => r.ticket_id === params.ticket_id);
    if (params.actor) rows = rows.filter((r) => r.actor.includes(params.actor!));
    if (params.transition_type) rows = rows.filter((r) => r.transition_type === params.transition_type);
    if (params.q) {
      const q = params.q.toLowerCase();
      rows = rows.filter((r) =>
        JSON.stringify(r.detail).toLowerCase().includes(q) ||
        r.actor.toLowerCase().includes(q) ||
        (r.from_state ?? "").toLowerCase().includes(q) ||
        (r.to_state ?? "").toLowerCase().includes(q)
      );
    }
    if (params.from) rows = rows.filter((r) => r.ts >= params.from!);
    if (params.to) rows = rows.filter((r) => r.ts <= params.to!);
    return rows.slice(0, params.limit ?? 1000);
  },
  async getTelemetry(component) {
    ensureInit();
    return store.telemetry.get(component) ?? {
      component,
      metric: "error_rate",
      unit: "rate",
      threshold: { min: 0, max: 0.05 },
      points: [],
    };
  },
  async getSettings() {
    ensureInit();
    return store.settings;
  },
  async stage(_ticket_id, body: StageBody) {
    ensureInit();
    const action = store.actions.get(body.action_id);
    if (!action) throw apiError(409, "illegal_transition", "no action");
    if (action.state !== "APPROVED") {
      throw apiError(409, "illegal_transition", `state=${action.state}`);
    }
    transition(action, "STAGED", "human:operator", `target=${body.target ?? "auto"}`);
    const vr = openValidation(action, store.settings.validation_window_seconds);
    transition(action, "VALIDATING", "system", `validation_id=${vr.validation_id}`);
    bumpCounter(action.category, "attempts");
    return {
      deployment_id: uuid(),
      validation_id: vr.validation_id,
      window_start: vr.window_start,
      window_end: vr.window_end,
      status: "PENDING",
    };
  },
  async promote(_ticket_id, body: PromoteBody) {
    ensureInit();
    const action = store.actions.get(body.action_id);
    if (!action) throw apiError(409, "illegal_transition", "no action");
    if (!action.validation_id) throw apiError(409, "illegal_transition", "no validation");
    const vr = store.validations.get(action.validation_id);
    if (!vr) throw apiError(409, "illegal_transition", "no validation");
    if (vr.overall_status !== "PASS") {
      throw apiError(409, "validation_not_passed", `status=${vr.overall_status}`);
    }
    if (!body.confirm) {
      throw apiError(423, "confirm_required", "human confirm required");
    }
    transition(action, "PROMOTED", "human:operator", "engineer confirmed promote");
    const end = new Date(Date.now() + store.settings.rollback_window_seconds * 1000);
    action.rollback_window_end = end.toISOString();
    return { action_id: action.action_id, state: "PROMOTED", rollback_window_end: end.toISOString() };
  },
  async revert(_ticket_id, body: RevertBody) {
    ensureInit();
    const action = store.actions.get(body.action_id);
    if (!action) throw apiError(409, "illegal_transition", "no action");
    // Idempotent on terminal-reverted.
    if (action.state === "REVERTED" || action.state === "ROLLEDBACK") {
      return { action_id: action.action_id, state: action.state, idempotent: true };
    }
    if (action.state === "PROMOTED") {
      const rw_end = action.rollback_window_end ? Date.parse(action.rollback_window_end) : 0;
      if (!rw_end || rw_end <= Date.now()) {
        transition(action, "CLOSED", "human:operator", "rollback window elapsed");
        return { action_id: action.action_id, state: "CLOSED", idempotent: false };
      }
      transition(action, "ROLLEDBACK", "human:operator", body.reason);
      bumpCounter(action.category, "rollbacks");
      return { action_id: action.action_id, state: "ROLLEDBACK", idempotent: false };
    }
    // Staged / Validating / Failed / Expired → Reverted
    transition(action, "REVERTED", "human:operator", body.reason);
    return { action_id: action.action_id, state: "REVERTED", idempotent: false };
  },
  async setSafeMode(body) {
    ensureInit();
    const target =
      body.scope === "system"
        ? store.safe.system
        : (store.safe.categories[body.scope] ??= {
            scope: body.scope,
            active: false,
            entered_at: null,
            entered_by: null,
            exited_at: null,
            exited_by: null,
            reason: null,
          });
    if (body.active) {
      if (!target.active) {
        target.active = true;
        target.entered_at = nowIso();
        target.entered_by = "human:operator";
        target.exited_at = null;
        target.exited_by = null;
        target.reason = body.reason;
        audit({
          action_id: "00000000-0000-0000-0000-000000000000",
          ticket_id: null,
          actor: "human:operator",
          transition_type: "safe_mode",
          from_state: null,
          to_state: "ACTIVE",
          detail: { scope: body.scope, reason: body.reason },
        });
        emit({
          type: "safe_mode_change",
          scope: body.scope,
          active: true,
          actor: "human:operator",
          reason: body.reason,
          ts: nowIso(),
        });
      }
    } else {
      if (target.active) {
        target.active = false;
        target.exited_at = nowIso();
        target.exited_by = "human:operator";
        target.reason = body.reason;
        audit({
          action_id: "00000000-0000-0000-0000-000000000000",
          ticket_id: null,
          actor: "human:operator",
          transition_type: "safe_mode",
          from_state: "ACTIVE",
          to_state: "CLEARED",
          detail: { scope: body.scope, reason: body.reason },
        });
        emit({
          type: "safe_mode_change",
          scope: body.scope,
          active: false,
          actor: "human:operator",
          reason: body.reason,
          ts: nowIso(),
        });
      }
    }
    return { ...target };
  },
  async updateSettings(body) {
    ensureInit();
    store.settings = { ...store.settings, ...body, guards: { ...store.settings.guards, ...(body.guards ?? {}) } };
    return store.settings;
  },
  subscribe(onEvent) {
    ensureInit();
    subscribers.add(onEvent);
    return () => subscribers.delete(onEvent);
  },
};

// ---- API error shape mirrors the FastAPI 4xx detail envelope ---------------
export class ApiError extends Error {
  status: number;
  body: { detail: { error: string; msg?: string } };
  constructor(status: number, error: string, msg?: string) {
    super(msg ?? error);
    this.status = status;
    this.body = { detail: { error, msg } };
  }
}
function apiError(status: number, error: string, msg?: string): ApiError {
  return new ApiError(status, error, msg);
}

// Expose a few scenario helpers used by the Overview demo button.
export const mockHelpers = {
  /** Drive a chosen action's validation to FAIL → auto-revert. */
  fail(action_id: string) {
    const action = store.actions.get(action_id);
    if (!action?.validation_id) return;
    const vr = store.validations.get(action.validation_id);
    if (!vr) return;
    vr.checks = vr.checks.map((c) =>
      c.name === "generated_tests"
        ? { ...c, status: "FAIL", evaluated_at: nowIso(), detail: "1 generated test failed" }
        : c
    );
    vr.overall_status = "FAIL";
    transition(action, "FAILED", "system", "generated_tests failed");
    transition(action, "REVERTED", "system", "auto-revert from staging");
    bumpCounter(action.category, "failures");
    emit({
      type: "notification",
      kind: "validation_failed",
      action_id: action.action_id,
      ticket_id: action.ticket_id,
      triggering: "generated_tests",
      resulting_state: "REVERTED",
      detail: { validation_id: vr.validation_id },
      ts: nowIso(),
    });
  },
  /** Trip a category guard → enter Safe Mode for it. */
  tripGuard(category: string) {
    // Bump failures past the threshold.
    for (let i = 0; i < 6; i++) bumpCounter(category, "failures");
    for (let i = 0; i < 6; i++) bumpCounter(category, "attempts");
    const scope = `category:${category}`;
    store.safe.categories[scope] = {
      scope,
      active: true,
      entered_at: nowIso(),
      entered_by: "guard:validation_failed",
      exited_at: null,
      exited_by: null,
      reason: "rolling rate 0.50 crossed threshold 0.20",
    };
    audit({
      action_id: "00000000-0000-0000-0000-000000000000",
      ticket_id: null,
      actor: "guard:validation_failed",
      transition_type: "safe_mode",
      from_state: null,
      to_state: "ACTIVE",
      detail: { scope, signal: "validation_failed", rate: 0.5 },
    });
    emit({
      type: "guard_trip",
      category,
      signal: "validation_failed",
      value: 0.5,
      threshold: 0.2,
      action_ids: [],
      ts: nowIso(),
    });
    emit({
      type: "safe_mode_change",
      scope,
      active: true,
      actor: "guard:validation_failed",
      reason: "rolling rate 0.50 crossed threshold 0.20",
      ts: nowIso(),
    });
  },
};
