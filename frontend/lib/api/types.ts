/**
 * Domain types — the contract between UI and backend.
 *
 * These mirror the FastAPI schemas in
 * `backend/app/mitigation_safety/api/schemas.py`. The mock adapter and the
 * live REST client both satisfy the same `Api` interface so swapping
 * adapters is a single retarget point (see lib/api/index.ts).
 */

export type MitigationState =
  | "DRAFTED"
  | "APPROVED"
  | "REJECTED"
  | "STAGED"
  | "VALIDATING"
  | "PROMOTED"
  | "FAILED"
  | "EXPIRED"
  | "REVERTED"
  | "ROLLEDBACK"
  | "CLOSED";

export const MITIGATION_STATES: MitigationState[] = [
  "DRAFTED",
  "APPROVED",
  "REJECTED",
  "STAGED",
  "VALIDATING",
  "PROMOTED",
  "FAILED",
  "EXPIRED",
  "REVERTED",
  "ROLLEDBACK",
  "CLOSED",
];

export const TERMINAL_STATES = new Set<MitigationState>([
  "REJECTED",
  "REVERTED",
  "ROLLEDBACK",
  "CLOSED",
]);

export type CheckName =
  | "generated_tests"
  | "regression_suite"
  | "telemetry_bounds"
  | "correlated_incidents"
  | "human_signoff";

export const CHECK_ORDER: CheckName[] = [
  "generated_tests",
  "regression_suite",
  "telemetry_bounds",
  "correlated_incidents",
  "human_signoff",
];

export const CHECK_LABEL: Record<CheckName, string> = {
  generated_tests: "Generated tests (CI)",
  regression_suite: "Regression suite",
  telemetry_bounds: "Component telemetry",
  correlated_incidents: "Correlated incidents",
  human_signoff: "Human sign-off",
};

export type CheckStatus = "PENDING" | "PASS" | "FAIL";
export type ValidationStatus = "PENDING" | "PASS" | "FAIL" | "EXPIRED";

export interface CheckResult {
  name: CheckName | string;
  status: CheckStatus;
  detail?: string | null;
  evaluated_at?: string | null;
}

export interface Validation {
  validation_id: string;
  overall_status: ValidationStatus;
  checks: CheckResult[];
  elapsed_seconds: number;
  time_remaining_seconds: number;
  window_start: string; // ISO
  window_end: string;   // ISO
}

export interface MitigationAction {
  action_id: string;
  ticket_id: string;
  category: string;
  type: "code" | "config";
  target: string;
  artifacts_ref: string;
  state: MitigationState;
  created_at: string;
  actor: string;                       // creator
  eligible: boolean;
  revert_handle_ref: string | null;
  validation_id: string | null;
  rollback_window_end: string | null;
  state_history: StateHistoryEntry[];
  expected_outcome?: Record<string, unknown>;
}

export interface StateHistoryEntry {
  from: string | null;
  to: string;
  actor: string;                       // "human:<id>" | "guard:<signal>" | "system"
  timestamp: string;
  detail?: string | null;
}

export interface SafeModeEntry {
  scope: string;                       // "system" | "category:<name>"
  active: boolean;
  entered_at: string | null;
  entered_by: string | null;           // "human:<id>" | "guard:<signal>"
  exited_at: string | null;
  exited_by: string | null;            // always "human:<id>" when set
  reason: string | null;
}

export interface SafeModeView {
  system: SafeModeEntry;
  categories: Record<string, SafeModeEntry>; // key is "category:<name>"
}

export interface AuditRow {
  audit_id: string;
  ts: string;
  action_id: string;
  ticket_id: string | null;
  actor: string;
  transition_type: "state" | "safe_mode" | "guard" | "config" | "system";
  from_state: string | null;
  to_state: string | null;
  detail: Record<string, unknown>;
}

export interface GuardThresholds {
  validation_failure_rate: number;
  rollback_rate: number;
  decline_rate: number;
  rolling_window_seconds: number;
  min_samples: number;
  telemetry_bounds: Record<string, Record<string, { min?: number; max?: number }>>;
}

export interface GuardStatus {
  category: string;
  rates: {
    signal: "validation_failed" | "rolled_back" | "declined";
    rate: number;
    threshold: number;
    samples: number;
  }[];
}

export interface TelemetryPoint {
  ts: string;
  metric: string;
  value: number;
  component: string;
}

export interface TelemetrySeries {
  component: string;
  metric: string;
  unit?: string;
  threshold?: { min?: number; max?: number };
  points: TelemetryPoint[];
  markers?: { ts: string; kind: "promoted" | "reverted" | "rolledback"; action_id: string }[];
}

