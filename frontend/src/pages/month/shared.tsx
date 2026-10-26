import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { Link } from "react-router";

import type { EmployeeBrief } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { cn } from "@/lib/cn";

import type { SortState } from "./sorting";

export function PersonCell({ employee, position }: { employee: EmployeeBrief; position?: string }) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      <Avatar employee={employee} size={24} />
      <span className="min-w-0">
        <Link to={`/people/${employee.id}`} className="block truncate text-[13px] font-medium hover:underline">
          {employee.short_name}
        </Link>
        {position ? <span className="block truncate text-[12px] text-ink-3">{position}</span> : null}
      </span>
    </span>
  );
}

export const th = "px-3 py-2 text-[12px] font-medium text-ink-3 whitespace-nowrap";
export const td = "px-3 py-2.5 text-[13px] tnum whitespace-nowrap";

export function NumTh({ children, className, title }: { children: React.ReactNode; className?: string; title?: string }) {
  return (
    <th scope="col" title={title} className={cn(th, "text-right", className)}>
      {children}
    </th>
  );
}

/**
 * Полоса выполнения нормы: заливка — Итого, риска — норма. Шкала общая для всех строк.
 * Сверх нормы — тот же цвет светлее, отделённый от нормы зазором, чтобы переработка читалась отдельно.
 */
export function NormBar({ total, norm, max }: { total: number; norm: number; max: number }) {
  const pct = (v: number) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`;
  const over = total > norm;
  return (
    <div className="relative h-2 w-full min-w-24" aria-hidden>
      <div className="absolute inset-0 rounded-full bg-surface-2" />
      <div
        className={cn("absolute inset-y-0 left-0 bg-accent", over ? "rounded-l-full" : "rounded-full")}
        style={{ width: pct(Math.min(total, norm)) }}
      />
      {over ? (
        <div
          className="absolute inset-y-0 rounded-r-full bg-accent/45"
          style={{ left: `calc(${pct(norm)} + 3px)`, width: `max(0px, calc(${pct(total)} - ${pct(norm)} - 3px))` }}
        />
      ) : null}
      <div className="absolute -inset-y-[3px] w-px -translate-x-1/2 bg-ink-2" style={{ left: pct(norm) }} />
    </div>
  );
}

// --- сортировка таблиц месяца ----------------------------------------------------------------

export function SortTh<K extends string>({
  label,
  sortKey,
  sort,
  onSort,
  title,
  align = "right",
  className,
}: {
  label: React.ReactNode;
  sortKey: K;
  sort: SortState<K> | null;
  onSort: (key: K) => void;
  title?: string;
  align?: "left" | "right";
  className?: string;
}) {
  const dir = sort?.key === sortKey ? sort.dir : null;
  const Icon = dir === "desc" ? ArrowDown : dir === "asc" ? ArrowUp : ArrowUpDown;
  return (
    <th
      scope="col"
      title={title}
      aria-sort={dir === "desc" ? "descending" : dir === "asc" ? "ascending" : "none"}
      className={cn(th, align === "right" && "text-right", className)}
    >
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={cn(
          "group inline-flex items-center gap-1 rounded-sm hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40",
          align === "right" && "flex-row-reverse",
          dir && "text-ink",
        )}
      >
        {label}
        <Icon
          aria-hidden
          className={cn("size-3.5 shrink-0", !dir && "opacity-0 group-hover:opacity-60 group-focus-visible:opacity-60")}
        />
      </button>
    </th>
  );
}

export function EmptyRows({ colSpan }: { colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-3 py-6 text-center text-[13px] text-ink-2">
        Под фильтр никто не подходит.
      </td>
    </tr>
  );
}
