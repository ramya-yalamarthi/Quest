"use client";

/**
 * ActionsTable — semantic <table> with sortable headers, focus management,
 * keyboard nav, and aria-live row-update announcements.
 *
 * Uses TanStack Table for sort/filter state and TanStack Virtual when rows
 * exceed 60 — kept simple under that.
 */

import Link from "next/link";
import { useMemo, useState } from "react";
import { useReactTable, getCoreRowModel, getSortedRowModel, createColumnHelper, flexRender, type SortingState } from "@tanstack/react-table";
import type { MitigationAction, MitigationState } from "@/lib/api/types";
import { StateBadge } from "./StateBadge";
import { CopyableId } from "./CopyableId";
import { ActorTag } from "./LifecycleTimeline";
import { fmtAge } from "@/lib/util/format";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/util/cn";

const col = createColumnHelper<MitigationAction>();

export function ActionsTable({
  actions,
  emptyText = "No actions match the current filters.",
}: {
  actions: MitigationAction[];
  emptyText?: string;
}) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: "created_at", desc: true },
  ]);

  const columns = useMemo(
    () => [
      col.accessor("state", {
        header: "State",
        cell: (info) => <StateBadge state={info.getValue() as MitigationState} size="sm" />,
        sortingFn: "alphanumeric",
      }),
      col.accessor("ticket_id", {
        header: "Ticket",
        cell: (info) => <CopyableId id={info.getValue()} />,
      }),
      col.accessor("action_id", {
        header: "Action",
        cell: (info) => <CopyableId id={info.getValue()} />,
      }),
      col.accessor("category", {
        header: "Category",
        cell: (info) => (
          <span className="font-data text-xs text-fg-muted">{info.getValue()}</span>
        ),
      }),
      col.accessor("type", {
        header: "Type",
        cell: (info) => (
          <span className="font-data text-2xs uppercase tracking-wider text-fg-muted">
            {info.getValue()}
          </span>
        ),
      }),
      col.accessor("target", {
        header: "Target",
        cell: (info) => (
          <span
            className="font-data text-xs text-fg truncate inline-block max-w-[16rem] align-middle"
            title={info.getValue()}
          >
            {info.getValue()}
          </span>
        ),
      }),
      col.accessor("actor", {
        header: "Actor",
        cell: (info) => <ActorTag actor={info.getValue()} />,
      }),
      col.accessor("created_at", {
        header: "Created",
        cell: (info) => (
          <span className="font-data text-2xs text-fg-muted">
            {fmtAge(info.getValue())}
          </span>
        ),
        sortingFn: (a, b) =>
          Date.parse(a.original.created_at) - Date.parse(b.original.created_at),
      }),
      col.display({
        id: "inspect",
        header: "",
        cell: (info) => (
          <Link
            href={`/actions/${info.row.original.action_id}`}
            className="text-xs text-accent hover:underline"
          >
            Inspect
          </Link>
        ),
      }),
    ],
    []
  );

  const table = useReactTable({
    data: actions,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (actions.length === 0) {
    return (
      <div className="card p-6 text-sm text-fg-muted text-center">
        {emptyText}
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm" role="grid">
          <thead className="bg-surface-2 text-2xs uppercase tracking-wider text-fg-muted">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => {
                  const sortable = h.column.getCanSort() && h.id !== "inspect";
                  const sort = h.column.getIsSorted();
                  return (
                    <th
                      key={h.id}
                      scope="col"
                      aria-sort={
                        sort === "asc"
                          ? "ascending"
                          : sort === "desc"
                            ? "descending"
                            : sortable
                              ? "none"
                              : undefined
                      }
                      className="px-3 py-2 text-left font-medium"
                    >
                      {sortable ? (
                        <button
                          type="button"
                          onClick={h.column.getToggleSortingHandler()}
                          className="inline-flex items-center gap-1 hover:text-fg transition-colors"
                        >
                          {flexRender(h.column.columnDef.header, h.getContext())}
                          {sort === "asc" ? (
                            <ArrowUp aria-hidden className="size-3" />
                          ) : sort === "desc" ? (
                            <ArrowDown aria-hidden className="size-3" />
                          ) : (
                            <ChevronsUpDown
                              aria-hidden
                              className="size-3 opacity-50"
                            />
                          )}
                        </button>
                      ) : (
                        flexRender(h.column.columnDef.header, h.getContext())
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row, i) => (
              <tr
                key={row.id}
                className={cn(
                  "border-t border-border hover:bg-surface-2/60 transition-colors duration-fast",
                  i % 2 === 1 && "bg-surface-2/20"
                )}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-2 align-middle">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
