"use client";

import { cn } from "@/lib/util/cn";
import { fmtPct } from "@/lib/util/format";

/**
 * Guard proximity — current rate vs configured threshold, drawn as a
 * burn-rate-style bar. Color + position + numeric text all encode the
 * same fact: how close are we to tripping Safe Mode for this signal?
 */
export function GuardProximityBar({
  signal,
  rate,
  threshold,
  samples,
}: {
  signal: string;
  rate: number;
  threshold: number;
  samples: number;
}) {
  const ratio = threshold > 0 ? rate / threshold : 0;
  const pct = Math.min(100, ratio * 100);
  const near = ratio >= 0.7 && ratio < 1;
  const over = ratio >= 1;
  return (
    <div className="card p-3 flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-fg">
          {SIGNAL_LABEL[signal] ?? signal}
        </span>
        <span className="font-data text-2xs text-fg-muted">
          {samples} samples
        </span>
      </div>
      <div className="flex items-baseline gap-2">
        <span
          className={cn(
            "font-data text-base font-semibold",
            over ? "text-danger" : near ? "text-warn" : "text-fg"
          )}
        >
          {fmtPct(rate)}
        </span>
        <span className="font-data text-2xs text-fg-muted">
          / threshold {fmtPct(threshold)}
        </span>
      </div>
      <div
        className="relative h-1.5 rounded-full bg-surface-2 overflow-hidden"
        aria-hidden
      >
        <div
          className={cn(
            "h-full transition-[width] duration-slow ease-out rounded-full",
            over ? "bg-danger" : near ? "bg-warn" : "bg-ok"
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p
        className="text-2xs text-fg-muted"
        aria-live="polite"
      >
        {over
          ? "Threshold crossed — guard will trip Safe Mode."
          : near
          ? "Approaching threshold."
          : "Within safe range."}
      </p>
    </div>
  );
}

const SIGNAL_LABEL: Record<string, string> = {
  validation_failed: "Validation failure rate",
  rolled_back: "Rollback rate",
  declined: "Decline rate",
};
