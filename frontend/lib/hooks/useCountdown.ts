"use client";

import { useEffect, useState } from "react";
import { usePrefersReducedMotion } from "./usePrefersReducedMotion";

/**
 * Tick a countdown to a target ISO timestamp.
 *
 * The hook is the single time source for the LoopRing, action-card
 * countdowns, and rollback-window indicators — so all surfaces tick in
 * lockstep without re-rendering each other.
 *
 * Respects prefers-reduced-motion: it still updates the displayed value
 * once per second (correctness > smoothness), but the SVG ring sweep is
 * frozen by the consuming component.
 */
export function useCountdown(targetIso: string | null | undefined): {
  remaining_s: number;
  elapsed_s: number;
  total_s: number;
  done: boolean;
} {
  const [now, setNow] = useState(() => Date.now());
  // Reduced motion does not change the cadence here — the component decides
  // whether to animate. We still tick every second so the text value stays
  // accurate.
  usePrefersReducedMotion();
  useEffect(() => {
    if (!targetIso) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [targetIso]);
  if (!targetIso) return { remaining_s: 0, elapsed_s: 0, total_s: 0, done: true };
  const end = Date.parse(targetIso);
  const remaining_s = Math.max(0, Math.floor((end - now) / 1000));
  return {
    remaining_s,
    elapsed_s: 0,
    total_s: 0,
    done: remaining_s <= 0,
  };
}

/**
 * For the LoopRing — we need both elapsed and remaining (and a stable total).
 */
export function useWindowCountdown(
  start: string | null | undefined,
  end: string | null | undefined
): { remaining_s: number; elapsed_s: number; total_s: number; done: boolean } {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!start || !end) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [start, end]);
  if (!start || !end) return { remaining_s: 0, elapsed_s: 0, total_s: 0, done: true };
  const s = Date.parse(start);
  const e = Date.parse(end);
  const total_s = Math.max(1, Math.floor((e - s) / 1000));
  const elapsed_s = Math.max(0, Math.min(total_s, Math.floor((now - s) / 1000)));
  const remaining_s = Math.max(0, total_s - elapsed_s);
  return { remaining_s, elapsed_s, total_s, done: remaining_s <= 0 };
}

/**
 * Format seconds as "12h 04m" / "04m 12s" / "00m 04s".
 */
export function fmtRemaining(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${pad(h)}h ${pad(m)}m`;
  if (m > 0) return `${pad(m)}m ${pad(sec)}s`;
  return `${pad(sec)}s`;
}

function pad(n: number) {
  return n.toString().padStart(2, "0");
}
