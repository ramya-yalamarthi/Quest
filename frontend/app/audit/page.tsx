"use client";

import { Suspense, useMemo } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getApi } from "@/lib/api";
import type { AuditRow } from "@/lib/api/types";
import { StateBadge } from "@/components/StateBadge";
import { ActorTag } from "@/components/LifecycleTimeline";
import { CopyableId } from "@/components/CopyableId";
import { Button } from "@/components/ui/Button";
import { fmtClockUtc } from "@/lib/util/format";
import { cn } from "@/lib/util/cn";
import { Download, Search } from "lucide-react";

const TYPE_OPTIONS: AuditRow["transition_type"][] = [
  "state",
  "safe_mode",
  "guard",
  "config",
  "system",
];

export default function AuditPageRoute() {
  return (
    <Suspense
      fallback={
        <div className="card p-6 animate-pulse text-sm text-fg-muted">
          Loading…
        </div>
      }
    >
      <AuditPage />
    </Suspense>
  );
}

function AuditPage() {
  const api = getApi();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const actionId = params.get("action_id") ?? undefined;
  const type =
    (params.get("type") as AuditRow["transition_type"] | null) ?? undefined;
  const q = params.get("q") ?? "";

  const { data, isLoading } = useQuery({
    queryKey: ["audit", { actionId, type, q, limit: 1000 }],
    queryFn: () =>
      api.listAudit({
        action_id: actionId,
        transition_type: type,
        q: q || undefined,
        limit: 1000,
      }),
    refetchInterval: 30_000,
  });

  const rows = data ?? [];

  const summary = useMemo(() => {
    const byActor = new Map<string, number>();
    let states = 0,
      safeMode = 0;
    for (const r of rows) {
      byActor.set(r.actor, (byActor.get(r.actor) ?? 0) + 1);
      if (r.transition_type === "state") states++;
      if (r.transition_type === "safe_mode") safeMode++;
    }
    return { byActor, states, safeMode };
  }, [rows]);

  function setParam(key: string, value: string | null) {
    const next = new URLSearchParams(params.toString());
    if (value === null || value === "") next.delete(key);
    else next.set(key, value);
    router.replace(`${pathname}?${next.toString()}`);
  }

  function exportCsv() {
    const headers = [
      "audit_id",
      "ts",
      "action_id",
      "ticket_id",
      "actor",
      "transition_type",
      "from_state",
      "to_state",
      "detail",
    ];
    const lines = [headers.join(",")];
    for (const r of rows) {
      lines.push(
        [
          r.audit_id,
          r.ts,
          r.action_id,
          r.ticket_id ?? "",
          r.actor,
          r.transition_type,
          r.from_state ?? "",
          r.to_state ?? "",
          JSON.stringify(r.detail),
        ]
          .map((v) => csvCell(String(v)))
          .join(",")
      );
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex flex-col gap-section">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-fg">Audit log</h1>
          <p className="text-xs text-fg-muted mt-1">
            Append-only record of every state transition, Safe Mode toggle,
            guard trip, and config change. Rows are immutable at the DB level
            (write-trigger + REVOKE grants).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search
              aria-hidden
              className="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-fg-muted"
            />
            <input
              type="search"
              defaultValue={q}
              placeholder="Search detail / actor / state"
              onChange={(e) => setParam("q", e.target.value)}
              className="rounded-md border border-border bg-surface pl-9 pr-3 py-2 text-sm w-72 focus:outline-none focus:ring-2 focus:ring-accent/40"
              aria-label="Search audit log"
            />
          </div>
          <Button variant="secondary" size="sm" onClick={exportCsv}>
            <Download aria-hidden />
            Export CSV
          </Button>
        </div>
      </header>

      {actionId && (
        <ReconstructPanel actionId={actionId} rows={rows} />
      )}

      <section>
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <span className="text-2xs uppercase tracking-wider text-fg-muted">
            Type
          </span>
          <button
            type="button"
            onClick={() => setParam("type", null)}
            aria-pressed={!type}
            className={cn(
              "rounded border px-2 py-0.5 text-2xs font-data uppercase tracking-wider transition-colors",
              !type ? "border-accent bg-accent/10" : "border-border text-fg-muted hover:bg-surface-2"
            )}
          >
            all ({rows.length})
          </button>
          {TYPE_OPTIONS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setParam("type", t === type ? null : t)}
              aria-pressed={type === t}
              className={cn(
                "rounded border px-2 py-0.5 text-2xs font-data uppercase tracking-wider transition-colors",
                type === t
                  ? "border-accent bg-accent/10 text-fg"
                  : "border-border text-fg-muted hover:bg-surface-2"
              )}
            >
              {t}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="card p-6 animate-pulse text-sm text-fg-muted">
            Loading…
          </div>
        ) : rows.length === 0 ? (
          <div className="card p-6 text-sm text-fg-muted text-center">
            No audit rows match these filters.
          </div>
        ) : (
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-surface-2 text-2xs uppercase tracking-wider text-fg-muted">
                  <tr>
                    <th scope="col" className="px-3 py-2 text-left">When (UTC)</th>
                    <th scope="col" className="px-3 py-2 text-left">Type</th>
                    <th scope="col" className="px-3 py-2 text-left">From → To</th>
                    <th scope="col" className="px-3 py-2 text-left">Action</th>
                    <th scope="col" className="px-3 py-2 text-left">Actor</th>
                    <th scope="col" className="px-3 py-2 text-left">Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr
                      key={r.audit_id}
                      className={cn(
                        "border-t border-border align-top",
                        i % 2 === 1 && "bg-surface-2/20"
                      )}
                    >
                      <td className="px-3 py-2 font-data whitespace-nowrap text-fg-muted">
                        {fmtClockUtc(r.ts)}
                      </td>
                      <td className="px-3 py-2">
                        <span className="font-data text-2xs uppercase tracking-wider text-fg-muted">
                          {r.transition_type}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <TransitionCell row={r} />
                      </td>
                      <td className="px-3 py-2">
                        {r.action_id &&
                        r.action_id !==
                          "00000000-0000-0000-0000-000000000000" ? (
                          <CopyableId id={r.action_id} />
                        ) : (
                          <span className="text-fg-subtle">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <ActorTag actor={r.actor} />
                      </td>
                      <td className="px-3 py-2 max-w-md">
                        <pre className="font-data text-2xs text-fg-muted whitespace-pre-wrap break-all">
                          {JSON.stringify(r.detail)}
                        </pre>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="border-t border-border px-3 py-2 text-2xs text-fg-muted">
              {rows.length} rows · {summary.states} state · {summary.safeMode}{" "}
              safe_mode · {summary.byActor.size} unique actor
              {summary.byActor.size === 1 ? "" : "s"}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function TransitionCell({ row }: { row: AuditRow }) {
  if (row.transition_type === "state" && row.to_state) {
    const isMitigationState = [
      "DRAFTED",
      "APPROVED",
      "REJECTED",
      "STAGED",
      "VALIDATING",
      "PROMOTED",
      "FAILED",
      "EXPIRED",
      "REVERTED",
      "ROLLEDBACK",
      "CLOSED",
    ].includes(row.to_state);
    if (isMitigationState) {
      return (
        <span className="inline-flex items-center gap-1">
          {row.from_state && (
            <span className="font-data text-2xs text-fg-muted">
              {row.from_state}
            </span>
          )}
          <span className="text-fg-subtle">→</span>
          <StateBadge state={row.to_state as never} size="sm" />
        </span>
      );
    }
  }
  if (row.from_state || row.to_state) {
    return (
      <span className="font-data text-2xs text-fg-muted">
        {row.from_state ?? "—"} → {row.to_state ?? "—"}
      </span>
    );
  }
  return <span className="text-fg-subtle">—</span>;
}

function ReconstructPanel({
  actionId,
  rows,
}: {
  actionId: string;
  rows: AuditRow[];
}) {
  const filtered = rows.filter((r) => r.action_id === actionId);
  return (
    <div className="card p-4 border-accent/40">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium text-fg">
          Reconstruct{" "}
          <span className="font-data text-fg-muted">{actionId}</span>
        </h2>
        <span className="text-2xs text-fg-muted">
          {filtered.length} rows
        </span>
      </div>
      <p className="text-2xs text-fg-muted mt-1">
        Full state machine and side-effect log for one action — replay the rows in
        order to derive its current state. Useful for incident review.
      </p>
    </div>
  );
}

function csvCell(value: string): string {
  if (/[",\n]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}
