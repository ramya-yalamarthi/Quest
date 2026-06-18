"use client";

import { useState } from "react";
import { ShieldCheck, Search, User2, ChevronDown } from "lucide-react";
import { Button } from "./ui/Button";
import { SafeModePill } from "./SafeModePill";
import { ThemeToggle } from "./ThemeToggle";
import { cn } from "@/lib/util/cn";

export function TopBar({ brand, defaultTheme }: { brand: string; defaultTheme: "dark" | "light" }) {
  const [env, setEnv] = useState<"production" | "staging">("production");
  return (
    <header
      className="sticky top-0 z-40 h-[var(--topbar-h)] border-b border-border bg-bg/95 backdrop-blur supports-[backdrop-filter]:bg-bg/80"
      role="banner"
    >
      <div className="container h-full flex items-center gap-3">
        {/* Brand */}
        <div className="flex items-center gap-2.5 mr-2">
          <ShieldCheck aria-hidden className="size-5 text-accent" />
          <span className="font-semibold tracking-tight text-fg">
            {brand}
          </span>
          <span
            className="font-data text-2xs uppercase tracking-wider text-fg-subtle border-l border-border pl-2.5 ml-1"
            aria-label="Module name"
          >
            Mitigation Safety
          </span>
        </div>

        {/* Environment selector */}
        <EnvSelect env={env} setEnv={setEnv} />

        {/* Safe Mode pill — the most prominent status indicator */}
        <SafeModePill />

        {/* Pushes the rest to the right */}
        <div className="flex-1" />

        {/* Command palette trigger */}
        <Button
          variant="secondary"
          size="sm"
          className="font-data"
          onClick={() => {
            // The palette listens for ⌘K; we synthesize one here.
            window.dispatchEvent(
              new KeyboardEvent("keydown", {
                key: "k",
                metaKey: true,
                ctrlKey: true,
              })
            );
          }}
          aria-label="Open command palette"
        >
          <Search className="size-3.5" aria-hidden />
          <span className="hidden sm:inline">Search</span>
          <kbd className="text-2xs border border-border-strong rounded px-1 ml-1">
            ⌘K
          </kbd>
        </Button>

        <ThemeToggle defaultTheme={defaultTheme} />

        <UserMenu />
      </div>
    </header>
  );
}

function EnvSelect({
  env,
  setEnv,
}: {
  env: "production" | "staging";
  setEnv: (e: "production" | "staging") => void;
}) {
  return (
    <label className="inline-flex items-center gap-1.5 text-xs">
      <span className="sr-only">Environment</span>
      <span
        className={cn(
          "inline-block size-2 rounded-full",
          env === "production" ? "bg-info" : "bg-warn"
        )}
        aria-hidden
      />
      <select
        className="bg-transparent text-fg-muted hover:text-fg focus:outline-none font-data text-xs cursor-pointer"
        value={env}
        onChange={(e) => setEnv(e.target.value as never)}
      >
        <option value="production">production</option>
        <option value="staging">staging</option>
      </select>
    </label>
  );
}

function UserMenu() {
  return (
    <button
      type="button"
      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface-2 px-2 py-1 text-xs text-fg-muted hover:text-fg hover:border-border-strong transition-colors"
      aria-label="User menu"
    >
      <User2 className="size-3.5" aria-hidden />
      <span className="font-data">operator</span>
      <ChevronDown className="size-3" aria-hidden />
    </button>
  );
}
