import type { Month, MonthRow } from "@/api/types";
import { cn } from "@/lib/cn";
import { hm, percent } from "@/lib/format";

import { EmptyRows, NormBar, PersonCell, SortTh, td } from "./shared";
import { footLabel, sortRows, useSort } from "./sorting";

/** «Итог за месяц» — первая таблица исходного листа: Часы(+), Часы(e%), Опоздания(−), Итого. */
type Key = "name" | "worked" | "result" | "penalty" | "total" | "norm" | "progress";
const GET: Record<Key, (r: MonthRow) => number | string> = {
  name: (r) => r.employee.short_name,
  worked: (r) => r.summary.worked_sec,
  result: (r) => r.summary.result_sec,
  penalty: (r) => r.summary.penalty_sec,
  total: (r) => r.summary.total_sec,
  norm: (r) => r.summary.norm_sec,
  progress: (r) => r.summary.norm_progress,
};

export function SummaryTab({ data, rows }: { data: Month; rows: MonthRow[] }) {
  const { sort, toggle } = useSort<Key>();
  // Шкала полос — по всей команде, чтобы фильтр не менял масштаб.
  const max = Math.max(1, ...data.rows.map((r) => Math.max(r.summary.total_sec, r.summary.norm_sec))) * 1.05;
  const sum = (f: (s: MonthRow["summary"]) => number) => rows.reduce((acc, r) => acc + f(r.summary), 0);
  const sorted = sortRows(rows, sort, GET);
  const col = { sort, onSort: toggle };
  return (
    <div className="grid gap-3">
      <div className="overflow-x-auto rounded-lg border border-line bg-surface">
        <table className="w-full min-w-[820px] border-collapse">
          <caption className="sr-only">Итог за месяц по сотрудникам</caption>
          <thead className="border-b border-line bg-surface-2/60 text-left">
            <tr>
              <SortTh label="Сотрудник" sortKey="name" align="left" {...col} />
              <SortTh label="Часы(+)" sortKey="worked" title="Сумма часов по дням" {...col} />
              <SortTh label="Часы(e%)" sortKey="result" title="Сумма итогов по дням: часы × e%" {...col} />
              <SortTh label="Опоздания(−)" sortKey="penalty" title="Штраф за опоздания по прогрессивной шкале" {...col} />
              <SortTh label="Итого" sortKey="total" className="text-ink" {...col} />
              <SortTh label="Норма" sortKey="norm" {...col} />
              <SortTh label="Выполнение нормы" sortKey="progress" align="left" className="w-[22%]" {...col} />
            </tr>
          </thead>
          <tbody>
            {sorted.length ? null : <EmptyRows colSpan={7} />}
            {sorted.map((r) => {
              const s = r.summary;
              return (
                <tr key={r.employee.id} className="border-b border-line last:border-b-0">
                  <th scope="row" className="px-3 py-2 text-left font-normal">
                    <PersonCell employee={r.employee} position={r.employee.position} />
                  </th>
                  <td className={cn(td, "text-right")}>{hm(s.worked_sec)}</td>
                  <td className={cn(td, "text-right")}>{hm(s.result_sec)}</td>
                  <td className={cn(td, "text-right", s.penalty_sec > 0 && "text-late-ink")}>
                    {s.penalty_sec > 0 ? `−${hm(s.penalty_sec)}` : "—"}
                  </td>
                  <td className={cn(td, "text-right text-[14px] font-semibold")}>{hm(s.total_sec)}</td>
                  <td className={cn(td, "text-right text-ink-2")}>{hm(s.norm_sec)}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-3">
                      <NormBar total={s.total_sec} norm={s.norm_sec} max={max} />
                      <span className={cn("w-12 text-right text-[12px] tnum", s.norm_progress >= 1 ? "font-semibold text-accent-ink" : "text-ink-2")}>
                        {percent(s.norm_progress)}
                      </span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot className="border-t border-line bg-surface-2/60">
            <tr className="text-[13px] tnum">
              <th scope="row" className="px-3 py-2 text-left text-[12px] font-medium text-ink-3">
                {footLabel(rows.length, data.rows.length, "Команда")}
              </th>
              <td className={cn(td, "text-right")}>{hm(sum((s) => s.worked_sec))}</td>
              <td className={cn(td, "text-right")}>{hm(sum((s) => s.result_sec))}</td>
              <td className={cn(td, "text-right", sum((s) => s.penalty_sec) > 0 ? "text-late-ink" : "text-ink-3")}>
                {sum((s) => s.penalty_sec) > 0 ? `−${hm(sum((s) => s.penalty_sec))}` : "—"}
              </td>
              <td className={cn(td, "text-right font-semibold")}>{hm(sum((s) => s.total_sec))}</td>
              <td className={cn(td, "text-right text-ink-2")}>{hm(sum((s) => s.norm_sec))}</td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="text-[12px] text-ink-3">
        Итого = Часы(e%) − Опоздания(−). Опоздания(−) — штраф по прогрессивной шкале от суммы опозданий за
        месяц (вкладка «Опоздания»). Норма фиксированная и не уменьшается из-за отпусков и праздников. Риска на полосе —
        норма.
      </p>
    </div>
  );
}
