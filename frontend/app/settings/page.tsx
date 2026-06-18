"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getApi } from "@/lib/api";
import type { SettingsPayload } from "@/lib/api/types";
import { Button } from "@/components/ui/Button";
import { CheckCircle2, RotateCcw } from "lucide-react";
import { cn } from "@/lib/util/cn";

export default function SettingsPage() {
  const api = getApi();
  const qc = useQueryClient();

  const { data: server } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.getSettings(),
  });

  const [draft, setDraft] = useState<SettingsPayload | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    if (server && !draft) setDraft(structuredClone(server));
  }, [server, draft]);

  const save = useMutation({
    mutationFn: (body: Partial<SettingsPayload>) => api.updateSettings(body),
    onSuccess: (next) => {
      qc.setQueryData(["settings"], next);
      setSavedAt(Date.now());
      setDraft(structuredClone(next));
    },
  });

  if (!draft || !server) {
    return (
      <div className="card p-6 animate-pulse text-sm text-fg-muted">
        Loading settings…
      </div>
    );
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(server);

  function update<K extends keyof SettingsPayload>(
    key: K,
    value: SettingsPayload[K]
  ) {
    setDraft((d) => (d ? { ...d, [key]: value } : d));
  }

  return (
    <div className="flex flex-col gap-section">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-fg">Settings</h1>
          <p className="text-xs text-fg-muted mt-1">
            Window durations, confirm-to-promote, notification routes, and
            guard thresholds. Changes apply on save; the backend hot-reloads.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {savedAt && !dirty && (
            <span className="inline-flex items-center gap-1 text-2xs text-ok">
              <CheckCircle2 aria-hidden className="size-3" /> Saved
            </span>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setDraft(structuredClone(server))}
            disabled={!dirty || save.isPending}
          >
            <RotateCcw aria-hidden />
            Discard
          </Button>
          <Button
            size="sm"
            onClick={() => save.mutate(draft)}
            disabled={!dirty || save.isPending}
          >
            {save.isPending ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </header>

      <SettingsGroup
        title="Windows"
        body="How long mitigations spend in validation, and how long after promote they remain reversible."
      >
        <Field label="Validation window">
          <DurationInput
            seconds={draft.validation_window_seconds}
            onChange={(s) => update("validation_window_seconds", s)}
          />
        </Field>
        <Field label="Rollback window">
          <DurationInput
            seconds={draft.rollback_window_seconds}
            onChange={(s) => update("rollback_window_seconds", s)}
          />
        </Field>
      </SettingsGroup>

      <SettingsGroup
        title="Confirm-to-promote"
        body="When held, the engineer must explicitly confirm to apply a passed mitigation to production. The default applies to any category without its own override."
      >
        <ConfirmRow
          label="Default"
          checked={draft.confirm_to_promote._default ?? true}
          onChange={(v) =>
            update("confirm_to_promote", {
              ...draft.confirm_to_promote,
              _default: v,
            })
          }
        />
        {draft.categories.map((c) => (
          <ConfirmRow
            key={c}
            label={c}
            checked={draft.confirm_to_promote[c] ?? draft.confirm_to_promote._default ?? true}
            onChange={(v) =>
              update("confirm_to_promote", {
                ...draft.confirm_to_promote,
                [c]: v,
              })
            }
          />
        ))}
      </SettingsGroup>

      <SettingsGroup
        title="Guard thresholds"
        body="When the rolling rate of any signal crosses its threshold (and minimum samples are met), Safe Mode is automatically held for the category."
      >
        <Field label="Validation failure rate">
          <RateInput
            value={draft.guards.validation_failure_rate}
            onChange={(v) =>
              update("guards", { ...draft.guards, validation_failure_rate: v })
            }
          />
        </Field>
        <Field label="Rollback rate">
          <RateInput
            value={draft.guards.rollback_rate}
            onChange={(v) =>
              update("guards", { ...draft.guards, rollback_rate: v })
            }
          />
        </Field>
        <Field label="Decline rate">
          <RateInput
            value={draft.guards.decline_rate}
            onChange={(v) =>
              update("guards", { ...draft.guards, decline_rate: v })
            }
          />
        </Field>
        <Field label="Rolling window">
          <DurationInput
            seconds={draft.guards.rolling_window_seconds}
            onChange={(s) =>
              update("guards", { ...draft.guards, rolling_window_seconds: s })
            }
          />
        </Field>
        <Field label="Minimum samples">
          <input
            type="number"
            value={draft.guards.min_samples}
            min={1}
            onChange={(e) =>
              update("guards", {
                ...draft.guards,
                min_samples: Math.max(1, parseInt(e.target.value || "1", 10)),
              })
            }
            className="rounded-md border border-border bg-surface px-2 py-1 font-data text-sm w-24 focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
        </Field>
      </SettingsGroup>

      <SettingsGroup
        title="Notifications"
        body="Where to deliver validation/window/guard/safe-mode events. The backend rate-limits per channel; leave blank to disable."
      >
        <Field label="Engineer (Slack)">
          <TextInput
            value={draft.notifications?.engineer_slack ?? ""}
            onChange={(v) =>
              update("notifications", {
                ...(draft.notifications ?? { channels: [] }),
                engineer_slack: v,
              })
            }
            placeholder="#sentinel-mitigations"
          />
        </Field>
        <Field label="Engineer (email)">
          <TextInput
            value={draft.notifications?.engineer_email ?? ""}
            onChange={(v) =>
              update("notifications", {
                ...(draft.notifications ?? { channels: [] }),
                engineer_email: v,
              })
            }
            placeholder="oncall@example.com"
          />
        </Field>
        <Field label="Lead (Slack)">
          <TextInput
            value={draft.notifications?.lead_slack ?? ""}
            onChange={(v) =>
              update("notifications", {
                ...(draft.notifications ?? { channels: [] }),
                lead_slack: v,
              })
            }
            placeholder="#sre-leads"
          />
        </Field>
      </SettingsGroup>

      {save.isError && (
        <div
          role="alert"
          className="card border-danger/40 bg-danger/10 p-3 text-xs text-danger"
        >
          Could not save changes: {String((save.error as Error).message)}
        </div>
      )}
    </div>
  );
}

function SettingsGroup({
  title,
  body,
  children,
}: {
  title: string;
  body: string;
  children: React.ReactNode;
}) {
  return (
    <section className="grid grid-cols-1 md:grid-cols-[18rem_1fr] gap-6 border-t border-border pt-6">
      <div>
        <h2 className="text-sm font-medium text-fg">{title}</h2>
        <p className="text-xs text-fg-muted mt-1">{body}</p>
      </div>
      <div className="card p-4 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
        {children}
      </div>
    </section>
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
    <label className="flex flex-col gap-1.5">
      <span className="text-xs text-fg-muted">{label}</span>
      {children}
    </label>
  );
}

function DurationInput({
  seconds,
  onChange,
}: {
  seconds: number;
  onChange: (s: number) => void;
}) {
  const [unit, setUnit] = useState<"s" | "m" | "h">("h");
  const value =
    unit === "h" ? seconds / 3600 : unit === "m" ? seconds / 60 : seconds;
  return (
    <div className="inline-flex gap-2">
      <input
        type="number"
        value={value}
        min={0}
        step={unit === "h" ? 1 : unit === "m" ? 5 : 60}
        onChange={(e) => {
          const next = parseFloat(e.target.value || "0");
          onChange(
            Math.round(
              unit === "h" ? next * 3600 : unit === "m" ? next * 60 : next
            )
          );
        }}
        className="rounded-md border border-border bg-surface px-2 py-1 font-data text-sm w-24 focus:outline-none focus:ring-2 focus:ring-accent/40"
      />
      <select
        value={unit}
        onChange={(e) => setUnit(e.target.value as "s" | "m" | "h")}
        className="rounded-md border border-border bg-surface px-2 py-1 font-data text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
        aria-label="Time unit"
      >
        <option value="s">seconds</option>
        <option value="m">minutes</option>
        <option value="h">hours</option>
      </select>
    </div>
  );
}

function RateInput({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="inline-flex items-center gap-2">
      <input
        type="number"
        value={(value * 100).toFixed(1)}
        min={0}
        max={100}
        step={0.5}
        onChange={(e) =>
          onChange(
            Math.max(0, Math.min(1, parseFloat(e.target.value || "0") / 100))
          )
        }
        className="rounded-md border border-border bg-surface px-2 py-1 font-data text-sm w-20 focus:outline-none focus:ring-2 focus:ring-accent/40"
      />
      <span className="font-data text-xs text-fg-muted">%</span>
    </div>
  );
}

function TextInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="rounded-md border border-border bg-surface px-2 py-1 font-data text-sm w-full focus:outline-none focus:ring-2 focus:ring-accent/40"
    />
  );
}

function ConfirmRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label
      className={cn(
        "flex items-center justify-between gap-3 rounded border border-border px-3 py-2 cursor-pointer hover:bg-surface-2 transition-colors",
        checked && "border-accent/40"
      )}
    >
      <div>
        <div className="text-sm font-medium text-fg">{label}</div>
        <div className="text-2xs text-fg-muted">
          {checked
            ? "Engineer must explicitly confirm to promote."
            : "Validation PASS auto-promotes."}
        </div>
      </div>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="size-4 accent-accent"
      />
    </label>
  );
}
