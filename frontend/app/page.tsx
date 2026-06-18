"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getApi } from "@/lib/api";
import type {
  KpiSnapshot,
  MitigationAction,
  MitigationState,
  SafeModeView,
} from "@/lib/api/types";
import { MITIGATION_STATES } from "@/lib/api/types";
import { StateBadge } from "@/components/StateBadge";
import { KpiBullet } from "@/components/KpiBullet";
import { MitigationActionCard } from "@/components/MitigationActionCard";
import { useRealtime } from "@/lib/hooks/useRealtime";
import { useSafeMode } from "@/lib/hooks/useSafeMode";
import { ActorTag } from "@/components/LifecycleTimeline";
import { fmtAge } from "@/lib/util/format";
import { cn } from "@/lib/util/cn";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  PauseCircle,
  PlayCircle,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";

const PIPELINE_ORDER: MitigationState[] = [
  "APPROVED",
  "STAGED",
  "VALIDATING",
  "PROMOTED",
  "FAILED",
  "EXPIRED",
  "REVERTED",
  "ROLLEDBACK",
];

export default function OverviewPage() {
  const api = getApi();

  const actionsQuery = useQuery({
    queryKey: ["actions", { limit: 200 }],
    queryFn: () => api.listActions({ limit: 200 }),
    refetchInterval: 15_000,
  });
  const kpisQuery = useQuery({
    queryKey: ["kpis", { windowSeconds: 86_400 }],
    queryFn: () => api.getKpis(86_400),
    refetchInterval: 15_000,
  });
  const safeMode = useSafeMode();
  const { events, status, pause, resume } = useRealtime();

  const actions = actionsQuery.data ?? [];
  const kpis = kpisQuery.data;

  const stateCounts = useMemo(() => {
    const counts = Object.fromEntries(
      MITIGATION_STATES.map((s) => [s, 0])
    ) as Record<MitigationState, number>;
    for (const a of actions) counts[a.state]++;
    return counts;
  }, [actions]);

  const needsAttention = useMemo(
    () => deriveNeedsAttention(actions, safeMode.data),
    [actions, safeMode.data]
  );

  return (
    <div className="flex flex-col gap-section">
      {/* Posture strip */}
      <PostureStrip
        kpis={kpis}
        actions={actions}
        safeMode={safeMode.data}
        streamConnected={status.connected}
        lastEventAt={status.lastEventAt}
      />

      {/* Lifecycle pipeline */}
      <section aria-labelledby="pipeline-heading">
        <SectionHeader id="pipeline-heading" title="Lifecycle pipeline" />
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
          {PIPELINE_ORDER.map((s) => (
            <Link
              key={s}
              href={`/actions?state=${s}`}
              className={cn(
                "card card-hover p-3 flex flex-col gap-1",
                stateCounts[s] === 0 && "opacity-60"
              )}
            >
              <StateBadge state={s} size="sm" />
              <span className="font-data text-xl text-fg">{stateCounts[s]}</span>
            </Link>
          ))}
        </div>
      </section>

      {/* KPI row */}
      <section aria-labelledby="kpi-heading">
        <SectionHeader
          id="kpi-heading"
          title="KPIs"
          hint="rolling 24h window"
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <KpiBullet
            label="Validation pass rate"
            value={kpis?.validation_pass_rate ?? 0}
            format="rate"
            max={1}
            sparkline={kpis?.sparklines?.pass}
            large
          />
          <KpiBullet
            label="Rollback rate"
            value={kpis?.rollback_rate ?? 0}
            threshold={0.1}
            format="rate"
            max={0.2}
            large
          />
          <KpiBullet
            label="Auto-reverted (24h)"
            value={kpis?.auto_reverted_count_in_window ?? 0}
            format="count"
            max={Math.max(
              5,
              (kpis?.auto_reverted_count_in_window ?? 0) + 2
            )}
            large
          />
          <KpiBullet
            label="Mean time in validation"
            value={kpis?.mean_time_in_validation_seconds ?? 0}
            format="seconds"
            max={Math.max(
              86_400,
              kpis?.mean_time_in_validation_seconds ?? 0
            )}
            large
          />
        </div>
      </section>

      {/* Needs attention + Live feed */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-section">
        <section
          aria-labelledby="needs-attention-heading"
          className="lg:col-span-2 flex flex-col gap-3"
        >
          <SectionHeader
            id="needs-attention-heading"
            title="Needs attention"
            hint={`${needsAttention.length} items`}
            action={
              <Link
                href="/actions"
                className="inline-flex items-center gap-1 text-xs text-fg-muted hover:text-fg transition-colors"
              >
                View all actions <ArrowRight aria-hidden className="size-3.5" />
              </Link>
            }
          />
          {actionsQuery.isLoading ? (
            <SkeletonCards />
          ) : needsAttention.length === 0 ? (
            <EmptyState
              icon={Activity}
              title="Nothing to chase right now"
              body="No actions are blocked or near a guard threshold. The pipeline is quiet."
            />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {needsAttention.slice(0, 4).map((a) => (
                <MitigationActionCard key={a.action_id} action={a} />
              ))}
            </div>
          )}
        </section>

        <section
          aria-labelledby="live-feed-heading"
          className="flex flex-col gap-3"
        >
          <SectionHeader
            id="live-feed-heading"
            title="Live feed"
            action={
              <button
                type="button"
                onClick={status.paused ? resume : pause}
                className="inline-flex items-center gap-1 text-xs text-fg-muted hover:text-fg transition-colors"
                aria-pressed={status.paused}
              >
                {status.paused ? (
                  <>
                    <PlayCircle aria-hidden className="size-3.5" /> Resume
                  </>
                ) : (
                  <>
                    <PauseCircle aria-hidden className="size-3.5" /> Pause
                  </>
                )}
              </button>
            }
          />
          <LiveFeed events={events} paused={status.paused} />
        </section>
      </div>
    </div>
  );
}

function SectionHeader({
  id,
  title,
  hint,
  action,
}: {
  id?: string;
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 mb-3">
      <h2 id={id} className="text-sm font-medium text-fg">
        {title}
        {hint && (
          <span className="ml-2 text-2xs uppercase tracking-wider text-fg-muted">
            {hint}
          </span>
        )}
      </h2>
      {action}
    </div>
  );
}

function PostureStrip({
  kpis,
  actions,
  safeMode,
  streamConnected,
  lastEventAt,
}: {
  kpis?: KpiSnapshot;
  actions: MitigationAction[];
  safeMode?: SafeModeView;
  streamConnected: boolean;
  lastEventAt: number | null;
}) {
  const validating = actions.filter((a) => a.state === "VALIDATING").length;
  const heldScopes = safeMode
    ? [
        ...(safeMode.system.active ? ["system"] : []),
        ...Object.entries(safeMode.categories)
          .filter(([, e]) => e.active)
          .map(([scope]) => scope),
      ]
    : [];
  const failRate = kpis?.validation_fail_rate ?? 0;
  const rollbackRate = kpis?.rollback_rate ?? 0;

  return (
    <div className="card p-4 grid grid-cols-1 md:grid-cols-4 gap-4">
      <PostureCell
        label="Safe Mode"
        value={
          heldScopes.length === 0
            ? "Off"
            : heldScopes.length === 1
              ? heldScopes[0]
              : `${heldScopes.length} scopes`
        }
        tone={heldScopes.length === 0 ? "ok" : "warn"}
        hint={
          heldScopes.length === 0
            ? "No human-gating active"
            : "Human confirm required"
        }
        icon={ShieldAlert}
      />
      <PostureCell
        label="In validation"
        value={`${validating}`}
        tone={validating > 0 ? "info" : "muted"}
        hint={validating === 1 ? "1 window open" : `${validating} windows open`}
      />
      <PostureCell
        label="Validation fail rate"
        value={`${(failRate * 100).toFixed(1)}%`}
        tone={failRate >= 0.2 ? "danger" : failRate >= 0.1 ? "warn" : "ok"}
        hint="rolling window"
      />
      <PostureCell
        label="Realtime"
        value={streamConnected ? "Live" : "Stale"}
        tone={streamConnected ? "ok" : "warn"}
        hint={
          lastEventAt
            ? `last event ${fmtAge(new Date(lastEventAt).toISOString())}`
            : "awaiting events"
        }
      />
      {/* Hide-on-mobile second-line: rollback rate appended */}
      <span className="sr-only">
        Rollback rate {(rollbackRate * 100).toFixed(1)}%
      </span>
    </div>
  );
}

function PostureCell({
  label,
  value,
  hint,
  tone,
  icon: Icon,
}: {
  label: string;
  value: string;
  hint?: string;
  tone: "ok" | "info" | "warn" | "danger" | "muted";
  icon?: LucideIcon;
}) {
  const toneCls = {
    ok: "text-ok",
    info: "text-info",
    warn: "text-warn",
    danger: "text-danger",
    muted: "text-fg-muted",
  }[tone];
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5 text-2xs uppercase tracking-wider text-fg-muted">
        {Icon && <Icon aria-hidden className="size-3.5" />}
        {label}
      </div>
      <div className={cn("font-data text-lg font-semibold", toneCls)}>
        {value}
      </div>
      {hint && <span className="text-2xs text-fg-subtle">{hint}</span>}
    </div>
  );
}

