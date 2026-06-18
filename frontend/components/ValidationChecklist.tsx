"use client";

/**
 * ValidationChecklist — the five MS-09 checks.
 *
 * Each row: name, status badge (color + icon + label), evaluated-at, and
 * an expandable detail. PASS uses a check; FAIL an X; PENDING a dashed
 * circle — so the list reads in grayscale.
 */

import { cn } from "@/lib/util/cn";
import { CHECK_LABEL, type CheckName, type CheckResult } from "@/lib/api/types";
import { Check, X, CircleDashed, ExternalLink } from "lucide-react";
import { useState } from "react";

export function ValidationChecklist({
  checks,
  overallStatus,
}: {
  checks: CheckResult[];
  overallStatus: string;
}) {
  return (
    <div className="card overflow-hidden">
      <div className="flex items-baseline justify-between gap-2 px-4 py-3 border-b border-border">
        <h3 className="text-sm font-medium text-fg">Checklist</h3>
        <span
          className={cn(
            "font-data text-2xs uppercase tracking-wider",
            overallStatus === "PASS"
              ? "text-ok"
              : overallStatus === "FAIL" || overallStatus === "EXPIRED"
              ? "text-danger"
              : "text-warn"
          )}
        >
          {overallStatus}
        </span>
      </div>
      <ul role="list" className="divide-y divide-border">
        {checks.map((c) => (
          <CheckRow key={c.name} check={c} />
        ))}
      </ul>
    </div>
  );
}

function CheckRow({ check }: { check: CheckResult }) {
  const [open, setOpen] = useState(false);
  const Icon =
    check.status === "PASS" ? Check : check.status === "FAIL" ? X : CircleDashed;
  const colorCls =
    check.status === "PASS"
      ? "text-ok"
      : check.status === "FAIL"
      ? "text-danger"
      : "text-warn";
  const label = CHECK_LABEL[check.name as CheckName] ?? check.name;
  return (
    <li className="px-4 py-3">
      <button
        type="button"
        className="w-full text-left flex items-start gap-3"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span
          aria-hidden
          className={cn(
            "mt-0.5 inline-flex size-5 items-center justify-center rounded-full border",
            check.status === "PASS"
              ? "border-ok/40 bg-ok/10"
              : check.status === "FAIL"
              ? "border-danger/40 bg-danger/10"
              : "border-warn/40 bg-warn/10 border-dashed"
          )}
        >
          <Icon className={cn("size-3.5", colorCls)} strokeWidth={2.5} />
        </span>
        <span className="flex-1">
          <span className="flex items-baseline justify-between gap-2">
            <span className="text-sm text-fg">{label}</span>
            <span
              className={cn(
                "font-data text-2xs uppercase tracking-wider",
                colorCls
              )}
            >
              {check.status}
            </span>
          </span>
          {check.detail && (
            <span className="block mt-0.5 text-xs text-fg-muted">
              {check.detail}
            </span>
          )}
          {check.evaluated_at && (
            <span className="block mt-0.5 font-data text-2xs text-fg-subtle">
              {new Date(check.evaluated_at).toLocaleString(undefined, {
                hour12: false,
              })}
            </span>
          )}
        </span>
        {check.name === "generated_tests" && (
          <ExternalLink
            aria-hidden
            className="mt-1 size-4 text-fg-muted"
          />
        )}
      </button>
    </li>
  );
}
