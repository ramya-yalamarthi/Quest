/**
 * REST adapter — fetches from the FastAPI backend.
 *
 * Mounted at the URLs declared in next.config.mjs `rewrites`, so the
 * dashboard never hits CORS in dev. The same `Api` shape as the mock
 * adapter, so swapping is a single import change.
 */

import type {
  Api,
  AuditRow,
  GuardStatus,
  KpiSnapshot,
  ListActionsParams,
  ListAuditParams,
  MitigationAction,
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
import { ApiError } from "./mock";

const PREFIX = "/api"; // see next.config.mjs rewrites

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${PREFIX}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
      ...authHeader(),
    },
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new ApiError(
      resp.status,
      body?.detail?.error ?? "request_failed",
      body?.detail?.msg ?? resp.statusText
    );
  }
  return resp.json();
}

function authHeader(): Record<string, string> {
  // The brief says no localStorage. Auth tokens are expected to live in an
  // httpOnly cookie set by the backend's auth flow; the REST adapter relies
  // on `credentials: include` to forward it. If a dev wants to override,
  // they can supply NEXT_PUBLIC_DEV_BEARER (NOT recommended for prod).
  const t = process.env.NEXT_PUBLIC_DEV_BEARER;
  return t ? { Authorization: `Bearer ${t}` } : {};
}

function qs(params: Record<string, unknown>) {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    if (Array.isArray(v)) v.forEach((x) => u.append(k, String(x)));
    else u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

export function makeRestApi(): Api {
  return {
    listActions: (p: ListActionsParams) =>
      http(`/mitigate/actions${qs(p as unknown as Record<string, unknown>)}`),
    getAction: (id) => http(`/mitigate/actions/${id}`),
    getValidation: (ticket) => http<Validation>(`/tickets/${ticket}/mitigate/validation`),
    getValidationByActionId: (action) =>
      http<Validation>(`/mitigate/actions/${action}/validation`),
    getSafeMode: () => http<SafeModeView>("/mitigation/safe-mode"),
    getKpis: (windowSeconds) => http<KpiSnapshot>(`/mitigation/kpis?window=${windowSeconds}`),
    getGuards: () => http<GuardStatus[]>("/mitigation/guards"),
    listAudit: (p: ListAuditParams) =>
      http<AuditRow[]>(`/audit${qs(p as unknown as Record<string, unknown>)}`),
    getTelemetry: (component, windowSeconds) =>
      http<TelemetrySeries>(`/mitigation/telemetry?component=${encodeURIComponent(component)}&window=${windowSeconds}`),
    getSettings: () => http<SettingsPayload>("/mitigation/settings"),
    stage: (ticket, body: StageBody) =>
      http(`/tickets/${ticket}/mitigate/stage`, { method: "POST", body: JSON.stringify(body) }),
    promote: (ticket, body: PromoteBody) =>
      http(`/tickets/${ticket}/mitigate/promote`, { method: "POST", body: JSON.stringify(body) }),
    revert: (ticket, body: RevertBody) =>
      http(`/tickets/${ticket}/mitigate/revert`, { method: "POST", body: JSON.stringify(body) }),
    setSafeMode: (body) =>
      http<SafeModeEntry>("/mitigation/safe-mode", { method: "POST", body: JSON.stringify(body) }),
    updateSettings: (body) =>
      http<SettingsPayload>("/mitigation/settings", { method: "PATCH", body: JSON.stringify(body) }),
    subscribe(onEvent: (e: RTEvent) => void) {
      // SSE by default. The realtime path is rewritten to <API>/mitigation/stream.
      const transport = (process.env.NEXT_PUBLIC_REALTIME ?? "sse").toLowerCase();
      if (transport === "websocket") {
        const url = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/^http/, "ws") + "/mitigation/stream";
        const ws = new WebSocket(url);
        ws.onmessage = (m) => {
          try { onEvent(JSON.parse(m.data)); } catch { /* swallow */ }
        };
        return () => ws.close();
      }
      const es = new EventSource(`${PREFIX}/stream`);
      es.onmessage = (m) => {
        try { onEvent(JSON.parse(m.data)); } catch { /* swallow */ }
      };
      return () => es.close();
    },
  };
}
