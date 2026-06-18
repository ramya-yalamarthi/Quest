"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { cn } from "@/lib/util/cn";
import {
  ChevronsLeft,
  ChevronsRight,
  LayoutDashboard,
  GitBranch,
  Activity,
  ShieldCheck,
  ScrollText,
  Settings as SettingsIcon,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

const NAV: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/actions", label: "Actions", icon: GitBranch },
  { href: "/validation", label: "Validation & Telemetry", icon: Activity },
  { href: "/safe-mode", label: "Safe Mode & Guards", icon: ShieldCheck },
  { href: "/audit", label: "Audit", icon: ScrollText },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  const width = collapsed
    ? "var(--sidebar-w-collapsed)"
    : "var(--sidebar-w)";

  return (
    <aside
      aria-label="Primary"
      className={cn(
        "hidden md:flex flex-col border-r border-border bg-surface shrink-0",
        "transition-[width] duration-default ease-out sticky top-[var(--topbar-h)] h-[calc(100dvh-var(--topbar-h))]"
      )}
      style={{ width }}
    >
      <nav className="flex-1 py-3">
        <ul className="flex flex-col gap-0.5">
          {NAV.map((item) => {
            const active =
              pathname === item.href ||
              (item.href !== "/" && pathname.startsWith(item.href));
            const Icon = item.icon;
            return (
              <li key={item.href} className="px-2">
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "group flex items-center gap-3 rounded-md px-2.5 py-2 text-sm font-medium",
                    "border-l-2",
                    active
                      ? "border-l-accent bg-surface-2 text-fg"
                      : "border-l-transparent text-fg-muted hover:bg-surface-2 hover:text-fg"
                  )}
                  title={collapsed ? item.label : undefined}
                >
                  <Icon className="size-4 shrink-0" aria-hidden />
                  {!collapsed && <span>{item.label}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="border-t border-border p-2">
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className="w-full inline-flex items-center justify-center gap-2 rounded-md px-2.5 py-2 text-xs text-fg-muted hover:bg-surface-2 hover:text-fg transition-colors"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronsRight className="size-4" /> : <ChevronsLeft className="size-4" />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
