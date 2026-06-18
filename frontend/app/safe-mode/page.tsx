"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getApi } from "@/lib/api";
import type { SafeModeEntry } from "@/lib/api/types";
import { useSafeMode } from "@/lib/hooks/useSafeMode";
import { useGuardStatus } from "@/lib/hooks/useGuardStatus";
import { GuardProximityBar } from "@/components/GuardProximityBar";
import { ActorTag } from "@/components/LifecycleTimeline";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { fmtAge } from "@/lib/util/format";
import { Lock, ShieldCheck, Unlock } from "lucide-react";
import { cn } from "@/lib/util/cn";

export default function SafeModePage() {
  const api = getApi();
  const qc = useQueryClient();
  const safeMode = useSafeMode();
  const guards = useGuardStatus();
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.getSettings(),
  });
  const audit = useQuery({
    queryKey: ["audit", { transition_type: "safe_mode", limit: 50 }],
    queryFn: () =>
      api.listAudit({ transition_type: "safe_mode", limit: 50 }),
    refetchInterval: 30_000,
  });

  const setMutation = useMutation({
    mutationFn: (body: { scope: string; active: boolean; reason: string }) =>
      api.setSafeMode(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["safe-mode"] });
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });

  const [pending, setPending] = useState<{
    scope: string;
    active: boolean;
  } | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const scopes = useMemo(() => {
    if (!safeMode.data) return [];
    const out: { scope: string; entry: SafeModeEntry }[] = [
      { scope: "system", entry: safeMode.data.system },
    ];
    const cats = settings.data?.categories ?? [];
    for (const c of cats) {
      const key = `category:${c}`;
      out.push({
        scope: key,
        entry: safeMode.data.categories[key] ?? {
          scope: key,
          active: false,
          entered_at: null,
          entered_by: null,
          exited_at: null,
          exited_by: null,
          reason: null,
        },
      });
    }
    for (const [key, entry] of Object.entries(safeMode.data.categories)) {
      if (!out.some((o) => o.scope === key)) out.push({ scope: key, entry });
    }
    return out;
  }, [safeMode.data, settings.data]);

  async function confirmToggle() {
    if (!pending) return;
    if (!reason.trim()) {
      setError("A reason is required.");
      return;
    }
    setError(null);
    try {
      await setMutation.mutateAsync({
        scope: pending.scope,
        active: pending.active,
        reason: reason.trim(),
      });
      setPending(null);
      setReason("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    }
  }

  return (
    <div className="flex flex-col gap-section">
      <header>
        <h1 className="text-xl font-semibold text-fg">Safe Mode & guards</h1>
        <p className="text-xs text-fg-muted mt-1">
          When Safe Mode is held, the bot pauses autonomous execution for the
          scope and every action requires a human in the loop. Only humans can
          exit Safe Mode.
        </p>
      </header>

      <section aria-labelledby="posture-heading">
        <h2 id="posture-heading" className="text-sm font-medium text-fg mb-3">
          Posture
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {scopes.map(({ scope, entry }) => (
            <ScopeCard
              key={scope}
              scope={scope}
              entry={entry}
              onToggle={() => setPending({ scope, active: !entry.active })}
            />
          ))}
        </div>
      </section>

      <section aria-labelledby="guards-heading">
        <h2 id="guards-heading" className="text-sm font-medium text-fg mb-3">
          Guard proximity
        </h2>
        {guards.data && guards.data.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {guards.data.map((g) => (
              <div key={g.category} className="card p-4 flex flex-col gap-3">
                <div className="flex items-baseline justify-between">
                  <span className="text-sm font-medium text-fg">
                    {g.category}
                  </span>
                  <span className="text-2xs uppercase tracking-wider text-fg-muted">
                    rolling rates
                  </span>
                </div>
                <div className="grid grid-cols-1 gap-2">
                  {g.rates.map((r) => (
                    <GuardProximityBar
                      key={r.signal}
                      signal={r.signal}
                      rate={r.rate}
                      threshold={r.threshold}
                      samples={r.samples}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="card p-4 text-xs text-fg-muted">
            No guard data yet — waiting for the first sample.
          </div>
        )}
      </section>

      <section aria-labelledby="history-heading">
        <h2 id="history-heading" className="text-sm font-medium text-fg mb-3">
          Recent Safe Mode events
        </h2>
        {audit.data && audit.data.length > 0 ? (
          <ol className="card divide-y divide-border overflow-hidden">
            {audit.data.map((row) => (
              <li key={row.audit_id} className="px-4 py-3 grid gap-1 text-xs">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-2xs font-data uppercase",
                      row.to_state === "ACTIVE"
                        ? "border-warn/40 bg-warn/10 text-warn"
                        : "border-ok/40 bg-ok/10 text-ok"
                    )}
                  >
                    {row.to_state === "ACTIVE" ? (
                      <Lock aria-hidden className="size-3" />
                    ) : (
                      <Unlock aria-hidden className="size-3" />
                    )}
                    {row.to_state}
                  </span>
                  <span className="font-data text-fg-muted">
                    {String(
                      (row.detail as { scope?: string }).scope ?? "system"
                    )}
                  </span>
                  <ActorTag actor={row.actor} />
                  <span className="font-data text-2xs text-fg-subtle ml-auto">
                    {fmtAge(row.ts)}
                  </span>
                </div>
                {(row.detail as { reason?: string }).reason && (
                  <p className="text-fg-muted">
                    {String((row.detail as { reason?: string }).reason)}
                  </p>
                )}
              </li>
            ))}
          </ol>
        ) : (
          <div className="card p-4 text-xs text-fg-muted">
            No Safe Mode events recorded yet.
          </div>
        )}
      </section>

      {/* Toggle dialog */}
      <Dialog
        open={pending !== null}
        onOpenChange={(next) => {
          if (!next) {
            setPending(null);
            setReason("");
            setError(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {pending?.active ? (
                <>
                  <Lock aria-hidden className="size-5 text-warn" />
                  Hold Safe Mode
                </>
              ) : (
                <>
                  <Unlock aria-hidden className="size-5 text-ok" />
                  Exit Safe Mode
                </>
              )}
            </DialogTitle>
            <DialogDescription>
              {pending?.active ? (
                <>
                  Holding <span className="font-data">{pending?.scope}</span>{" "}
                  in Safe Mode pauses autonomous execution and requires explicit
                  human action for every promote.
                </>
              ) : (
                <>
                  Exiting Safe Mode for{" "}
                  <span className="font-data">{pending?.scope}</span> resumes
                  autonomous execution. Only humans can exit — this action
                  records you as the authorizer.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <label className="mt-4 flex flex-col gap-1.5">
            <span className="text-xs text-fg-muted">
              Reason <span className="text-danger" aria-hidden>*</span>
            </span>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              maxLength={500}
              placeholder="Required — appears in the audit log."
              className="rounded-md border border-border bg-surface px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
            />
          </label>
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
              onClick={() => setPending(null)}
              disabled={setMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant={pending?.active ? "destructive" : "primary"}
              onClick={confirmToggle}
              disabled={setMutation.isPending}
            >
              {setMutation.isPending
                ? "Submitting…"
                : pending?.active
                  ? "Hold Safe Mode"
                  : "Exit Safe Mode"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ScopeCard({
  scope,
  entry,
  onToggle,
}: {
  scope: string;
  entry: SafeModeEntry;
  onToggle: () => void;
}) {
  const label =
    scope === "system" ? "System" : scope.replace(/^category:/, "Category — ");
  return (
    <div
      className={cn(
        "card p-4 flex flex-col gap-3",
        entry.active && "border-warn/40"
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-fg">{label}</div>
          <div className="font-data text-2xs text-fg-muted">{scope}</div>
        </div>
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded border px-2 py-0.5 text-2xs font-data uppercase tracking-wider",
            entry.active
              ? "border-warn/50 bg-warn/15 text-warn"
              : "border-ok/40 bg-ok/10 text-ok"
          )}
        >
          {entry.active ? (
            <Lock aria-hidden className="size-3" />
          ) : (
            <ShieldCheck aria-hidden className="size-3" />
          )}
          {entry.active ? "Holding" : "Normal"}
        </span>
      </div>
      <div className="text-2xs text-fg-muted grid grid-cols-2 gap-y-1">
        <span>Entered</span>
        <span className="font-data text-fg">
          {entry.entered_at ? fmtAge(entry.entered_at) : "—"}
        </span>
        <span>By</span>
        <span className="font-data text-fg">{entry.entered_by ?? "—"}</span>
        {entry.exited_at && (
          <>
            <span>Last exit</span>
            <span className="font-data text-fg">{fmtAge(entry.exited_at)}</span>
          </>
        )}
      </div>
      {entry.reason && (
        <p className="text-2xs text-fg-muted border-l-2 border-border-strong pl-2">
          {entry.reason}
        </p>
      )}
      <Button
        size="sm"
        variant={entry.active ? "primary" : "destructive"}
        onClick={onToggle}
      >
        {entry.active ? "Exit Safe Mode" : "Hold Safe Mode"}
      </Button>
    </div>
  );
}
