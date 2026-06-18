import { useEffect, useState } from "react";
import { fetchValidation, ValidationOut } from "../api/mitigation";

export function useValidation(ticketId: string | null, pollMs = 5000) {
  const [data, setData] = useState<ValidationOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticketId) return;
    let alive = true;
    const tick = async () => {
      try {
        const next = await fetchValidation(ticketId);
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
  }, [ticketId, pollMs]);

  return { data, error };
}
