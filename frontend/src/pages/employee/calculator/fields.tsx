import type { ReactNode } from "react";

import { Field, Input } from "@/components/ui/field";
import { cn } from "@/lib/cn";
import { readNumber } from "./input";

export function HoursField({ label, value, onChange, hint }: {
  label: string; value: string; onChange: (value: string) => void; hint?: string;
}) {
  return <Field label={label} hint={hint}>
    <Input value={value} onChange={(event) => onChange(event.target.value)} inputMode="decimal" placeholder="160:00" className="h-10" />
  </Field>;
}

export function EfficiencyField({ label, value, onChange }: {
  label: string; value: string; onChange: (value: string) => void;
}) {
  const number = readNumber(value);
  return <div className="grid gap-3">
    <Field label={label}>
      <Input type="number" min="0" max="100" step="0.1" value={value} onChange={(event) => onChange(event.target.value)} className="h-10" />
    </Field>
    <input type="range" min="0" max="100" step="1" value={Number.isFinite(number) ? Math.max(0, Math.min(100, number)) : 0}
      onChange={(event) => onChange(event.target.value)} aria-label={`${label} — ползунок`} className="h-3 w-full cursor-pointer accent-[var(--accent)]" />
    <div className="flex justify-between text-[11px] text-ink-3 tnum"><span>0%</span><span>50%</span><span>100%</span></div>
  </div>;
}

export function Metric({ label, children, accent = false }: { label: string; children: ReactNode; accent?: boolean }) {
  return <div className="min-w-0">
    <dt className="text-[12px] text-ink-2">{label}</dt>
    <dd className={cn("mt-1 break-words text-[22px] font-semibold leading-tight tnum", accent && "text-accent-ink")}>{children}</dd>
  </div>;
}

export function Breakdown({ items }: { items: { label: string; value: string; color: string; amount: number }[] }) {
  const total = items.reduce((sum, item) => sum + Math.max(0, item.amount), 0);
  return <div className="grid gap-3">
    <div className="flex h-3 overflow-hidden rounded-full bg-surface-3" aria-hidden>
      {items.map((item) => item.amount > 0 ? <div key={item.label} style={{ width: `${item.amount / total * 100}%`, backgroundColor: item.color }} /> : null)}
    </div>
    <dl className="grid gap-2 text-[12px]">
      {items.map((item) => <div key={item.label} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <dt className="flex items-center gap-2 text-ink-2"><i className="size-2 shrink-0 rounded-full" style={{ backgroundColor: item.color }} />{item.label}</dt>
        <dd className="font-medium tnum">{item.value}</dd>
      </div>)}
    </dl>
  </div>;
}