function deriveNeedsAttention(
  actions: MitigationAction[],
  safeMode?: SafeModeView
): MitigationAction[] {
  const heldCategories = new Set(
    safeMode
      ? Object.entries(safeMode.categories)
          .filter(([, e]) => e.active)
          .map(([scope]) => scope.replace(/^category:/, ""))
      : []
  );
  const score = (a: MitigationAction) => {
    if (a.state === "VALIDATING") {
      return heldCategories.has(a.category) ? 30 : 20;
    }
    if (a.state === "PROMOTED") return 25; // in rollback window
    if (a.state === "FAILED") return 18;
    if (a.state === "EXPIRED") return 15;
    return 0;
  };
  return [...actions]
    .filter((a) => score(a) > 0)
    .sort((a, b) => score(b) - score(a))
    .slice(0, 8);
}

function LiveFeed({
  events,
  paused,
}: {
  events: ReturnType<typeof useRealtime>["events"];
  paused: boolean;
}) {
  if (paused) {
    return (
      <div className="card p-4 text-xs text-fg-muted flex items-center gap-2">
        <PauseCircle aria-hidden className="size-4" /> Feed paused — new events
        will resume on click.
      </div>
    );
  }
  if (events.length === 0) {
    return (
      <div className="card p-4 text-xs text-fg-muted">
        Quiet — no events in the last minute.
      </div>
    );
  }
  return (
    <ol
      role="log"
      aria-live="polite"
      aria-relevant="additions"
      className="card divide-y divide-border overflow-hidden max-h-[640px] overflow-y-auto"
    >
      {events.slice(0, 60).map((e, i) => (
        <li key={`${e.ts}-${i}`} className="px-3 py-2 grid gap-1 text-xs">
          <FeedEvent event={e} />
        </li>
      ))}
    </ol>
  );
}

