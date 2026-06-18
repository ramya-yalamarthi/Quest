"use client";

import { Suspense, useMemo } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getApi } from "@/lib/api";
import type { MitigationState } from "@/lib/api/types";
import { MITIGATION_STATES } from "@/lib/api/types";
import { ActionsTable } from "@/components/ActionsTable";
import { StateBadge } from "@/components/StateBadge";
import { cn } from "@/lib/util/cn";
import { Search } from "lucide-react";

export default function ActionsPageRoute() {
  return (
    <Suspense
      fallback={
        <div className="card p-6 animate-pulse text-sm text-fg-muted">
          Loading…
        </div>
      }
    >
      <ActionsPage />
    </Suspense>
  );
}

function ActionsPage() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const stateFilter = (params.get("state") as MitigationState | null) ?? null;
  const typeFilter = (params.get("type") as "code" | "config" | null) ?? null;
  const q = params.get("q") ?? "";

  const api = getApi();
  const { data, isLoading } = useQuery({
    queryKey: ["actions", { state: stateFilter, type: typeFilter, q }],
    queryFn: () =>
      api.listActions({
        states: stateFilter ? [stateFilter] : undefined,
        types: typeFilter ? [typeFilter] : undefined,
        q: q || undefined,
        limit: 500,
      }),
  });

  const rows = data ?? [];

  const stateCounts = useMemo(() => {
    const counts = Object.fromEntries(MITIGATION_STATES.map((s) => [s, 0])) as Record<
      MitigationState,
      number
    >;
    for (const a of rows) counts[a.state]++;
    return counts;
  }, [rows]);

  function setParam(key: string, value: string | null) {
    const next = new URLSearchParams(params.toString());
    if (value === null || value === "") next.delete(key);
    else next.set(key, value);
    router.replace(`${pathname}?${next.toString()}`);
  }

  return (
    <div className="flex flex-col gap-section">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-fg">Actions</h1>
          <p className="text-xs text-fg-muted mt-1">
            Every mitigation action and its current position in the staged-rollout pipeline.
          </p>
        </div>
        <div className="relative">
          <Search
            aria-hidden
            className="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-fg-muted"
          />
          <input
            type="search"
            defaultValue={q}
            placeholder="Search ticket / action / target / actor"
            onChange={(e) => setParam("q", e.target.value)}
            className="rounded-md border border-border bg-surface pl-9 pr-3 py-2 text-sm w-72 focus:outline-none focus:ring-2 focus:ring-accent/40"
            aria-label="Search actions"
          />
        </div>
      </header>

      <section aria-labelledby="state-filter">
        <h2 id="state-filter" className="sr-only">
          Filter by state
        </h2>
        <div className="flex flex-wrap gap-2">
          <FilterChip
            label={`All (${rows.length})`}
            active={!stateFilter}
            onClick={() => setParam("state", null)}
          />
          {MITIGATION_STATES.map((s) => {
            const n = stateCounts[s];
            const dim = n === 0 && stateFilter !== s;
            return (
              <button
                key={s}
                type="button"
                onClick={() => setParam("state", s === stateFilter ? null : s)}
                aria-pressed={stateFilter === s}
                className={cn(
                  "inline-flex items-center gap-2 rounded-md border px-2 py-1 transition-colors duration-fast",
                  stateFilter === s
                    ? "border-accent bg-accent/10"
                    : "border-border hover:bg-surface-2",
                  dim && "opacity-50"
                )}
              >
                <StateBadge state={s} size="sm" />
                <span className="font-data text-xs text-fg-muted">{n}</span>
              </button>
            );
          })}
        </div>
      </section>

      <section aria-labelledby="type-filter">
        <h2 id="type-filter" className="sr-only">
          Filter by type
        </h2>
        <div className="flex gap-2 items-center text-xs">
          <span className="text-2xs uppercase tracking-wider text-fg-muted">Type</span>
          {(["code", "config"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setParam("type", t === typeFilter ? null : t)}
              aria-pressed={typeFilter === t}
              className={cn(
                "rounded border px-2 py-0.5 font-data uppercase text-2xs tracking-wider transition-colors duration-fast",
                typeFilter === t
                  ? "border-accent bg-accent/10 text-fg"
                  : "border-border text-fg-muted hover:bg-surface-2"
              )}
            >
              {t}
            </button>
          ))}
        </div>
      </section>

      {isLoading ? (
        <div className="card p-6 text-sm text-fg-muted animate-pulse">Loading…</div>
      ) : (
        <ActionsTable actions={rows} />
      )}
    </div>
  );
}

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-md border px-2 py-1 text-xs transition-colors duration-fast",
        active
          ? "border-accent bg-accent/10 text-fg"
          : "border-border text-fg-muted hover:bg-surface-2"
      )}
    >
      {label}
    </button>
  );
}
