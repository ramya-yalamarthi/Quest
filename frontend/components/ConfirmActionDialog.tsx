"use client";

/**
 * ConfirmActionDialog — consequence-stating modal used by Promote and Revert.
 *
 * - Title states the action ("Promote to production")
 * - Body states the consequence in plain language and shows what will change
 *   (which target / which scope / which rollback window applies)
 * - Optional required reason input (Revert always; Promote never)
 * - Primary button is destructively-styled for Revert; primary for Promote
 * - Two confirm "shapes": single-click for Promote (after the dialog itself),
 *   typed-confirm for Revert (paste-style "I understand" not required, but a
 *   non-empty reason is)
 */

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/Dialog";
import { Button } from "./ui/Button";
import { cn } from "@/lib/util/cn";
import { AlertTriangle, ShieldCheck } from "lucide-react";

export interface ConfirmActionDialogProps {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  intent: "promote" | "revert";
  title: string;
  /** Plain-English consequence statement, e.g. "This will deploy to production." */
  consequence: React.ReactNode;
  /** Optional list of bullet facts shown in a dense card. */
  facts?: { label: string; value: React.ReactNode }[];
  /** Provided by parent — handles the actual API call. Must throw on failure. */
  onConfirm: (reason: string) => Promise<void>;
  /** Disabled state with reason (e.g. validation not PASS). */
  disabledReason?: string | null;
  /** Force a reason input (required for revert). */
  requireReason?: boolean;
}

export function ConfirmActionDialog({
  open,
  onOpenChange,
  intent,
  title,
  consequence,
  facts,
  onConfirm,
  disabledReason,
  requireReason = false,
}: ConfirmActionDialogProps) {
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setReason("");
    setError(null);
    setSubmitting(false);
  }

  async function handleConfirm() {
    if (requireReason && reason.trim().length === 0) {
      setError("A reason is required to revert.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm(reason.trim());
      reset();
      onOpenChange(false);
    } catch (e: unknown) {
      const msg =
        e && typeof e === "object" && "message" in e
          ? String((e as { message: string }).message)
          : "Request failed";
      setError(msg);
      setSubmitting(false);
    }
  }

  const PrimaryIcon = intent === "promote" ? ShieldCheck : AlertTriangle;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <PrimaryIcon
              aria-hidden
              className={cn(
                "size-5",
                intent === "promote" ? "text-ok" : "text-danger"
              )}
            />
            {title}
          </DialogTitle>
          <DialogDescription>{consequence}</DialogDescription>
        </DialogHeader>

        {facts && facts.length > 0 && (
          <dl className="mt-4 grid grid-cols-3 gap-y-2 gap-x-3 rounded-md border border-border bg-surface-2/40 p-3 text-xs">
            {facts.map((f) => (
              <div key={f.label} className="contents">
                <dt className="col-span-1 text-fg-muted">{f.label}</dt>
                <dd className="col-span-2 font-data text-fg break-all">
                  {f.value}
                </dd>
              </div>
            ))}
          </dl>
        )}

        {requireReason && (
          <label className="mt-4 flex flex-col gap-1.5">
            <span className="text-xs text-fg-muted">
              Reason{" "}
              <span className="text-danger" aria-hidden>
                *
              </span>
            </span>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              maxLength={500}
              placeholder="What's the trigger? Keep it short — this goes into the audit log."
              className="rounded-md border border-border bg-surface px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
              required
            />
            <span className="text-2xs text-fg-subtle">
              Recorded immutably in the audit log alongside your identity.
            </span>
          </label>
        )}

        {disabledReason && (
          <div className="mt-3 rounded-md border border-warn/30 bg-warn/5 px-3 py-2 text-xs text-warn">
            {disabledReason}
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="mt-3 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger"
          >
            {error}
          </div>
        )}

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            Cancel
          </Button>
          <Button
            variant={intent === "promote" ? "primary" : "destructive"}
            onClick={handleConfirm}
            disabled={submitting || Boolean(disabledReason)}
          >
            {submitting
              ? intent === "promote"
                ? "Promoting…"
                : "Reverting…"
              : intent === "promote"
                ? "Confirm promote"
                : "Confirm revert"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
