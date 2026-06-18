"use client";

/**
 * LoopRing — the dashboard's signature element.
 *
 * A radial countdown drawn with a small set of deliberate visual rules:
 *  • the ring sweeps *open* during the 24h validation window
 *  • it only "closes" (a full continuous circle) at the moment of Promote
 *  • on Fail/Expire, it visibly *breaks* — a gap is drawn at the head
 *  • the center always shows the remaining time as large mono text
 *  • a recessed inner track makes the sweep readable in grayscale
 *
 * Respects prefers-reduced-motion: when reduced, the SVG sweep is static
 * (we still update the text once per second so the value is correct).
 */

import { cn } from "@/lib/util/cn";
import { fmtRemaining, useWindowCountdown } from "@/lib/hooks/useCountdown";
import { usePrefersReducedMotion } from "@/lib/hooks/usePrefersReducedMotion";
import type { ValidationStatus } from "@/lib/api/types";
import { CheckCircle2, AlertTriangle, Timer } from "lucide-react";

export interface LoopRingProps {
  /** ISO window_start */
  windowStart?: string | null;
  /** ISO window_end */
  windowEnd?: string | null;
  /** Overall validation status — drives the visual mode (open / closed / broken) */
  overallStatus?: ValidationStatus | "PROMOTED";
  /** Display size in CSS pixels for the outer ring. */
  size?: number;
  /** Optional decorative scale; ignored on mobile. */
  className?: string;
  /** Show "12h 04m remaining of 24h" as the center text */
  showLabel?: boolean;
}

export function LoopRing({
  windowStart,
  windowEnd,
  overallStatus = "PENDING",
  size = 144,
  className,
  showLabel = true,
}: LoopRingProps) {
  const { remaining_s, elapsed_s, total_s } = useWindowCountdown(windowStart, windowEnd);
  const reduced = usePrefersReducedMotion();

  const stroke = size >= 96 ? 10 : 7;
  const r = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const C = 2 * Math.PI * r;
  const progress = total_s > 0 ? Math.min(1, elapsed_s / total_s) : 0;

  // Visual mode — derived from overall status.
  const mode: "open" | "closed" | "broken" =
    overallStatus === "PROMOTED" ? "closed" :
    overallStatus === "FAIL" || overallStatus === "EXPIRED" ? "broken" :
    "open";

  // Open mode: the colored arc represents *time elapsed*; the remaining
  // portion uses a tick pattern so it's readable in grayscale.
  // Closed mode: full continuous accent ring — "loop closed at Promote".
  // Broken mode: ring drawn but with a gap punched out near the head.
  const elapsedArc = mode === "closed" ? C : C * progress;
  const remainingArc = C - elapsedArc;

  // For the broken state we leave a 16° gap at the top so it reads as
  // physically broken even at small sizes.
  const breakGapDeg = mode === "broken" ? 16 : 0;
  const ringAriaLabel =
    mode === "closed"
      ? `Loop closed — promoted.`
      : mode === "broken"
      ? `Loop broken — ${overallStatus === "EXPIRED" ? "window expired" : "validation failed"}; auto-reverted.`
      : `${fmtRemaining(remaining_s)} remaining of ${fmtRemaining(total_s)} validation window.`;

  return (
    <div
      role="img"
      aria-label={ringAriaLabel}
      className={cn("relative inline-flex items-center justify-center", className)}
      style={{ width: size, height: size }}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        // Rotate so the sweep starts at 12 o'clock.
        style={{ transform: "rotate(-90deg)" }}
        aria-hidden
      >
        {/* Outer track — always visible, low contrast */}
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke="rgb(var(--border-strong))"
          strokeWidth={stroke}
          opacity={0.6}
        />
        {/* Inner ticks for grayscale readability — 12 marks for the hours */}
        {Array.from({ length: 12 }).map((_, i) => {
          const a = (i / 12) * 2 * Math.PI;
          const x1 = cx + Math.cos(a) * (r - stroke / 2 - 2);
          const y1 = cy + Math.sin(a) * (r - stroke / 2 - 2);
          const x2 = cx + Math.cos(a) * (r - stroke / 2 - 6);
          const y2 = cy + Math.sin(a) * (r - stroke / 2 - 6);
          return (
            <line
              key={i}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke="rgb(var(--border-strong))"
              strokeWidth={1}
              opacity={0.7}
            />
          );
        })}

        {/* The sweep itself */}
        {mode !== "broken" && (
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke={
              mode === "closed"
                ? "rgb(var(--ok))"
                : "rgb(var(--accent))"
            }
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${elapsedArc} ${remainingArc}`}
            style={{
              transition: reduced ? "none" : "stroke-dasharray var(--motion-slow) var(--motion-ease-out)",
            }}
          />
        )}

        {/* Broken state: draw mostly-full ring with a clear gap at the head */}
        {mode === "broken" && (
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke="rgb(var(--danger))"
            strokeWidth={stroke}
            strokeLinecap="butt"
            strokeDasharray={`${C * (1 - breakGapDeg / 360)} ${C * (breakGapDeg / 360)}`}
            transform={`rotate(${breakGapDeg / 2 + 90} ${cx} ${cy})`}
          />
        )}

        {/* The closure-cap dot at the head of the sweep (open/closed only) */}
        {mode !== "broken" && (
          <circle
            cx={cx + r * Math.cos(2 * Math.PI * progress - Math.PI / 2 + Math.PI / 2)}
            cy={cy + r * Math.sin(2 * Math.PI * progress - Math.PI / 2 + Math.PI / 2)}
            r={stroke / 2}
            fill={mode === "closed" ? "rgb(var(--ok))" : "rgb(var(--accent))"}
          />
        )}
      </svg>

      {/* Center label */}
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        {showLabel && (
          <>
            {mode === "broken" ? (
              <div className="flex flex-col items-center text-danger">
                <AlertTriangle aria-hidden className="size-5 mb-1" />
                <div className="text-xs font-medium uppercase tracking-wider">
                  Loop broken
                </div>
                <div className="text-2xs text-fg-muted">
                  {overallStatus === "EXPIRED" ? "Window expired" : "Check failed"}
                </div>
              </div>
            ) : mode === "closed" ? (
              <div className="flex flex-col items-center text-ok">
                <CheckCircle2 aria-hidden className="size-5 mb-1" />
                <div className="text-xs font-medium uppercase tracking-wider">
                  Loop closed
                </div>
                <div className="text-2xs text-fg-muted">Promoted</div>
              </div>
            ) : (
              <div className="flex flex-col items-center">
                <Timer aria-hidden className="size-4 mb-1 text-fg-muted" />
                <div className="font-data text-lg leading-none text-fg">
                  {fmtRemaining(remaining_s)}
                </div>
                <div className="mt-1 text-2xs uppercase tracking-wider text-fg-muted">
                  Remaining
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
