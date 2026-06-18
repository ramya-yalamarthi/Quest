"use client";

/**
 * StateBadge — the canonical pill for one of the 11 mitigation states.
 *
 * Color is NEVER the only signal. Every badge carries:
 *   1. color      (token-mapped, dark+light safe)
 *   2. icon       (lucide, consistent stroke; aria-hidden — text label says it)
 *   3. text label (sentence case, full state name)
 *   4. shape      (border style + a small marker that distinguishes states
 *                  even in grayscale)
 *
 * This satisfies the WCAG 2.2 "color is not the only indicator" rule and
 * keeps the lifecycle pipeline readable on a printer or to a color-blind
 * operator.
 */

import { cn } from "@/lib/util/cn";
import type { MitigationState } from "@/lib/api/types";
import {
  CircleDashed,
  CircleCheckBig,
  CircleX,
  PackageCheck,
  Loader2,
  ShieldCheck,
  AlertTriangle,
  Timer,
  Undo2,
  RotateCcw,
  CircleSlash,
  type LucideIcon,
} from "lucide-react";

interface Spec {
  label: string;
  icon: LucideIcon;
  /** Background + foreground class pair, dark/light safe via tokens. */
  cls: string;
  /** Shape modifier — different shapes per state so grayscale still reads. */
  shape: "solid" | "ring" | "double-ring" | "striped" | "dashed";
  /** A tiny SR-only suffix when the state is non-obvious. */
  hint?: string;
}

const SPEC: Record<MitigationState, Spec> = {
  DRAFTED:    { label: "Drafted",     icon: CircleDashed,   cls: "bg-surface-2 text-fg-muted border-border-strong",      shape: "dashed" },
  APPROVED:   { label: "Approved",    icon: CircleCheckBig, cls: "bg-info/10 text-info border-info/40",                   shape: "ring" },
  REJECTED:   { label: "Rejected",    icon: CircleX,        cls: "bg-neutral/10 text-fg-muted border-neutral/40",         shape: "ring" },
  STAGED:     { label: "Staged",      icon: PackageCheck,   cls: "bg-info/10 text-info border-info/40",                   shape: "double-ring" },
  VALIDATING: { label: "Validating",  icon: Loader2,        cls: "bg-warn/10 text-warn border-warn/40",                   shape: "ring",       hint: "in 24-hour validation window" },
  PROMOTED:   { label: "Promoted",    icon: ShieldCheck,    cls: "bg-ok/10 text-ok border-ok/40",                         shape: "solid" },
  FAILED:     { label: "Failed",      icon: AlertTriangle,  cls: "bg-danger/15 text-danger border-danger/40",             shape: "ring" },
  EXPIRED:    { label: "Expired",     icon: Timer,          cls: "bg-danger/15 text-danger border-danger/40",             shape: "dashed",    hint: "window elapsed without PASS" },
  REVERTED:   { label: "Reverted",    icon: Undo2,          cls: "bg-danger/10 text-danger border-danger/40",             shape: "ring" },
  ROLLEDBACK: { label: "Rolled back", icon: RotateCcw,      cls: "bg-danger/10 text-danger border-danger/40",             shape: "double-ring" },
  CLOSED:     { label: "Closed",      icon: CircleSlash,    cls: "bg-neutral/10 text-fg-muted border-neutral/40",         shape: "solid" },
};

export function StateBadge({
  state,
  size = "md",
  withDot = false,
  className,
}: {
  state: MitigationState;
  size?: "sm" | "md";
  withDot?: boolean;
  className?: string;
}) {
  const spec = SPEC[state];
  const Icon = spec.icon;
  const ringExtras: Record<Spec["shape"], string> = {
    solid: "",
    ring: "ring-1 ring-inset ring-current/30",
    "double-ring": "ring-2 ring-offset-1 ring-offset-bg ring-current/30",
    striped: "bg-[length:8px_8px] bg-[linear-gradient(45deg,currentColor_25%,transparent_25%,transparent_50%,currentColor_50%,currentColor_75%,transparent_75%)]",
    dashed: "border-dashed",
  };
  const sizeCls =
    size === "sm"
      ? "px-1.5 py-0.5 text-2xs gap-1 h-5"
      : "px-2 py-0.5 text-xs gap-1.5 h-6";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border font-medium align-middle whitespace-nowrap",
        spec.cls,
        ringExtras[spec.shape],
        sizeCls,
        className
      )}
    >
      {withDot && (
        <span
          className={cn("size-1.5 rounded-full bg-current")}
          aria-hidden
        />
      )}
      <Icon
        aria-hidden
        className={cn(
          size === "sm" ? "size-3" : "size-3.5",
          state === "VALIDATING" ? "motion-safe:animate-spin" : ""
        )}
        strokeWidth={2}
      />
      <span>{spec.label}</span>
      {spec.hint && <span className="sr-only">— {spec.hint}</span>}
    </span>
  );
}

export { SPEC as STATE_BADGE_SPEC };
