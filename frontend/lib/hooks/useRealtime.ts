"use client";

import { useEffect, useRef, useState } from "react";
import { getApi } from "@/lib/api";
import type { RTEvent } from "@/lib/api/types";
import { useQueryClient } from "@tanstack/react-query";

export interface RealtimeStatus {
  connected: boolean;
  paused: boolean;
  lastEventAt: number | null; // ms epoch
}

/**
 * Subscribe to backend realtime events.
 *
 * - keeps a `lastEventAt` heartbeat so the UI can show a "stale" indicator
 *   if events stop flowing during an incident
 * - exposes `pause`/`resume` for the activity feed (the brief requires a
 *   pause control on every live surface)
 * - reconciles relevant React Query caches on every event
 */
export function useRealtime(onEvent?: (e: RTEvent) => void): {
  status: RealtimeStatus;
  pause: () => void;
  resume: () => void;
  events: RTEvent[];
} {
  const [status, setStatus] = useState<RealtimeStatus>({
    connected: false,
    paused: false,
    lastEventAt: null,
  });
  const [events, setEvents] = useState<RTEvent[]>([]);
  const handlerRef = useRef(onEvent);
  const pausedRef = useRef(false);
  const qc = useQueryClient();

  useEffect(() => {
    handlerRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    const api = getApi();
    setStatus((s) => ({ ...s, connected: true }));
    const off = api.subscribe((e) => {
      setStatus((s) => ({ ...s, lastEventAt: Date.now(), connected: true }));
      if (pausedRef.current) return;
      handlerRef.current?.(e);
      setEvents((prev) => [e, ...prev].slice(0, 200));
      // Cache reconciliation by event kind.
      switch (e.type) {
        case "state_transition":
          qc.invalidateQueries({ queryKey: ["actions"] });
          qc.invalidateQueries({ queryKey: ["action", e.action_id] });
          qc.invalidateQueries({ queryKey: ["kpis"] });
          break;
        case "validation_update":
          qc.invalidateQueries({ queryKey: ["validation", e.action_id] });
          break;
        case "safe_mode_change":
          qc.invalidateQueries({ queryKey: ["safe-mode"] });
          qc.invalidateQueries({ queryKey: ["guards"] });
          break;
        case "guard_trip":
          qc.invalidateQueries({ queryKey: ["guards"] });
          qc.invalidateQueries({ queryKey: ["safe-mode"] });
          qc.invalidateQueries({ queryKey: ["actions"] });
          break;
        case "notification":
          // Toasts handle this elsewhere; we just keep the feed up to date.
          break;
      }
    });
    return () => {
      off();
      setStatus((s) => ({ ...s, connected: false }));
    };
  }, [qc]);

  // Stale-stream watchdog — if we haven't received an event in 30s, flag.
  useEffect(() => {
    const id = setInterval(() => {
      setStatus((s) => {
        if (s.paused || !s.lastEventAt) return s;
        const stale = Date.now() - s.lastEventAt > 30_000;
        if (s.connected === !stale) return s;
        return { ...s, connected: !stale };
      });
    }, 5_000);
    return () => clearInterval(id);
  }, []);

  return {
    status,
    pause: () => {
      pausedRef.current = true;
      setStatus((s) => ({ ...s, paused: true }));
    },
    resume: () => {
      pausedRef.current = false;
      setStatus((s) => ({ ...s, paused: false }));
    },
    events,
  };
}
