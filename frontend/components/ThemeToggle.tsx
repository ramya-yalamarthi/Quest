"use client";

import { Sun, Moon } from "lucide-react";
import { useTheme } from "@/lib/hooks/useTheme";
import { Button } from "./ui/Button";

export function ThemeToggle({ defaultTheme }: { defaultTheme: "dark" | "light" }) {
  const { theme, toggle } = useTheme(defaultTheme);
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggle}
      aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
    >
      {theme === "dark" ? <Sun aria-hidden /> : <Moon aria-hidden />}
    </Button>
  );
}
