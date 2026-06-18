import type { Config } from "tailwindcss";

// All colors and rhythm come from CSS variables defined in lib/design/tokens.css
// so the theme can be switched at runtime via class="dark" without rebuilding
// Tailwind. Only the variable *names* live in this file.
const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    container: { center: true, padding: "1.5rem" },
    extend: {
      colors: {
        bg: "rgb(var(--bg) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        "surface-2": "rgb(var(--surface-2) / <alpha-value>)",
        border: "rgb(var(--border) / <alpha-value>)",
        "border-strong": "rgb(var(--border-strong) / <alpha-value>)",
        fg: "rgb(var(--fg) / <alpha-value>)",
        "fg-muted": "rgb(var(--fg-muted) / <alpha-value>)",
        "fg-subtle": "rgb(var(--fg-subtle) / <alpha-value>)",
        ok: "rgb(var(--ok) / <alpha-value>)",
        info: "rgb(var(--info) / <alpha-value>)",
        warn: "rgb(var(--warn) / <alpha-value>)",
        danger: "rgb(var(--danger) / <alpha-value>)",
        halt: "rgb(var(--halt) / <alpha-value>)",
        neutral: "rgb(var(--neutral) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
      },
      fontFamily: {
        sans: [
          "var(--font-sans)",
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "sans-serif",
        ],
        mono: [
          "var(--font-mono)",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "monospace",
        ],
      },
      fontSize: {
        // 12 / 13 / 14 / 16 / 20 / 24 / 30
        "2xs": ["0.75rem", { lineHeight: "1rem" }],
        xs: ["0.8125rem", { lineHeight: "1.125rem" }],
        sm: ["0.875rem", { lineHeight: "1.25rem" }],
        base: ["1rem", { lineHeight: "1.5rem" }],
        lg: ["1.25rem", { lineHeight: "1.75rem" }],
        xl: ["1.5rem", { lineHeight: "2rem" }],
        "2xl": ["1.875rem", { lineHeight: "2.25rem" }],
      },
      spacing: {
        // 4/8 rhythm; section tiers 16 / 24 / 32 / 48
        section: "2rem",
        gutter: "1.5rem",
      },
      borderRadius: {
        none: "0",
        sm: "0.25rem",
        DEFAULT: "0.375rem",
        md: "0.5rem",
        lg: "0.625rem",
      },
      // Status pattern utilities (color isn't the only signal — see StateBadge)
      ringWidth: { DEFAULT: "2px" },
      transitionDuration: {
        fast: "150ms",
        DEFAULT: "200ms",
        slow: "300ms",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.16, 1, 0.3, 1)",
        in: "cubic-bezier(0.4, 0, 1, 1)",
      },
      boxShadow: {
        // One consistent elevation scale — subtle, prefers borders.
        e1: "0 1px 0 0 rgb(var(--border) / 0.6)",
        e2:
          "0 1px 0 0 rgb(var(--border) / 0.6), 0 4px 12px -4px rgb(0 0 0 / 0.4)",
        e3:
          "0 1px 0 0 rgb(var(--border) / 0.8), 0 12px 32px -8px rgb(0 0 0 / 0.55)",
      },
    },
  },
  plugins: [],
};

export default config;
