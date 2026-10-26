import { Link } from "react-router";

import type { EmployeeBrief } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { cn } from "@/lib/cn";

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

/** Полоса выполнения нормы: заливка — Итого, вертикальная риска — норма. Шкала общая для всех строк. */
export function NormBar({ total, norm, max }: { total: number; norm: number; max: number }) {
  const pct = (v: number) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`;
  const over = total > norm;
  return (
    <div className="relative h-2.5 w-full min-w-24 rounded-full bg-surface-2" aria-hidden>
      <div className="absolute inset-y-0 left-0 rounded-full bg-accent/80" style={{ width: pct(Math.min(total, norm)) }} />
      {over ? (
        <div className="absolute inset-y-0 rounded-r-full bg-accent" style={{ left: pct(norm), width: `calc(${pct(total)} - ${pct(norm)})` }} />
      ) : null}
      <div className="absolute -inset-y-1 w-0.5 rounded bg-ink" style={{ left: pct(norm) }} />
    </div>
  );
}
