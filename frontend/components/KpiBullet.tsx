"use client";

/**
 * KpiBullet — a Tufte-style bullet chart for a KPI vs guard threshold.
 *
 * Number is always primary text (legible without color or chart). The
 * threshold marker is drawn as a vertical tick at the configured
 * threshold. Near-threshold tints amber; over tints red.
 */

import { cn } from "@/lib/util/cn";
import { fmtPct } from "@/lib/util/format";

export interface KpiBulletProps {
  label: string;
  value: number;           // 0..1 (rate) or 0..max
  threshold?: number;      // 0..1 (rate) or 0..max
  max?: number;            // defaults to 1
  /** "rate" formats as percentage; "count" formats as integer. */
  format?: "rate" | "count" | "seconds";
  /** A short sparkline-style array, optional */
  sparkline?: number[];
  /** Increase the visual weight (use for the overview KPI row only) */
  large?: boolean;
}

export function KpiBullet({
  label,
  value,
  threshold,
  max = 1,
  format = "rate",
  sparkline,
  large = false,
}: KpiBulletProps) {
  const safeMax = Math.max(max, threshold ?? 0, value, 0.0001);
  const valuePct = Math.min(100, (value / safeMax) * 100);
  const thresholdPct =
    threshold !== undefined ? Math.min(100, (threshold / safeMax) * 100) : null;

  const near =
    threshold !== undefined && value >= threshold * 0.8 && value < threshold;
  const over = threshold !== undefined && value >= threshold;

  const valueText =
    format === "rate"
      ? fmtPct(value)
      : format === "seconds"
      ? `${Math.round(value / 60)} min`
      : value.toLocaleString();

  return (
    <div
      className={cn(
        "card p-4",
        large ? "min-h-32" : "min-h-24",
        over && "border-danger/60"
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-2xs uppercase tracking-wider text-fg-muted">
          {label}
        </span>
        {threshold !== undefined && (
          <span
            className={cn(
              "font-data text-2xs",
              over ? "text-danger" : near ? "text-warn" : "text-fg-muted"
            )}
            aria-label={`Threshold ${format === "rate" ? fmtPct(threshold) : threshold}`}
          >
            ⌖ {format === "rate" ? fmtPct(threshold) : threshold}
          </span>
        )}
      </div>
      <div
        className={cn(
          "font-data text-fg font-semibold",
          large ? "text-2xl mt-2" : "text-xl mt-1.5"
        )}
        aria-label={`${label}: ${valueText}`}
      >
        {valueText}
      </div>

      {/* The bullet bar */}
      <div
        className="relative mt-3 h-2 rounded-full bg-surface-2 overflow-hidden"
        aria-hidden
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-slow ease-out",
            over
              ? "bg-danger"
              : near
              ? "bg-warn"
              : "bg-accent"
          )}
          style={{ width: `${valuePct}%` }}
        />
        {thresholdPct !== null && (
          <div
            className="absolute top-0 bottom-0 w-px bg-fg/70"
            style={{ left: `calc(${thresholdPct}% - 0.5px)` }}
          />
        )}
      </div>

      {sparkline && sparkline.length > 1 && (
        <Sparkline values={sparkline} className="mt-3 h-7" />
      )}
    </div>
  );
}

function Sparkline({
  values,
  className,
}: {
  values: number[];
  className?: string;
}) {
  const w = 100;
  const h = 24;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = w / (values.length - 1);
  const d = values
    .map((v, i) => {
      const x = i * step;
      const y = h - ((v - min) / range) * h;
      return `${i === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className={cn("w-full", className)}
      aria-hidden
    >
      <path
        d={d}
        fill="none"
        stroke="rgb(var(--fg-muted))"
        strokeWidth={1.25}
      />
    </svg>
  );
}
