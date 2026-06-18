"use client";

/**
 * Toaster — listens to the realtime stream and surfaces the four critical
 * events as toasts with the right urgency mapping:
 *
 *   validation_failed | window_expired | guard_rollback | safe_mode_entered
 *
 * Critical events use role="alert" / aria-live="assertive" + aria-atomic;
 * routine ones default to polite. Toasts include action_id, ticket_id, the
 * triggering condition, the resulting state, and a deep link.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Toast,
  ToastClose,
  ToastDescription,
  ToastProvider,
  ToastTitle,
  ToastViewport,
} from "./Toast";
import { useRealtime } from "@/lib/hooks/useRealtime";
import type { RTEvent } from "@/lib/api/types";
import { truncId } from "@/lib/util/format";

interface Item {
  id: string;
  tone: "info" | "ok" | "warn" | "danger" | "default";
  title: string;
  body: string;
  href?: string;
  assertive: boolean;
  ts: number;
}

const KIND_MAP: Record<
  string,
  { tone: Item["tone"]; title: string; assertive: boolean }
> = {
  validation_failed: { tone: "danger", title: "Validation failed", assertive: true },
  window_expired: { tone: "warn", title: "Window expired — auto-reverted", assertive: true },
  guard_rollback: { tone: "danger", title: "Guard-triggered rollback", assertive: true },
  safe_mode_entered: { tone: "danger", title: "Safe Mode entered", assertive: true },
};

export function Toaster() {
  const [items, setItems] = useState<Item[]>([]);

  useRealtime((e) => {
    const item = toItem(e);
    if (!item) return;
    setItems((prev) => [item, ...prev].slice(0, 6));
  });

  return (
    <ToastProvider swipeDirection="right" duration={8000}>
      {items.map((it) => (
        <Toast
          key={it.id}
          tone={it.tone}
          role={it.assertive ? "alert" : undefined}
          aria-live={it.assertive ? "assertive" : "polite"}
          aria-atomic
        >
          <div className="min-w-0 flex-1">
            <ToastTitle>{it.title}</ToastTitle>
            <ToastDescription>{it.body}</ToastDescription>
            {it.href && (
              <Link
                href={it.href}
                className="mt-1 inline-block text-xs text-accent hover:underline"
              >
                Inspect →
              </Link>
            )}
          </div>
          <ToastClose />
        </Toast>
      ))}
      <ToastViewport />
    </ToastProvider>
  );
}

function toItem(e: RTEvent): Item | null {
  if (e.type === "notification") {
    const map = KIND_MAP[e.kind];
    if (!map) return null;
    return {
      id: `n-${e.ts}-${e.action_id ?? ""}`,
      tone: map.tone,
      title: map.title,
      body:
        e.action_id && e.ticket_id
          ? `${e.triggering} · action ${truncId(e.action_id)} · ticket ${truncId(e.ticket_id)}${e.resulting_state ? ` → ${e.resulting_state}` : ""}`
          : `${e.triggering}${e.resulting_state ? ` → ${e.resulting_state}` : ""}`,
      href: e.action_id ? `/actions/${e.action_id}` : undefined,
      assertive: map.assertive,
      ts: Date.now(),
    };
  }
  if (e.type === "safe_mode_change" && e.active) {
    return {
      id: `sm-${e.ts}-${e.scope}`,
      tone: "danger",
      title: "Safe Mode entered",
      body: `${e.scope} · by ${e.actor}${e.reason ? ` — ${e.reason}` : ""}`,
      href: "/safe-mode",
      assertive: true,
      ts: Date.now(),
    };
  }
  if (e.type === "guard_trip") {
    return {
      id: `g-${e.ts}-${e.category}`,
      tone: "danger",
      title: "Guard tripped",
      body: `${e.category} · ${e.signal} rate ${(e.value * 100).toFixed(0)}% over ${(e.threshold * 100).toFixed(0)}%`,
      href: "/safe-mode",
      assertive: true,
      ts: Date.now(),
    };
  }
  return null;
}
