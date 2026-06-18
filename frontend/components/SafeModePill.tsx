"use client";

import { Lock, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/util/cn";
import { useSafeMode } from "@/lib/hooks/useSafeMode";
import Link from "next/link";

/**
 * SafeModePill — top-bar status pill.
 *
 * Green "Autonomy active" / striped-halt "Safe Mode — human approval
 * required" with a count of held scopes. Striped pattern conveys "halt"
 * without depending on color alone.
 */
export function SafeModePill() {
  const { data } = useSafeMode();
  if (!data) return <Placeholder />;
  const heldCount =
    (data.system.active ? 1 : 0) +
    Object.values(data.categories).filter((c) => c.active).length;
  if (heldCount === 0) {
    return (
      <Link
        href="/safe-mode"
        className="inline-flex items-center gap-1.5 rounded-full border border-ok/40 bg-ok/10 px-2.5 py-1 text-xs font-medium text-ok hover:bg-ok/15 transition-colors"
        aria-label="Autonomy active — Safe Mode off"
      >
        <ShieldCheck className="size-3.5" aria-hidden />
        Autonomy active
      </Link>
    );
  }
  return (
    <Link
      href="/safe-mode"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold text-bg striped-halt",
        "ring-1 ring-halt/60 hover:ring-halt"
      )}
      aria-label={`Safe Mode active for ${heldCount} scope${heldCount > 1 ? "s" : ""}. Human approval required.`}
    >
      <Lock className="size-3.5" aria-hidden />
      Safe Mode · {heldCount} scope{heldCount > 1 ? "s" : ""}
    </Link>
  );
}

function Placeholder() {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-border-strong bg-surface-2 px-2.5 py-1 text-xs text-fg-muted"
      aria-busy
    >
      <span className="size-2 rounded-full bg-fg-muted/40" aria-hidden />
      Loading…
    </span>
  );
}
