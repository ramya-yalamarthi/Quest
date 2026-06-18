"use client";

/**
 * TelemetryChart — a line chart of one component/metric pair with optional
 * upper/lower bounds drawn as reference lines and a markers strip for
 * deploy/promote/revert events.
 *
 * Color is not the only signal: a small table alternative lists the latest
 * point, the min/max in window, and the threshold breach count for screen
 * readers and grayscale prints.
 */

import { useQuery } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  CartesianGrid,
  ReferenceDot,
} from "recharts";
import { useMemo } from "react";
import { getApi } from "@/lib/api";
import { usePrefersReducedMotion } from "@/lib/hooks/usePrefersReducedMotion";
import { fmtPct } from "@/lib/util/format";

export function TelemetryChart({
  component,
  bounds,
}: {
  component: string;
  bounds?: { min?: number; max?: number };
}) {
  const api = getApi();
  const { data } = useQuery({
    queryKey: ["telemetry", component, 3600],
    queryFn: () => api.getTelemetry(component, 3600),
    refetchInterval: 5_000,
  });
  const reduced = usePrefersReducedMotion();

  const series = useMemo(() => {
    if (!data) return [] as { ts: string; value: number; label: string }[];
    return data.points.map((p) => ({
      ts: p.ts,
      value: p.value,
      label: new Date(p.ts).toLocaleTimeString(undefined, {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
      }),
    }));
  }, [data]);

  const breaches = useMemo(() => {
    if (!data || !bounds) return 0;
    return data.points.reduce((n, p) => {
      if (bounds.max !== undefined && p.value > bounds.max) return n + 1;
      if (bounds.min !== undefined && p.value < bounds.min) return n + 1;
      return n;
    }, 0);
  }, [data, bounds]);

  const latest = series[series.length - 1];

  return (
    <figure className="card p-4 flex flex-col gap-3">
      <div className="flex items-baseline justify-between gap-2">
        <figcaption>
          <div className="text-sm font-medium text-fg">{component}</div>
          <div className="text-2xs uppercase tracking-wider text-fg-muted">
            {data?.metric ?? "—"} · rolling 60m
          </div>
        </figcaption>
        <div className="text-right text-2xs text-fg-muted">
          <div className="font-data text-base text-fg">
            {latest ? fmtPct(latest.value, 2) : "—"}
          </div>
          {bounds?.max !== undefined && (
            <div>
              max bound{" "}
              <span className="font-data text-fg">{fmtPct(bounds.max, 1)}</span>
            </div>
          )}
          {breaches > 0 && (
            <div className="font-data text-danger">
              {breaches} breach{breaches === 1 ? "" : "es"}
            </div>
          )}
        </div>
      </div>

      <div
        className="h-44"
        role="img"
        aria-label={`${component} ${data?.metric ?? "telemetry"} chart over the last hour`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={series}
            margin={{ top: 8, right: 6, bottom: 0, left: 0 }}
          >
            <CartesianGrid stroke="rgb(var(--border))" strokeDasharray="3 3" />
            <XAxis
              dataKey="label"
              stroke="rgb(var(--fg-muted))"
              tick={{ fontSize: 10 }}
              interval="preserveStartEnd"
              minTickGap={32}
            />
            <YAxis
              stroke="rgb(var(--fg-muted))"
              tick={{ fontSize: 10 }}
              tickFormatter={(v) => `${(v * 100).toFixed(1)}%`}
              width={48}
            />
            <Tooltip
              contentStyle={{
                background: "rgb(var(--surface))",
                border: "1px solid rgb(var(--border))",
                borderRadius: 8,
                fontSize: 12,
              }}
              labelStyle={{ color: "rgb(var(--fg-muted))" }}
              formatter={(value: number) => fmtPct(value, 2)}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="rgb(var(--accent))"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={!reduced}
            />
            {bounds?.max !== undefined && (
              <ReferenceLine
                y={bounds.max}
                stroke="rgb(var(--danger))"
                strokeDasharray="4 4"
                label={{
                  value: `max ${fmtPct(bounds.max, 1)}`,
                  position: "insideTopRight",
                  fontSize: 10,
                  fill: "rgb(var(--danger))",
                }}
              />
            )}
            {bounds?.min !== undefined && bounds.min > 0 && (
              <ReferenceLine
                y={bounds.min}
                stroke="rgb(var(--warn))"
                strokeDasharray="4 4"
              />
            )}
            {data?.markers?.map((m, i) => {
              const matched = series.findIndex(
                (s) => Math.abs(Date.parse(s.ts) - Date.parse(m.ts)) < 60_000
              );
              if (matched < 0) return null;
              return (
                <ReferenceDot
                  key={i}
                  x={series[matched].label}
                  y={series[matched].value}
                  r={5}
                  fill="rgb(var(--ok))"
                  stroke="rgb(var(--bg))"
                  strokeWidth={2}
                />
              );
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Text alternative for screen readers / grayscale prints */}
      <table className="sr-only" aria-label={`${component} telemetry summary`}>
        <thead>
          <tr>
            <th>Now</th>
            <th>Min</th>
            <th>Max</th>
            <th>Breaches</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>{latest ? fmtPct(latest.value, 2) : "—"}</td>
            <td>
              {series.length
                ? fmtPct(Math.min(...series.map((s) => s.value)), 2)
                : "—"}
            </td>
            <td>
              {series.length
                ? fmtPct(Math.max(...series.map((s) => s.value)), 2)
                : "—"}
            </td>
            <td>{breaches}</td>
          </tr>
        </tbody>
      </table>
    </figure>
  );
}
