import { ChevronDown, ChevronRight } from "lucide-react";
import { Fragment, useState } from "react";

import type { Month, MonthRow } from "@/api/types";
import { cn } from "@/lib/cn";
import { hm, money } from "@/lib/format";

import { EmptyRows, PersonCell, SortTh, td } from "./shared";
import { footLabel, sortRows, useSort } from "./sorting";

/** «Премии за месяц»: переработка от месячной нормы × ставка, с расшифровкой по клику. */
type Key = "name" | "total" | "norm" | "overtime" | "rate" | "bonus";
const GET: Record<Key, (r: MonthRow) => number | string> = {
  name: (r) => r.employee.short_name,
  total: (r) => r.summary.total_sec,
  norm: (r) => r.summary.norm_sec,
  overtime: (r) => r.summary.overtime_sec,
  rate: (r) => Number(r.summary.hourly_rate),
  bonus: (r) => Number(r.summary.bonus),
};

export function BonusTab({ data, rows }: { data: Month; rows: MonthRow[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const { sort, toggle } = useSort<Key>();
  const sorted = sortRows(rows, sort, GET);
  const col = { sort, onSort: toggle };
  const total = rows.reduce((s, r) => s + Number(r.summary.bonus), 0);
  return (
    <div className="grid gap-3">
      <div className="overflow-x-auto rounded-lg border border-line bg-surface">
        <table className="w-full min-w-[720px] border-collapse">
          <caption className="sr-only">Премии за переработку</caption>
          <thead className="border-b border-line bg-surface-2/60 text-left">
            <tr>
              <SortTh label="Сотрудник" sortKey="name" align="left" {...col} />
              <SortTh label="Итого" sortKey="total" {...col} />
              <SortTh label="Норма" sortKey="norm" {...col} />
              <SortTh label="Переработка" sortKey="overtime" {...col} />
              <SortTh label="Ставка, ₽/ч" sortKey="rate" {...col} />
              <SortTh label="Премия" sortKey="bonus" className="text-ink" {...col} />
            </tr>
          </thead>
          <tbody>
            {sorted.length ? null : <EmptyRows colSpan={6} />}
            {sorted.map((r) => {
              const s = r.summary;
              const expanded = open === r.employee.id;
              return (
                <Fragment key={r.employee.id}>
                  <tr
                    className="cursor-pointer border-b border-line hover:bg-surface-2/50"
                    onClick={() => setOpen(expanded ? null : r.employee.id)}
                  >
                    <th scope="row" className="px-3 py-2 text-left font-normal">
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          aria-expanded={expanded}
                          aria-label={`Расшифровка расчёта: ${r.employee.short_name}`}
                          className="rounded p-0.5 text-ink-3 hover:bg-surface-2"
                          onClick={(e) => {
                            e.stopPropagation();
                            setOpen(expanded ? null : r.employee.id);
                          }}
                        >
                          {expanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                        </button>
                        <PersonCell employee={r.employee} position={r.employee.position} />
                      </div>
                    </th>
                    <td className={cn(td, "text-right")}>{hm(s.total_sec)}</td>
                    <td className={cn(td, "text-right text-ink-2")}>{hm(s.norm_sec)}</td>
                    <td className={cn(td, "text-right", s.overtime_sec > 0 && "font-medium text-accent-ink")}>
                      {s.overtime_sec > 0 ? hm(s.overtime_sec) : "—"}
                    </td>
                    <td className={cn(td, "text-right text-ink-2")}>{Number(s.hourly_rate).toLocaleString("ru-RU")}</td>
                    <td className={cn(td, "text-right text-[14px] font-semibold")}>
                      {Number(s.bonus) > 0 ? money(s.bonus) : <span className="font-normal text-ink-3">—</span>}
                    </td>
                  </tr>
                  {expanded ? (
                    <tr className="border-b border-line bg-bg/60">
                      <td colSpan={6} className="px-3 py-3">
                        <Breakdown row={r} />
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
          <tfoot className="border-t border-line bg-surface-2/60">
            <tr>
              <th scope="row" colSpan={5} className="px-3 py-2 text-left text-[12px] font-medium text-ink-3">
                {footLabel(rows.length, data.rows.length, "Всего премий")}
              </th>
              <td className={cn(td, "text-right font-semibold")}>{money(total)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="text-[12px] text-ink-3">
        Переработка = max(0, Итого − норма). Премия = переработка в часах × ставка, считается от месячной нормы, а
        не по дням. Часы считаются точно, а деньги округляются до копеек, поэтому премия может отличаться на копейки
        от расчёта по показанным минутам.
      </p>
    </div>
  );
}

function Breakdown({ row }: { row: MonthRow }) {
  const s = row.summary;
  const lines: [string, string][] = [
    ["Итого", `Часы(e%) ${hm(s.result_sec)} − Опоздания(−) ${hm(s.penalty_sec)} = ${hm(s.total_sec)}`],
    ["Переработка", `max(0, ${hm(s.total_sec)} − норма ${hm(s.norm_sec)}) = ${hm(s.overtime_sec)}`],
    [
      "Премия",
      s.overtime_sec > 0
        ? `${hm(s.overtime_sec)} × ${Number(s.hourly_rate).toLocaleString("ru-RU")} ₽ = ${money(s.bonus)}`
        : "переработки нет, премия не начисляется",
    ],
  ];
  return (
    <dl className="grid gap-1 pl-8 text-[13px] tnum">
      {lines.map(([k, v]) => (
        <div key={k} className="grid grid-cols-[7rem_1fr] gap-3">
          <dt className="text-ink-3">{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}
