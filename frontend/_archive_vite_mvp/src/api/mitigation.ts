import { authHeader } from "../auth/token";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export type CheckStatus = "PENDING" | "PASS" | "FAIL";
export type ValidationStatus = "PENDING" | "PASS" | "FAIL" | "EXPIRED";

export interface CheckResult {
  name: string;
  status: CheckStatus;
  detail?: string | null;
  evaluated_at?: string | null;
}

export interface ValidationOut {
  validation_id: string;
  overall_status: ValidationStatus;
  checks: CheckResult[];
  elapsed_seconds: number;
  time_remaining_seconds: number;
  window_start: string;
  window_end: string;
}

export interface SafeModeEntryOut {
  scope: string;
  active: boolean;
  entered_at?: string | null;
  entered_by?: string | null;
  exited_at?: string | null;
  exited_by?: string | null;
  reason?: string | null;
}

export interface SafeModeView {
  system: SafeModeEntryOut;
  categories: Record<string, SafeModeEntryOut>;
}

async function jsonOrThrow<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    const err: any = new Error(`HTTP ${resp.status}`);
    err.status = resp.status;
    err.body = body;
    throw err;
  }
  return resp.json() as Promise<T>;
}

export async function fetchValidation(ticketId: string): Promise<ValidationOut> {
  const resp = await fetch(
    `${BASE}/tickets/${ticketId}/mitigate/validation`,
    { headers: { ...authHeader() } },
  );
  return jsonOrThrow<ValidationOut>(resp);
}

export async function promote(
  ticketId: string,
  actionId: string,
  confirm: boolean,
): Promise<{ action_id: string; state: string; rollback_window_end: string }> {
  const resp = await fetch(
    `${BASE}/tickets/${ticketId}/mitigate/promote`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({ action_id: actionId, confirm }),
    },
  );
  return jsonOrThrow(resp);
}

export async function revert(
  ticketId: string,
  actionId: string,
  reason: string,
): Promise<{ action_id: string; state: string; idempotent: boolean }> {
  const resp = await fetch(
    `${BASE}/tickets/${ticketId}/mitigate/revert`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({ action_id: actionId, reason }),
    },
  );
  return jsonOrThrow(resp);
}

export async function fetchSafeMode(): Promise<SafeModeView> {
  const resp = await fetch(`${BASE}/mitigation/safe-mode`, {
    headers: { ...authHeader() },
  });
  return jsonOrThrow<SafeModeView>(resp);
}

export async function mutateSafeMode(
  scope: string,
  active: boolean,
  reason: string,
): Promise<SafeModeEntryOut> {
  const resp = await fetch(`${BASE}/mitigation/safe-mode`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify({ scope, active, reason }),
  });
  return jsonOrThrow<SafeModeEntryOut>(resp);
}
