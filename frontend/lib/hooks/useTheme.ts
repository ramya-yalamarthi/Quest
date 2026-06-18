"use client";

import { useEffect, useState } from "react";

/**
 * Theme controller — no localStorage (per the brief). The default theme is
 * applied to <html> in the layout server component; this hook only handles
 * runtime toggle for the current tab.
 */
export type Theme = "dark" | "light";

export function useTheme(defaultTheme: Theme = "dark") {
  const [theme, setTheme] = useState<Theme>(defaultTheme);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "light") {
      root.classList.add("light");
      root.classList.remove("dark");
      root.setAttribute("data-theme", "light");
    } else {
      root.classList.add("dark");
      root.classList.remove("light");
      root.setAttribute("data-theme", "dark");
    }
  }, [theme]);

  return { theme, setTheme, toggle: () => setTheme((t) => (t === "dark" ? "light" : "dark")) };
}