function FeedEvent({
  event,
}: {
  event: ReturnType<typeof useRealtime>["events"][number];
}) {
  switch (event.type) {
    case "state_transition":
      return (
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-data text-2xs text-fg-subtle shrink-0">
            {fmtAge(event.ts)}
          </span>
          {event.from && (
            <>
              <StateBadge state={event.from} size="sm" />
              <ArrowRight aria-hidden className="size-3 text-fg-subtle" />
            </>
          )}
          <StateBadge state={event.to} size="sm" />
          <ActorTag actor={event.actor} />
        </div>
      );
    case "validation_update":
      return (
        <div className="flex items-center gap-2 text-fg-muted">
          <span className="font-data text-2xs text-fg-subtle shrink-0">
            {fmtAge(event.ts)}
          </span>
          <span>Validation {event.overall_status.toLowerCase()}</span>
          <span className="font-data text-2xs text-fg-subtle">
            {Math.floor(event.time_remaining_seconds / 60)}m remaining
          </span>
        </div>
      );
    case "safe_mode_change":
      return (
        <div className="flex items-center gap-2">
          <span className="font-data text-2xs text-fg-subtle shrink-0">
            {fmtAge(event.ts)}
          </span>
          <ShieldAlert
            aria-hidden
            className={cn(
              "size-3.5",
              event.active ? "text-warn" : "text-fg-muted"
            )}
          />
          <span className="text-fg">
            Safe Mode {event.active ? "entered" : "cleared"}
          </span>
          <span className="font-data text-2xs text-fg-muted">{event.scope}</span>
          <ActorTag actor={event.actor} />
        </div>
      );
    case "guard_trip":
      return (
        <div className="flex items-center gap-2">
          <span className="font-data text-2xs text-fg-subtle shrink-0">
            {fmtAge(event.ts)}
          </span>
          <AlertTriangle aria-hidden className="size-3.5 text-danger" />
          <span className="text-fg">
            Guard {event.signal} crossed threshold
          </span>
          <span className="font-data text-2xs text-fg-muted">
            {(event.value * 100).toFixed(1)}% / {(event.threshold * 100).toFixed(1)}%
          </span>
        </div>
      );
    case "notification":
      return (
        <div className="flex items-center gap-2 text-fg-muted">
          <span className="font-data text-2xs text-fg-subtle shrink-0">
            {fmtAge(event.ts)}
          </span>
          <span className="text-fg">{event.triggering}</span>
          {event.resulting_state && (
            <span className="font-data text-2xs">
              → {event.resulting_state}
            </span>
          )}
        </div>
      );
  }
}

function SkeletonCards() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="card p-4 animate-pulse min-h-32" />
      ))}
    </div>
  );
}

function EmptyState({
  icon: Icon,
  title,
  body,
}: {
  icon: LucideIcon;
  title: string;
  body: string;
}) {
  return (
    <div className="card p-6 flex flex-col items-center justify-center text-center gap-2">
      <Icon aria-hidden className="size-6 text-fg-muted" />
      <div className="text-sm font-medium text-fg">{title}</div>
      <div className="text-xs text-fg-muted max-w-xs">{body}</div>
    </div>
  );
}
