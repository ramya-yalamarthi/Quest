"use client";

/**
 * LifecycleTimeline — the state machine made visible.
 *
 * Vertical stepper of every transition the action has been through, with
 * timestamp, actor, and reason. The current state is emphasized; terminal
 * states close the spine with a doubled rail so it's obvious the action
 * cannot move further.
 */

import { cn } from "@/lib/util/cn";
import type { MitigationAction, StateHistoryEntry } from "@/lib/api/types";
import { TERMINAL_STATES } from "@/lib/api/types";
import { StateBadge } from "./StateBadge";
import { Dot } from "lucide-react";

export function LifecycleTimeline({ action }: { action: MitigationAction }) {
  const entries = action.state_history;
  return (
    <ol className="relative" aria-label="State history">
      {/* Vertical spine */}
      <span
        aria-hidden
        className="absolute left-[14px] top-2 bottom-2 w-px bg-border-strong"
      />
      {entries.map((e, i) => {
        const isCurrent = i === entries.length - 1;
        const isTerminal = isCurrent && TERMINAL_STATES.has(e.to as never);
        return (
          <li
            key={i}
            className={cn(
              "relative pl-10 pb-5 last:pb-0",
              isCurrent ? "" : "opacity-90"
            )}
          >
            <span
              aria-hidden
              className={cn(
                "absolute left-[6px] top-1.5 size-4 rounded-full border-2 bg-bg",
                isCurrent
                  ? "border-accent"
                  : "border-border-strong",
                isTerminal && "ring-2 ring-accent/40"
              )}
            />
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <StateBadge state={e.to as never} size="sm" />
              <ActorTag actor={e.actor} />
              <time
                dateTime={e.timestamp}
                className="font-data text-2xs text-fg-muted"
              >
                {new Date(e.timestamp).toLocaleString(undefined, {
                  hour12: false,
                })}
              </time>
            </div>
            {e.detail && (
              <p className="mt-1 text-xs text-fg-muted">{e.detail}</p>
            )}
            {e.from && (
              <p className="mt-0.5 text-2xs text-fg-subtle">
                <span aria-hidden>
                  <Dot className="inline size-3" />
                </span>
                Previous: {e.from}
              </p>
            )}
          </li>
        );
      })}
      {/* Terminal cap when the action can move no further */}
      {entries.length > 0 &&
        TERMINAL_STATES.has(entries[entries.length - 1].to as never) && (
          <li aria-hidden className="relative pl-10">
            <span className="absolute left-[10px] top-0 size-2 rounded-full bg-accent" />
            <p className="text-2xs uppercase tracking-wider text-fg-subtle">
              Lifecycle closed
            </p>
          </li>
        )}
    </ol>
  );
}

export function ActorTag({ actor }: { actor: string }) {
  // human:<id> vs guard:<signal> vs system — each gets a distinct shape.
  const isHuman = actor.startsWith("human:");
  const isGuard = actor.startsWith("guard:");
  const label = actor.split(":").slice(1).join(":") || actor;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-medium",
        isHuman
          ? "bg-info/10 text-info border border-info/30"
          : isGuard
          ? "bg-halt/10 text-halt border border-halt/40"
          : "bg-surface-2 text-fg-muted border border-border"
      )}
      title={actor}
    >
      <span className="font-data uppercase">
        {isHuman ? "human" : isGuard ? "guard" : "system"}
      </span>
      <span className="font-data text-fg">{label || actor}</span>
    </span>
  );
}
