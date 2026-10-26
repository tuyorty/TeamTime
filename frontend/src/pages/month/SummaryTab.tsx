import type { Month } from "@/api/types";
import { cn } from "@/lib/cn";
import { hm, percent } from "@/lib/format";

import { NormBar, NumTh, PersonCell, td, th } from "./shared";

/** «Итог за месяц» — первая таблица исходного листа: Часы(+), Часы(e%), Опоздания(−), Итого. */
export function SummaryTab({ data }: { data: Month }) {
  const max = Math.max(1, ...data.rows.map((r) => Math.max(r.summary.total_sec, r.summary.norm_sec))) * 1.05;
  const sum = (f: (s: Month["rows"][number]["summary"]) => number) => data.rows.reduce((acc, r) => acc + f(r.summary), 0);
  return (
    <div className="grid gap-3">
      <div className="overflow-x-auto rounded-lg border border-line bg-surface">
        <table className="w-full min-w-[820px] border-collapse">
          <caption className="sr-only">Итог за месяц по сотрудникам</caption>
          <thead className="border-b border-line bg-surface-2/60 text-left">
            <tr>
              <th scope="col" className={th}>Сотрудник</th>
              <NumTh title="Сумма часов по дням">Часы(+)</NumTh>
              <NumTh title="Сумма итогов по дням: часы × e%">Часы(e%)</NumTh>
              <NumTh title="Штраф за опоздания по прогрессивной шкале">Опоздания(−)</NumTh>
              <NumTh className="text-ink">Итого</NumTh>
              <NumTh>Норма</NumTh>
              <th scope="col" className={cn(th, "w-[22%]")}>Выполнение нормы</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => {
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
              <th scope="row" className="px-3 py-2 text-left text-[12px] font-medium text-ink-3">Команда</th>
              <td className={cn(td, "text-right")}>{hm(sum((s) => s.worked_sec))}</td>
              <td className={cn(td, "text-right")}>{hm(sum((s) => s.result_sec))}</td>
              <td className={cn(td, "text-right text-late-ink")}>−{hm(sum((s) => s.penalty_sec))}</td>
              <td className={cn(td, "text-right font-semibold")}>{hm(sum((s) => s.total_sec))}</td>
              <td className={cn(td, "text-right text-ink-2")}>{hm(sum((s) => s.norm_sec))}</td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="text-[12px] text-ink-3">
        Итого = Часы(e%) − Опоздания(−). Опоздания(−) — штраф по прогрессивной шкале от суммы опозданий за
        месяц (вкладка «Опоздания»). Норма фиксированная и не уменьшается из-за отпусков и праздников. Чёрная риска на
        полосе — норма.
      </p>
    </div>
  );
}
