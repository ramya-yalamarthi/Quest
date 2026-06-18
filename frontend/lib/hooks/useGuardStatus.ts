"use client";

import { useQuery } from "@tanstack/react-query";
import { getApi } from "@/lib/api";
import type { GuardStatus } from "@/lib/api/types";

export function useGuardStatus() {
  return useQuery<GuardStatus[]>({
    queryKey: ["guards"],
    queryFn: () => getApi().getGuards(),
    refetchInterval: 30_000,
    staleTime: 10_000,
  });
}
