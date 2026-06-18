"use client";

/**
 * CommandPalette — keyboard-first (⌘K / Ctrl-K), Radix Dialog so we get
 * focus trap, escape, focus restore, and proper modal semantics for free.
 *
 * The palette searches actions and audit rows, exposes quick commands
 * (Enter Safe Mode, jump to Validating, open ticket), and is fully
 * keyboard-driven (arrow keys to move, Enter to select, Escape to close).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { getApi } from "@/lib/api";
import type { MitigationAction } from "@/lib/api/types";
import { Search, ChevronRight, ShieldCheck, GitBranch, Activity, ScrollText } from "lucide-react";
import { cn } from "@/lib/util/cn";
import { truncId } from "@/lib/util/format";

interface Item {
  id: string;
  label: string;
  hint?: string;
  href: string;
  icon: React.ReactNode;
  kind: "action" | "command";
}

const QUICK: Item[] = [
  { id: "q-overview", label: "Go to overview", href: "/", icon: <Activity className="size-4" />, kind: "command" },
  { id: "q-actions-validating", label: "Show Validating actions", href: "/actions?state=VALIDATING", icon: <GitBranch className="size-4" />, kind: "command" },
  { id: "q-actions-needs-attention", label: "Show needs-attention queue", href: "/actions?state=VALIDATING&overall=PASS", icon: <GitBranch className="size-4" />, kind: "command" },
  { id: "q-safe-mode", label: "Open Safe Mode controls", href: "/safe-mode", icon: <ShieldCheck className="size-4" />, kind: "command" },
  { id: "q-audit", label: "Open audit trail", href: "/audit", icon: <ScrollText className="size-4" />, kind: "command" },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  const { data: actions } = useQuery<MitigationAction[]>({
    queryKey: ["actions", "palette"],
    queryFn: () => getApi().listActions({ limit: 50 }),
    staleTime: 30_000,
  });

  // Keyboard shortcut.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  const items = useMemo<Item[]>(() => {
    const q = query.toLowerCase();
    const matchedActions = (actions ?? [])
      .filter(
        (a) =>
          !q ||
          a.ticket_id.toLowerCase().includes(q) ||
          a.action_id.toLowerCase().includes(q) ||
          a.target.toLowerCase().includes(q) ||
          a.actor.toLowerCase().includes(q)
      )
      .slice(0, 8)
      .map<Item>((a) => ({
        id: a.action_id,
        label: `${a.category} · ${a.target}`,
        hint: `${a.state} · ticket ${truncId(a.ticket_id)} · action ${truncId(a.action_id)}`,
        href: `/actions/${a.action_id}`,
        icon: <GitBranch className="size-4" />,
        kind: "action",
      }));
    const matchedQuick = QUICK.filter(
      (it) => !q || it.label.toLowerCase().includes(q)
    );
    return [...matchedQuick, ...matchedActions];
  }, [actions, query]);

  const onSelect = useCallback(
    (item: Item) => {
      setOpen(false);
      router.push(item.href);
    },
    [router]
  );

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-[2px]" />
        <DialogPrimitive.Content
          className="fixed left-1/2 top-[18%] z-50 -translate-x-1/2 w-[640px] max-w-[92vw] rounded-xl border border-border bg-surface shadow-e3 overflow-hidden"
          aria-label="Command palette"
        >
          <DialogPrimitive.Title className="sr-only">Command palette</DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">
            Search actions, tickets, audit; pick a quick command. Use arrow keys to navigate, Enter to select, Escape to close.
          </DialogPrimitive.Description>
          <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
            <Search aria-hidden className="size-4 text-fg-muted" />
            <input
              ref={inputRef}
              type="text"
              role="combobox"
              aria-expanded
              aria-controls="command-listbox"
              aria-activedescendant={items[active] ? `cmd-${items[active].id}` : undefined}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setActive(0);
              }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setActive((a) => Math.min(items.length - 1, a + 1));
                } else if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setActive((a) => Math.max(0, a - 1));
                } else if (e.key === "Enter" && items[active]) {
                  e.preventDefault();
                  onSelect(items[active]);
                }
              }}
              placeholder="Search actions, tickets, or run a command…"
              className="flex-1 bg-transparent text-sm text-fg placeholder:text-fg-subtle focus:outline-none"
            />
            <kbd className="font-data text-2xs text-fg-muted border border-border rounded px-1.5 py-0.5">
              Esc
            </kbd>
          </div>
          <ul
            id="command-listbox"
            role="listbox"
            className="max-h-80 overflow-y-auto py-1"
          >
            {items.length === 0 ? (
              <li className="px-3 py-6 text-sm text-fg-muted text-center">
                No matches. Try a ticket id or "Validating".
              </li>
            ) : (
              items.map((item, i) => (
                <li
                  id={`cmd-${item.id}`}
                  key={item.id}
                  role="option"
                  aria-selected={i === active}
                  className={cn(
                    "px-3 py-2 cursor-pointer flex items-center gap-3 text-sm",
                    i === active ? "bg-surface-2" : "hover:bg-surface-2/60"
                  )}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => onSelect(item)}
                >
                  <span className="text-fg-muted">{item.icon}</span>
                  <span className="flex-1 min-w-0">
                    <span className="block text-fg truncate">{item.label}</span>
                    {item.hint && (
                      <span className="block text-2xs text-fg-muted truncate font-data">
                        {item.hint}
                      </span>
                    )}
                  </span>
                  <ChevronRight aria-hidden className="size-3.5 text-fg-subtle" />
                </li>
              ))
            )}
          </ul>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
