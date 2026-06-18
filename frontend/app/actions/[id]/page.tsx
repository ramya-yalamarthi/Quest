"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getApi } from "@/lib/api";
import type { MitigationAction, Validation } from "@/lib/api/types";
import { StateBadge } from "@/components/StateBadge";
import { LoopRing } from "@/components/LoopRing";
import { ValidationChecklist } from "@/components/ValidationChecklist";
import { LifecycleTimeline } from "@/components/LifecycleTimeline";
import { CopyableId } from "@/components/CopyableId";
import { PromotionDecisionPanel } from "@/components/PromotionDecisionPanel";
import { ConfirmActionDialog } from "@/components/ConfirmActionDialog";
import { Button } from "@/components/ui/Button";
import { useSafeMode } from "@/lib/hooks/useSafeMode";
import {
  ArrowLeft,
  ChevronRight,
  GitBranch,
  Boxes,
  ShieldCheck,
  Undo2,
} from "lucide-react";
import { fmtAge, truncId } from "@/lib/util/format";
import { fmtRemaining, useCountdown } from "@/lib/hooks/useCountdown";

export default function ActionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const api = getApi();
  const qc = useQueryClient();
  const safeMode = useSafeMode();

  const actionQuery = useQuery({
    queryKey: ["action", id],
    queryFn: () => api.getAction(id),
    refetchInterval: 5_000,
  });

  const validationQuery = useQuery({
    queryKey: ["validation", id],
    queryFn: () => api.getValidationByActionId(id),
    enabled: actionQuery.data?.validation_id != null,
    refetchInterval: 2_000,
  });

  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.getSettings(),
  });

  const [promoteOpen, setPromoteOpen] = useState(false);
  const [revertOpen, setRevertOpen] = useState(false);

  const promote = useMutation({
    mutationFn: () =>
      api.promote(actionQuery.data!.ticket_id, {
        action_id: id,
        confirm: true,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["action", id] });
      qc.invalidateQueries({ queryKey: ["actions"] });
    },
  });

  const revert = useMutation({
    mutationFn: (reason: string) =>
      api.revert(actionQuery.data!.ticket_id, { action_id: id, reason }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["action", id] });
      qc.invalidateQueries({ queryKey: ["actions"] });
    },
  });

  if (actionQuery.isLoading) {
    return (
      <div className="card p-6 animate-pulse text-sm text-fg-muted">
        Loading action…
      </div>
    );
  }
  if (actionQuery.isError || !actionQuery.data) {
    return (
      <div className="card p-6 text-sm text-danger">
        Action <span className="font-data">{id}</span> not found.
      </div>
    );
  }

  const action = actionQuery.data;
  const validation = validationQuery.data;

  const safeModeHeld = Boolean(
    safeMode.data?.system.active ||
      safeMode.data?.categories[`category:${action.category}`]?.active
  );
  const confirmRequired = Boolean(
    settingsQuery.data?.confirm_to_promote[action.category] ??
      settingsQuery.data?.confirm_to_promote._default
  );
  const overallPass = validation?.overall_status === "PASS";

  const canPromote =
    action.state === "VALIDATING" && overallPass && action.eligible;
  const canRevert =
    action.state === "STAGED" ||
    action.state === "VALIDATING" ||
    action.state === "FAILED" ||
    action.state === "EXPIRED" ||
    action.state === "PROMOTED";

  return (
    <div className="flex flex-col gap-section">
      <nav aria-label="Breadcrumb" className="text-xs text-fg-muted">
        <Link href="/actions" className="inline-flex items-center gap-1 hover:text-fg">
          <ArrowLeft aria-hidden className="size-3" />
          Actions
        </Link>
        <ChevronRight aria-hidden className="inline size-3 mx-1" />
        <span className="font-data">{truncId(action.action_id)}</span>
      </nav>

      {/* Header */}
      <header className="card p-5 flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-3 min-w-0">
          <div className="flex flex-wrap items-baseline gap-2">
            <StateBadge state={action.state} />
            <TypeChip type={action.type} />
            <span className="font-data text-xs text-fg-muted">
              {action.category}
            </span>
            <span className="font-data text-2xs text-fg-subtle">
              created {fmtAge(action.created_at)}
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5 text-xs">
            <Field label="Ticket"><CopyableId id={action.ticket_id} /></Field>
            <Field label="Action"><CopyableId id={action.action_id} /></Field>
            <Field label="Target"><span className="font-data text-fg">{action.target}</span></Field>
            <Field label="Artifacts"><span className="font-data text-fg break-all">{action.artifacts_ref}</span></Field>
            <Field label="Revert handle">
              {action.revert_handle_ref ? (
                <span className="font-data text-ok">{action.revert_handle_ref}</span>
              ) : (
                <span className="font-data text-danger">missing — staging blocked</span>
              )}
            </Field>
            <Field label="Creator"><span className="font-data text-fg">{action.actor}</span></Field>
          </div>
        </div>
        <div className="flex flex-col items-end gap-3">
          {action.state === "VALIDATING" && validation && (
            <LoopRing
              windowStart={validation.window_start}
              windowEnd={validation.window_end}
              overallStatus={validation.overall_status}
              size={140}
            />
          )}
          {action.state === "PROMOTED" && (
            <PromotedSummary end={action.rollback_window_end} />
          )}
          <div className="flex gap-2 flex-wrap justify-end">
            <Button
              variant="primary"
              disabled={!canPromote}
              onClick={() => setPromoteOpen(true)}
              aria-disabled={!canPromote}
            >
              <ShieldCheck aria-hidden />
              Promote
            </Button>
            <Button
              variant="destructive"
              disabled={!canRevert || revert.isPending}
              onClick={() => setRevertOpen(true)}
              aria-disabled={!canRevert}
            >
              <Undo2 aria-hidden />
              Revert
            </Button>
          </div>
          {!canPromote && action.state === "VALIDATING" && (
            <p className="text-2xs text-fg-muted text-right max-w-[20ch]">
              {overallPass
                ? "All checks PASS — promote available."
                : "Promote unlocks when all checks PASS."}
            </p>
          )}
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-section">
        {/* Left column: validation + decision */}
        <div className="lg:col-span-2 flex flex-col gap-section">
          {validation ? (
            <section aria-labelledby="checklist-heading">
              <h2 id="checklist-heading" className="sr-only">
                Validation checklist
              </h2>
              <ValidationChecklist
                checks={validation.checks}
                overallStatus={validation.overall_status}
              />
            </section>
          ) : (
            <div className="card p-4 text-xs text-fg-muted">
              No validation window opened yet.
            </div>
          )}
          <section aria-labelledby="decision-heading">
            <h2 id="decision-heading" className="sr-only">
              Promotion decision
            </h2>
            <PromotionDecisionPanel
              overallPass={overallPass}
              safeModeHeld={safeModeHeld}
              confirmRequired={confirmRequired}
            />
          </section>
        </div>

        {/* Right column: lifecycle timeline */}
        <section aria-labelledby="lifecycle-heading" className="flex flex-col gap-3">
          <h2 id="lifecycle-heading" className="text-sm font-medium text-fg">
            Lifecycle
          </h2>
          <div className="card p-4">
            <LifecycleTimeline action={action} />
          </div>
        </section>
      </div>

      {/* Promote dialog */}
      <ConfirmActionDialog
        open={promoteOpen}
        onOpenChange={setPromoteOpen}
        intent="promote"
        title="Promote to production"
        consequence={
          <>
            This is the only call site that applies a mitigation to production.
            After promote, a {fmtDurationHours(
              settingsQuery.data?.rollback_window_seconds ?? 86_400
            )} rollback window opens.
          </>
        }
        facts={[
          { label: "Target", value: action.target },
          { label: "Category", value: action.category },
          { label: "Validation", value: validation?.validation_id ?? "—" },
        ]}
        onConfirm={async () => {
          await promote.mutateAsync();
        }}
        disabledReason={
          safeModeHeld
            ? "Safe Mode is held for this scope — Promote remains available but is the gate the operator explicitly chose."
            : null
        }
      />

      {/* Revert dialog */}
      <ConfirmActionDialog
        open={revertOpen}
        onOpenChange={setRevertOpen}
        intent="revert"
        title={
          action.state === "PROMOTED" ? "Roll back from production" : "Revert"
        }
        consequence={
          action.state === "PROMOTED" ? (
            <>
              Roll back the production change using its registered revert handle.
              Idempotent — replays on terminal state are safe.
            </>
          ) : (
            <>
              Tear down the staging deployment for this action. Idempotent.
            </>
          )
        }
        facts={[
          { label: "Target", value: action.target },
          { label: "State", value: action.state },
          {
            label: "Revert handle",
            value: action.revert_handle_ref ?? "(none)",
          },
        ]}
        requireReason
        onConfirm={async (reason) => {
          await revert.mutateAsync(reason);
        }}
      />
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline gap-2 min-w-0">
      <span className="text-fg-muted shrink-0">{label}</span>
      <span className="min-w-0 truncate">{children}</span>
    </div>
  );
}

function TypeChip({ type }: { type: "code" | "config" }) {
  const Icon = type === "code" ? GitBranch : Boxes;
  return (
    <span className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-2xs font-data uppercase tracking-wider text-fg-muted">
      <Icon className="size-3" aria-hidden />
      {type}
    </span>
  );
}

function PromotedSummary({ end }: { end: string | null }) {
  const { remaining_s } = useCountdown(end);
  return (
    <div className="card p-3 flex flex-col items-end gap-1">
      <span className="text-2xs uppercase tracking-wider text-fg-muted">
        Rollback window
      </span>
      <span className="font-data text-xl text-warn">
        {end ? fmtRemaining(remaining_s) : "—"}
      </span>
      <span className="text-2xs text-fg-muted">
        revert remains available
      </span>
    </div>
  );
}

function fmtDurationHours(seconds: number): string {
  const h = Math.round(seconds / 3600);
  return `${h}-hour`;
}
