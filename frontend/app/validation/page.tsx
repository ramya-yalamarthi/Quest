"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getApi } from "@/lib/api";
import { MitigationActionCard } from "@/components/MitigationActionCard";
import { TelemetryChart } from "@/components/TelemetryChart";

export default function ValidationPage() {
  const api = getApi();

  const actionsQuery = useQuery({
    queryKey: ["actions", { states: ["VALIDATING"] }],
    queryFn: () => api.listActions({ states: ["VALIDATING"], limit: 200 }),
    refetchInterval: 5_000,
  });

  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.getSettings(),
  });

  const validating = actionsQuery.data ?? [];

  const components = useMemo(() => {
    const set = new Set<string>();
    for (const a of validating) {
      const c =
        (a.expected_outcome?.component as string | undefined) ??
        a.target.split("-")[0];
      if (c) set.add(c);
    }
    // Also include any components explicitly bounded by guards
    const bounds = settingsQuery.data?.guards.telemetry_bounds ?? {};
    for (const c of Object.keys(bounds)) set.add(c);
    return [...set];
  }, [validating, settingsQuery.data]);

  return (
    <div className="flex flex-col gap-section">
      <header>
        <h1 className="text-xl font-semibold text-fg">Validation & telemetry</h1>
        <p className="text-xs text-fg-muted mt-1">
          Live 24-hour windows for staged mitigations and the component telemetry
          their bounds-checks read from.
        </p>
      </header>

      <section aria-labelledby="in-flight-heading">
        <header className="flex items-baseline justify-between mb-3">
          <h2 id="in-flight-heading" className="text-sm font-medium text-fg">
            In-flight windows
            <span className="ml-2 text-2xs uppercase tracking-wider text-fg-muted">
              {validating.length} open
            </span>
          </h2>
          <Link
            href="/actions?state=VALIDATING"
            className="text-xs text-fg-muted hover:text-fg"
          >
            View as table →
          </Link>
        </header>
        {validating.length === 0 ? (
          <div className="card p-6 text-sm text-fg-muted text-center">
            No windows are open right now. Stage an Approved action to start one.
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {validating.map((a) => (
              <ValidationCard key={a.action_id} actionId={a.action_id} />
            ))}
          </div>
        )}
      </section>

      <section aria-labelledby="telemetry-heading">
        <header className="flex items-baseline justify-between mb-3">
          <h2 id="telemetry-heading" className="text-sm font-medium text-fg">
            Component telemetry
            <span className="ml-2 text-2xs uppercase tracking-wider text-fg-muted">
              bounds-checked
            </span>
          </h2>
        </header>
        {components.length === 0 ? (
          <div className="card p-6 text-sm text-fg-muted text-center">
            No bounded components yet — configure thresholds in{" "}
            <Link href="/settings" className="text-accent hover:underline">
              settings
            </Link>
            .
          </div>
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            {components.map((c) => (
              <TelemetryChart
                key={c}
                component={c}
                bounds={
                  settingsQuery.data?.guards.telemetry_bounds[c]?.error_rate
                }
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function ValidationCard({ actionId }: { actionId: string }) {
  const api = getApi();
  const actionQuery = useQuery({
    queryKey: ["action", actionId],
    queryFn: () => api.getAction(actionId),
    refetchInterval: 5_000,
  });
  const validationQuery = useQuery({
    queryKey: ["validation", actionId],
    queryFn: () => api.getValidationByActionId(actionId),
    refetchInterval: 2_000,
  });

  if (!actionQuery.data) {
    return <div className="card p-4 animate-pulse min-h-40" aria-hidden />;
  }
  return (
    <MitigationActionCard
      action={actionQuery.data}
      validation={validationQuery.data}
    />
  );
}

