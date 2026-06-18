"use client";

import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { cn } from "@/lib/util/cn";
import { truncId } from "@/lib/util/format";

export function CopyableId({
  id,
  className,
  short = true,
}: {
  id: string;
  className?: string;
  short?: boolean;
}) {
  const [done, setDone] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(id);
      setDone(true);
      setTimeout(() => setDone(false), 1500);
    } catch {
      /* swallow — clipboard is best-effort */
    }
  }
  return (
    <span className={cn("inline-flex items-center gap-1", className)} title={id}>
      <span className="font-data text-fg">{short ? truncId(id) : id}</span>
      <button
        type="button"
        onClick={copy}
        className="rounded p-0.5 text-fg-muted hover:text-fg hover:bg-surface-2 transition-colors"
        aria-label={done ? "Copied" : `Copy ${id}`}
      >
        {done ? (
          <Check className="size-3" aria-hidden />
        ) : (
          <Copy className="size-3" aria-hidden />
        )}
      </button>
    </span>
  );
}