export interface KpiSnapshot {
  validation_pass_rate: number;
  validation_fail_rate: number;
  rollback_rate: number;
  decline_rate: number;
  mean_time_in_validation_seconds: number;
  expired_count_in_window: number;
  auto_reverted_count_in_window: number;
  sparklines: Record<string, number[]>;
}

export interface SettingsPayload {
  validation_window_seconds: number;
  rollback_window_seconds: number;
  confirm_to_promote: Record<string, boolean>;
  validation_window_overrides: Record<string, number>;
  rollback_window_overrides: Record<string, number>;
  guards: GuardThresholds;
  categories: string[];
  allow_listed_categories: string[];
  notifications?: NotificationConfig;
}

export interface NotificationConfig {
  engineer_slack?: string;
  engineer_email?: string;
  lead_slack?: string;
  lead_email?: string;
  channels: ("validation_failure" | "window_expiry" | "guard_rollback" | "safe_mode_entry")[];
}

// ---- Realtime events --------------------------------------------------------

export interface RTStateTransition {
  type: "state_transition";
  action_id: string;
  ticket_id: string | null;
  from: MitigationState | null;
  to: MitigationState;
  actor: string;
  ts: string;
}

export interface RTValidationUpdate {
  type: "validation_update";
  validation_id: string;
  action_id: string;
  overall_status: ValidationStatus;
  checks: CheckResult[];
  time_remaining_seconds: number;
  ts: string;
}

export interface RTSafeModeChange {
  type: "safe_mode_change";
  scope: string;
  active: boolean;
  actor: string;
  reason: string | null;
  ts: string;
}

export interface RTGuardTrip {
  type: "guard_trip";
  category: string;
  signal: string;
  value: number;
  threshold: number;
  action_ids: string[];
  ts: string;
}

export interface RTNotification {
  type: "notification";
  kind:
    | "validation_failed"
    | "window_expired"
    | "guard_rollback"
    | "safe_mode_entered";
  action_id: string | null;
  ticket_id: string | null;
  triggering: string;
  resulting_state: string | null;
  detail: Record<string, unknown>;
  ts: string;
}

export type RTEvent =
  | RTStateTransition
  | RTValidationUpdate
  | RTSafeModeChange
  | RTGuardTrip
  | RTNotification;

// ---- API contract -----------------------------------------------------------

export interface ListActionsParams {
  states?: MitigationState[];
  categories?: string[];
  types?: ("code" | "config")[];
  q?: string;
  from?: string;
  to?: string;
  limit?: number;
}

export interface ListAuditParams {
  action_id?: string;
  ticket_id?: string;
  actor?: string;
  transition_type?: AuditRow["transition_type"];
  q?: string;
  from?: string;
  to?: string;
  limit?: number;
}

export interface StageBody {
  action_id: string;
  type: "code" | "config";
  artifacts_ref: string;
  expected_outcome: Record<string, unknown>;
  revert_handle_ref: string;
  category: string;
  target?: string;
}

export interface PromoteBody {
  action_id: string;
  confirm: boolean;
}

export interface RevertBody {
  action_id: string;
  reason: string;
}

export interface Api {
  // Reads
  listActions(params: ListActionsParams): Promise<MitigationAction[]>;
  getAction(action_id: string): Promise<MitigationAction>;
  getValidation(ticket_id: string): Promise<Validation>;
  getValidationByActionId(action_id: string): Promise<Validation>;
  getSafeMode(): Promise<SafeModeView>;
  getKpis(windowSeconds: number): Promise<KpiSnapshot>;
  getGuards(): Promise<GuardStatus[]>;
  listAudit(params: ListAuditParams): Promise<AuditRow[]>;
  getTelemetry(component: string, windowSeconds: number): Promise<TelemetrySeries>;
  getSettings(): Promise<SettingsPayload>;

  // Writes (all require an authenticated human)
  stage(ticket_id: string, body: StageBody): Promise<{ deployment_id: string; validation_id: string; window_start: string; window_end: string; status: "PENDING" }>;
  promote(ticket_id: string, body: PromoteBody): Promise<{ action_id: string; state: "PROMOTED"; rollback_window_end: string }>;
  revert(ticket_id: string, body: RevertBody): Promise<{ action_id: string; state: "REVERTED" | "ROLLEDBACK" | "CLOSED"; idempotent: boolean }>;
  setSafeMode(body: { scope: string; active: boolean; reason: string }): Promise<SafeModeEntry>;
  updateSettings(body: Partial<SettingsPayload>): Promise<SettingsPayload>;

  // Realtime
  subscribe(onEvent: (e: RTEvent) => void): () => void;
}
