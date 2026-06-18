/**
 * Locale-aware number/time formatting helpers.
 * Tabular numerics is enabled globally; these only handle text content.
 */

export function fmtPct(v: number, digits = 1): string {
  if (Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function fmtAge(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ms = Date.now() - Date.parse(iso);
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export function fmtClockUtc(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toISOString().replace("T", " ").slice(0, 19) + "Z";
}

export function truncId(id: string, head = 8, tail = 4): string {
  if (id.length <= head + tail + 1) return id;
  return `${id.slice(0, head)}…${id.slice(-tail)}`;
}
