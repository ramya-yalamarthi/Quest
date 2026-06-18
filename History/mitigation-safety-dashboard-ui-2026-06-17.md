# Sentinel Mitigation Safety Dashboard — UI/UX Build

**Created:** 2026-06-17
**Workflow ID:** ms-dashboard-ui-2026-06-17
**Status:** In Progress
**Brief:** Full operator console for the Sentinel Mitigation Safety module (the 6 `/mitigate/*` + `/mitigation/*` backend routes already shipped).
**Stack:** Next.js (App Router) + React + TypeScript + Tailwind + shadcn/ui + TanStack Query/Table + Recharts + lucide-react.
**Default theme:** dark; light fully supported.

## Phases

### G1: Foundation — design tokens + Tailwind config + theme + reduced-motion
- Status: In Progress
- Deliverables: `lib/design/tokens.css` (dark + light, semantic, status uses color+icon+label+shape), Tailwind config wiring CSS vars, `class="dark"` strategy, prefers-reduced-motion vars, tabular-nums everywhere.

### G2: API + realtime + mock adapter (single retarget point)
- Status: Not Started
- Deliverables: `lib/api/types.ts`, `lib/api/client.ts`, `lib/api/mock.ts` (in-memory with simulated event emitter — Approved→Staged→Validating tick, fail→auto-revert, expiry, guard-trip→Safe Mode), `lib/hooks/useRealtime.ts`, `useCountdown.ts`, `useSafeMode.ts`, `useGuardStatus.ts`. SSE-default, stale-stream detection.

### G3: Signature primitives — LoopRing, StateBadge, LifecycleTimeline, KpiBullet, GuardProximityBar
- Status: Not Started
- Deliverables: the bold custom SVG components that carry the identity. LoopRing closes only at Promote; breaks on Fail/Expire. StateBadge uses color+icon+text+shape for all 11 states. Promotion-decision panel.

### G4: Global frame — Sidebar, TopBar, SafeModeBanner, SafeModePill, CommandPalette (⌘K), ThemeToggle, Toaster
- Status: Not Started
- Deliverables: layout, focus-not-obscured handling for sticky banner (WCAG 2.2 §2.4.11), skip-link, deep-link URL filter system.

### G5: Routes
- Status: Not Started
- 5a. `/` Overview (posture strip, lifecycle pipeline, KPI row, needs-attention, live feed)
- 5b. `/actions` + `/actions/[id]` (table + board, action card, action detail drawer/page, promote/revert flows)
- 5c. `/validation` (in-flight windows + telemetry)
- 5d. `/safe-mode` (posture control + guard config + history)
- 5e. `/audit` (immutable trail + CSV export + reconstruct-by-action)
- 5f. `/settings` (windows, confirm-to-promote, notifications)

### G6: Tables — ActionsTable + AuditTable
- Status: Not Started
- Deliverables: semantic `<table>` with `<th scope>`, `aria-sort`, sort-change `aria-live` announcement, focus-on-paginate, virtualization via TanStack.

### G7: Confirm dialogs — Promote consequence-stating, Revert with required reason, Safe Mode entry/exit
- Status: Not Started
- Deliverables: shadcn/Radix Dialog with focus trap, Escape, restored focus, scrim ≥40% black.

### G8: Charts — StreamingChart (pause/reduced-motion), bullet KPI, line+highlights, funnel/stepper
- Status: Not Started
- Deliverables: Recharts wrappers + custom SVG; all charts have a text/table alternative and `aria-label`; deploy/promote/revert markers labeled.

### G9: README + run instructions + a11y notes + assumptions
- Status: Not Started

## Execution Log
| Date | Phase | Action | Status |
|------|-------|--------|--------|
| 2026-06-17 | G1 | started | pending |
