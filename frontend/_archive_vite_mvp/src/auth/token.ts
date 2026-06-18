// Auth seam. Today reads a dev JWT from localStorage; tomorrow this file
// becomes a MSAL bearer-token helper without touching the API client.

export function getBearerToken(): string | null {
  return localStorage.getItem("sentinel_token");
}

export function authHeader(): Record<string, string> {
  const t = getBearerToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}
