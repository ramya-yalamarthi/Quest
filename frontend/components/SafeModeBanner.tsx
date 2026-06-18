"use client";

/**
 * SafeModeBanner — sticky high-visibility halt banner.
 *
 * Always renders for the highest-priority active scope. Sets a class on
 * <html> so the global focus-not-obscured rule (WCAG 2.2 §2.4.11) can push
 * scroll-margin-top on focused elements while the banner is showing.
 */

import { useEffect } from "react";
import Link from "next/link";
import { Lock } from "lucide-react";
import { useSafeMode } from "@/lib/hooks/useSafeMode";
import { fmtAge } from "@/lib/util/format";

export function SafeModeBanner() {
  const { data } = useSafeMode();
  const held = [
    ...(data?.system.active ? [data.system] : []),
    ...(data ? Object.values(data.categories).filter((c) => c.active) : []),
  ];
  const active = held.length > 0;
  const primary = held[0];

  // Toggle a class on <html> so CSS can adjust scroll-margin-top on focus.
  useEffect(() => {
    const root = document.documentElement;
    if (active) {
      root.classList.add("banner-active");
    } else {
      root.classList.remove("banner-active");
    }
  }, [active]);

  if (!active || !primary) return null;

  return (
    <div
      role="region"
      aria-label="Safe Mode banner"
      className="striped-halt sticky z-40 text-bg shadow-e1"
      style={{
        top: "var(--topbar-h)",
        minHeight: "var(--safe-mode-banner-h)",
      }}
    >
      <div className="container flex flex-wrap items-center gap-3 py-3">
        <Lock aria-hidden className="size-5 shrink-0" />
        <div className="flex-1 min-w-0 text-sm">
          <p className="font-semibold">
            Safe Mode active — {held.length} scope
            {held.length > 1 ? "s" : ""}. Auto-execution suspended;
            mitigations require human approval.
          </p>
          <p className="text-xs opacity-90 font-data">
            entered_by <strong>{primary.entered_by ?? "—"}</strong>
            {" · "}
            {fmtAge(primary.entered_at)}
            {primary.reason && (
              <>
                {" · "}
                <span className="opacity-80">{primary.reason}</span>
              </>
            )}
          </p>
        </div>
        <Link
          href="/safe-mode"
          className="inline-flex items-center gap-1 rounded border border-bg/40 bg-bg/15 px-2.5 py-1 text-xs font-medium hover:bg-bg/25 transition-colors"
        >
          Manage
        </Link>
      </div>
    </div>
  );
}
