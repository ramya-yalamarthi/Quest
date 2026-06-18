"use client";

/**
 * MitigationActionCard — the Vercel "deployment card" analog.
 *
 * Dense card with state badge, ids, type chip, target, category,
 * created-relative, and (when Validating) the LoopRing + per-check strip.
 * When Promoted, shows the rollback-window countdown. Primary action
 * contextual to state.
 */

import Link from "next/link";
import type { MitigationAction, Validation } from "@/lib/api/types";
import { StateBadge } from "./StateBadge";
import { LoopRing } from "./LoopRing";
import { CopyableId } from "./CopyableId";
import { ActorTag } from "./LifecycleTimeline";
import { cn } from "@/lib/util/cn";
import { fmtAge, fmtPct } from "@/lib/util/format";
import { fmtRemaining, useCountdown } from "@/lib/hooks/useCountdown";
import { Check, X, CircleDashed, ChevronRight, GitBranch, Boxes } from "lucide-react";

export function MitigationActionCard({
  action,
  validation,
  className,
}: {
  action: MitigationAction;
  validation?: Validation | null;
  className?: string;
}) {
  const isValidating = action.state === "VALIDATING";
  const isPromoted = action.state === "PROMOTED";
  return (
    <article
      className={cn(
        "card p-4 grid gap-3 grid-cols-[1fr_auto] hover:bg-surface-2 transition-colors duration-fast",
        className
      )}
      aria-label={`Mitigation action ${action.action_id}`}
    >
      <div className="flex flex-col gap-3 min-w-0">
        <div className="flex flex-wrap items-baseline gap-2">
          <StateBadge state={action.state} />
          <TypeChip type={action.type} />
          <span className="font-data text-2xs text-fg-muted">
            {action.category}
          </span>
          <span className="font-data text-2xs text-fg-subtle ml-auto">
            {fmtAge(action.created_at)}
          </span>
        </div>
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-fg-muted">Ticket</span>
            <CopyableId id={action.ticket_id} />
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-fg-muted">Action</span>
            <CopyableId id={action.action_id} />
          </div>
          <div className="flex items-center gap-2 text-xs min-w-0">
            <span className="text-fg-muted shrink-0">Target</span>
            <span className="font-data text-fg truncate" title={action.target}>
              {action.target}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2 mt-1">
          <ActorTag actor={action.actor} />
          {isPromoted && action.rollback_window_end && (
            <RollbackBadge end={action.rollback_window_end} />
          )}
        </div>
      </div>

      {/* Right column — loop ring when Validating, check strip below */}
      <div className="flex flex-col items-end gap-2">
        {isValidating && validation ? (
          <>
            <LoopRing
              windowStart={validation.window_start}
              windowEnd={validation.window_end}
              overallStatus={validation.overall_status}
              size={96}
              showLabel
            />
            <CheckStrip checks={validation.checks} />
          </>
        ) : (
          <Link
            href={`/actions/${action.action_id}`}
            className="inline-flex items-center gap-1 text-xs text-accent hover:underline"
          >
            Inspect <ChevronRight className="size-3.5" aria-hidden />
          </Link>
        )}
      </div>
    </article>
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

function CheckStrip({ checks }: { checks: Validation["checks"] }) {
  return (
    <ol
      className="flex items-center gap-1"
      aria-label={`Check status: ${checks.map((c) => `${c.name} ${c.status}`).join(", ")}`}
    >
      {checks.map((c) => (
        <li
          key={c.name}
          className={cn(
            "inline-flex size-5 items-center justify-center rounded-full border",
            c.status === "PASS"
              ? "border-ok/40 bg-ok/10 text-ok"
              : c.status === "FAIL"
              ? "border-danger/40 bg-danger/10 text-danger"
              : "border-warn/40 bg-warn/5 border-dashed text-warn"
          )}
          title={`${c.name}: ${c.status}`}
        >
          {c.status === "PASS" ? (
            <Check className="size-3" aria-hidden strokeWidth={2.5} />
          ) : c.status === "FAIL" ? (
            <X className="size-3" aria-hidden strokeWidth={2.5} />
          ) : (
            <CircleDashed className="size-3" aria-hidden strokeWidth={2.5} />
          )}
        </li>
      ))}
    </ol>
  );
}

function RollbackBadge({ end }: { end: string }) {
  const { remaining_s } = useCountdown(end);
  return (
    <span className="inline-flex items-center gap-1.5 rounded border border-warn/30 bg-warn/5 px-1.5 py-0.5 text-2xs font-data text-warn">
      Rollback window: {fmtRemaining(remaining_s)}
    </span>
  );
}
