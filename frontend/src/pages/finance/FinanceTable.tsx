import { ChevronRight } from "lucide-react";

import type { FinanceRow } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { hm, money } from "@/lib/format";

import { sumAmounts } from "./amounts";

export function FinanceTable({ rows, onSelect }: { rows: FinanceRow[]; onSelect: (id: number) => void }) {
  if (!rows.length) return <p className="rounded-lg border border-line bg-surface p-10 text-center text-ink-2">По этому отбору сотрудников нет.</p>;
  const totals = sumAmounts(rows);
  return (
    <>
      <div className="hidden overflow-x-auto rounded-lg border border-line bg-surface md:block">
        <table className="w-full min-w-[860px] border-collapse text-[13px]">
          <caption className="sr-only">Расчёт оплаты по сотрудникам</caption>
          <thead className="border-b border-line bg-surface-2/60 text-right text-[12px] text-ink-3">
            <tr>{["Сотрудник", "Норма / ставка", "Оклад", "Переработка", "Проектные премии", "Итого", ""].map((title, index) => (
              <th key={index} scope="col" className={`whitespace-nowrap px-4 py-3 font-medium ${index === 0 ? "text-left" : ""}`}>{title || <span className="sr-only">Подробнее</span>}</th>
            ))}</tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.employee.id} className="border-b border-line last:border-0 hover:bg-surface-2/40">
                <th scope="row" className="px-4 py-4 text-left font-normal">
                  <button className="flex max-w-64 items-center gap-2.5 rounded text-left" onClick={() => onSelect(row.employee.id)} aria-label={`Расчёт: ${row.employee.short_name}`}>
                    <Avatar employee={row.employee} size={32} />
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{row.employee.short_name}</span>
                      <span className="block truncate text-[12px] text-ink-3">{row.employee.position}</span>
                      {!row.employee.is_active ? <Badge className="mt-1">В архиве</Badge> : null}
                    </span>
                  </button>
                </th>
                <td className="whitespace-nowrap px-4 py-4 text-right tnum">
                  <div>{hm(row.summary.norm_sec)} ч</div>
                  <div className="text-[12px] text-ink-3">{money(row.summary.hourly_rate)} / ч</div>
                  {Number(row.summary.hourly_rate) === 0 ? <Badge tone="deviation">Нет ставки</Badge> : null}
                </td>
                <td className="whitespace-nowrap px-4 py-4 text-right tnum">{money(row.amounts.salary ?? "0")}</td>
                <td className="whitespace-nowrap px-4 py-4 text-right tnum">
                  <div>{money(row.amounts.overtime_pay ?? "0")}</div>
                  <div className="text-[12px] text-ink-3">{hm(row.summary.overtime_sec)} ч сверх нормы</div>
                </td>
                <td className="whitespace-nowrap px-4 py-4 text-right tnum">{money(row.amounts.project_bonuses ?? "0")}</td>
                <td className="whitespace-nowrap px-4 py-4 text-right font-semibold tnum">{money(row.amounts.total ?? "0")}</td>
                <td className="pr-3"><Button size="icon-sm" variant="ghost" onClick={() => onSelect(row.employee.id)} aria-label={`Подробнее: ${row.employee.short_name}`}><ChevronRight /></Button></td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t border-line bg-surface-2/60 text-right font-semibold tnum">
            <tr><th colSpan={2} className="px-4 py-3 text-left font-medium">Итого по отбору · {rows.length}</th>
              {[totals.salary, totals.overtime_pay, totals.project_bonuses, totals.total].map((value, i) => <td key={i} className="whitespace-nowrap px-4 py-3">{money(value ?? "0")}</td>)}<td />
            </tr>
          </tfoot>
        </table>
      </div>
      <div className="grid gap-3 md:hidden">
        {rows.map((row) => (
          <button key={row.employee.id} onClick={() => onSelect(row.employee.id)} className="rounded-lg border border-line bg-surface p-4 text-left" aria-label={`Расчёт: ${row.employee.short_name}`}>
            <span className="flex items-center gap-2.5"><Avatar employee={row.employee} size={32} /><span className="min-w-0 flex-1"><span className="block truncate font-medium">{row.employee.short_name}</span><span className="text-[12px] text-ink-3">{row.employee.is_active ? row.employee.position : "В архиве"}</span></span><ChevronRight className="size-4 text-ink-3" /></span>
            <span className="mt-3 block font-display text-[24px] font-semibold tnum">{money(row.amounts.total ?? "0")}</span>
            <span className="mt-3 grid grid-cols-[1fr_auto] gap-x-2 gap-y-1 text-[12px] text-ink-2 tnum">
              <span>Оклад</span><span>{money(row.amounts.salary ?? "0")}</span>
              <span>Переработка · {hm(row.summary.overtime_sec)} ч</span><span>{money(row.amounts.overtime_pay ?? "0")}</span>
              <span>Проектные премии</span><span>{money(row.amounts.project_bonuses ?? "0")}</span>
            </span>
            {Number(row.summary.hourly_rate) === 0 ? <Badge tone="deviation" className="mt-2">Не указана ставка</Badge> : null}
          </button>
        ))}
      </div>
    </>
  );
}
