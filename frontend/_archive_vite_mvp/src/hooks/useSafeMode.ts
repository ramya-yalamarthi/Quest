import { useEffect, useState } from "react";
import { fetchSafeMode, SafeModeView } from "../api/mitigation";

export function useSafeMode(pollMs = 10_000) {
  const [data, setData] = useState<SafeModeView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const next = await fetchSafeMode();
        if (alive) {
          setData(next);
          setError(null);
        }
      } catch (e: any) {
        if (alive) setError(e.message);
      }
    };
    tick();
    const handle = setInterval(tick, pollMs);
    return () => {
      alive = false;
      clearInterval(handle);
    };
  }, [pollMs]);

  return { data, error, refresh: async () => setData(await fetchSafeMode()) };
}
