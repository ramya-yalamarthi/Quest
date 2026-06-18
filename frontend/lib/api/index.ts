/**
 * Adapter selector — one place to swap between mock and live.
 *
 * Defaults to the mock so the dashboard runs end-to-end with no backend.
 * Set NEXT_PUBLIC_API_BASE_URL to point at a real FastAPI host and the
 * REST adapter takes over.
 */

import type { Api } from "./types";
import { mockApi } from "./mock";
import { makeRestApi } from "./rest";

export function getApi(): Api {
  if (typeof window === "undefined") return mockApi; // SSR — never hit network
  if (process.env.NEXT_PUBLIC_API_BASE_URL) return makeRestApi();
  return mockApi;
}

export { ApiError, mockHelpers } from "./mock";
export type * from "./types";
