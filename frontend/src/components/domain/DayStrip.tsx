import type { DayCell } from "@/api/types";
import { DAY, type Axis } from "@/lib/axis";
import { cn } from "@/lib/cn";

import { describeCell } from "./states";

export type { Axis };

function segments(intervals: [number, number][]): [number, number][] {
  return intervals.map(([a, b]) => [a, b < a ? DAY + b : b]);
}

/**
 * Полоса дня — фирменный элемент xTime (docs/design.md).
 * План — контур, факт — заливка. Опоздание — красная метка от планового начала до фактического,
 * ранний уход — янтарная метка в конце. «Нет дейлика» — пунктирный контур, отсутствие — штриховка.
 */
export function DayStrip({
  cell,
  axis,
  now,
  height = 14,
  className,
  label,
}: {
  cell: DayCell;
  axis: Axis;
  /** Секунды от полуночи для маркера «сейчас» (только для сегодняшнего дня). */
  now?: number | null;
  height?: number;
  className?: string;
  label?: string;
}) {
  const span = axis.end - axis.start;
  const x = (s: number) => `${Math.max(0, Math.min(100, ((s - axis.start) / span) * 100))}%`;
  const w = (a: number, b: number) =>
    `${Math.max(0, ((Math.min(b, axis.end) - Math.max(a, axis.start)) / span) * 100)}%`;

  const plan = cell.plan?.kind === "work" ? segments(cell.plan.intervals as [number, number][]) : [];
  const fact = cell.fact ? segments(cell.fact.intervals as [number, number][]) : [];
  const absence = cell.status && cell.status !== "remote" && !cell.fact;
  const missing = cell.state === "missing";
  const off = !cell.fact && !plan.length && (cell.state === "off" || cell.plan?.kind === "off");
  const lateFrom = plan[0]?.[0];
  const lateTo = fact[0]?.[0];
  const earlyFrom = fact.at(-1)?.[1];
  const earlyTo = plan.at(-1)?.[1];

  return (
    <div
      role="img"
      aria-label={label ?? (describeCell(cell) || "нет данных")}
      className={cn("relative w-full overflow-hidden rounded-[3px] bg-surface-2", className)}
      style={{ height }}
    >
      {absence ? <div className="hatch-absence absolute inset-0" /> : null}
      {off ? <div className="hatch absolute inset-0 opacity-70" /> : null}
      {plan.map(([a, b], i) => (
        <div
          key={`p${i}`}
          className={cn(
            "absolute inset-y-0 rounded-[3px] border",
            missing ? "border-dashed border-ink-3" : "border-ink-3/70",
          )}
          style={{ left: x(a), width: w(a, b) }}
        />
      ))}
      {fact.map(([a, b], i) => (
        <div
          key={`f${i}`}
          className="absolute inset-y-[3px] rounded-[2px] bg-accent"
          style={{ left: x(a), width: w(a, b), marginLeft: i > 0 ? 1 : 0 }}
        />
      ))}
      {cell.late_sec && lateFrom !== undefined && lateTo !== undefined ? (
        <div className="absolute inset-y-0 rounded-l-[3px] bg-late" style={{ left: x(lateFrom), width: w(lateFrom, lateTo) }} />
      ) : null}
      {cell.early_leave_sec && earlyFrom !== undefined && earlyTo !== undefined ? (
        <div className="absolute bottom-0 h-[4px] rounded-r-[3px] bg-deviation" style={{ left: x(earlyFrom), width: w(earlyFrom, earlyTo) }} />
      ) : null}
      {now !== null && now !== undefined && now > axis.start && now < axis.end ? (
        <div className="absolute inset-y-[-2px] w-px bg-ink" style={{ left: x(now) }} aria-hidden />
      ) : null}
    </div>
  );
}

/** Подписи часов над колонкой полос. */
export function AxisTicks({ axis, className }: { axis: Axis; className?: string }) {
  const hours = (axis.end - axis.start) / 3600;
  const step = hours > 12 ? 4 : hours > 6 ? 2 : 1;
  const ticks: number[] = [];
  for (let h = Math.ceil(axis.start / 3600); h * 3600 <= axis.end; h += step) ticks.push(h);
  return (
    <div className={cn("relative h-3 text-[10px] leading-3 text-ink-3 tnum", className)} aria-hidden>
      {ticks.map((h) => (
        <span
          key={h}
          className="absolute -translate-x-1/2"
          style={{ left: `${((h * 3600 - axis.start) / (axis.end - axis.start)) * 100}%` }}
        >
          {h % 24}
        </span>
      ))}
    </div>
  );
}
