"use client";

/**
 * PromotionDecisionPanel — renders the live decision tree the backend uses
 * to gate Promote, so it is always obvious *why* the button is or isn't
 * available right now.
 *
 *  All checks PASS?  →  Safe Mode active for category?  →  confirm-to-promote required?
 *
 * Each node reflects the live state via the inputs.
 */

import { cn } from "@/lib/util/cn";
import { Check, X, AlertOctagon, ShieldQuestion } from "lucide-react";

export function PromotionDecisionPanel({
  overallPass,
  safeModeHeld,
  confirmRequired,
}: {
  overallPass: boolean;
  safeModeHeld: boolean;
  confirmRequired: boolean;
}) {
  const canAuto = overallPass && !safeModeHeld && !confirmRequired;
  const canConfirm = overallPass && (safeModeHeld || confirmRequired);

  return (
    <div className="card p-4">
      <h3 className="text-2xs uppercase tracking-wider text-fg-muted">
        Promotion decision
      </h3>
      <ol className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
        <Node
          label="All checks PASS?"
          ok={overallPass}
          okText="Yes — validation passed"
          failText="No — promote unavailable until PASS"
        />
        <Node
          label="Safe Mode active?"
          ok={!safeModeHeld}
          okText="No — autonomy normal"
          failText="Yes — human confirm required"
          warnInsteadOfFail
        />
        <Node
          label="confirm-to-promote required?"
          ok={!confirmRequired}
          okText="No — would auto-promote"
          failText="Yes — explicit confirm required"
          warnInsteadOfFail
        />
      </ol>
      <p
        className={cn(
          "mt-4 text-sm",
          canAuto ? "text-ok" : canConfirm ? "text-warn" : "text-danger"
        )}
      >
        {canAuto && "Promote is available. Auto-promotion permitted (no human confirm required)."}
        {canConfirm && "Promote is available with an explicit human confirm."}
        {!overallPass && "Promote is not available — validation has not passed."}
      </p>
    </div>
  );
}

function Node({
  label,
  ok,
  okText,
  failText,
  warnInsteadOfFail = false,
}: {
  label: string;
  ok: boolean;
  okText: string;
  failText: string;
  warnInsteadOfFail?: boolean;
}) {
  const Icon = ok ? Check : warnInsteadOfFail ? AlertOctagon : X;
  const cls = ok
    ? "border-ok/40 bg-ok/10 text-ok"
    : warnInsteadOfFail
    ? "border-warn/40 bg-warn/10 text-warn"
    : "border-danger/40 bg-danger/10 text-danger";
  return (
    <li
      className={cn(
        "flex flex-col gap-1.5 rounded-md border p-3",
        cls
      )}
    >
      <div className="flex items-start gap-2">
        <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span className="text-xs font-medium text-fg">{label}</span>
      </div>
      <p className="text-2xs text-fg-muted">{ok ? okText : failText}</p>
    </li>
  );
}
