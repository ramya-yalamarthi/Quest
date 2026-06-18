"use client";

import { useQuery } from "@tanstack/react-query";
import { getApi } from "@/lib/api";
import type { SafeModeView } from "@/lib/api/types";

export function useSafeMode() {
  return useQuery<SafeModeView>({
    queryKey: ["safe-mode"],
    queryFn: () => getApi().getSafeMode(),
    refetchInterval: 30_000,
    staleTime: 10_000,
  });
}
