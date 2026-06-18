import "./globals.css";
import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Providers } from "@/components/Providers";
import { TopBar } from "@/components/TopBar";
import { Sidebar } from "@/components/Sidebar";
import { SafeModeBanner } from "@/components/SafeModeBanner";
import { CommandPalette } from "@/components/CommandPalette";
import { Toaster } from "@/components/ui/Toaster";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

const DEFAULT_THEME = (process.env.NEXT_PUBLIC_DEFAULT_THEME ?? "dark") as
  | "dark"
  | "light";
const BRAND = process.env.NEXT_PUBLIC_BRAND ?? "Sentinel";

export const metadata: Metadata = {
  title: `${BRAND} — Mitigation Safety`,
  description: "Operator console for the Sentinel Mitigation Safety module.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${mono.variable} ${DEFAULT_THEME}`}
      data-theme={DEFAULT_THEME}
      suppressHydrationWarning
    >
      <body className="min-h-dvh">
        <a className="skip-link" href="#main">
          Skip to main content
        </a>
        <Providers>
          <TopBar brand={BRAND} defaultTheme={DEFAULT_THEME} />
          <SafeModeBanner />
          <div className="flex">
            <Sidebar />
            <main
              id="main"
              tabIndex={-1}
              className="flex-1 min-w-0 focus:outline-none"
            >
              <div className="container py-section">{children}</div>
            </main>
          </div>
          <CommandPalette />
          <Toaster />
        </Providers>
      </body>
    </html>
  );
}
