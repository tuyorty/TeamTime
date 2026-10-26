import type * as React from "react";

/** Общая подсказка графиков: текст всегда в токенах ink, цвет — только у маркера. */
export function TooltipBox({ title, rows }: { title: React.ReactNode; rows: { color?: string; label: string; value: React.ReactNode }[] }) {
  return (
    <div className="rounded-md border border-line bg-surface px-2.5 py-2 text-[12px] shadow-panel">
      <div className="mb-1 font-medium text-ink">{title}</div>
      <div className="grid gap-0.5">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center gap-2 text-ink-2">
            {r.color ? <span className="size-2 rounded-[2px]" style={{ background: r.color }} /> : null}
            <span>{r.label}</span>
            <span className="ml-auto pl-4 font-medium text-ink tnum">{r.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
