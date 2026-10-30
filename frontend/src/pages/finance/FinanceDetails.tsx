import { Pencil, Plus, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import type { FinanceRow, ProjectBonus } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { hm, money } from "@/lib/format";

import { BonusForm, CancelBonus } from "./BonusForm";

export function FinanceDetails({ row, year, month, label, onClose }: { row: FinanceRow; year: number; month: number; label: string; onClose: () => void }) {
  const admin = useIsAdmin();
  const [editing, setEditing] = useState<ProjectBonus | "new" | null>(null);
  const [cancelling, setCancelling] = useState<ProjectBonus | null>(null);
  const s = row.summary;
  return (
    <>
      <Sheet open onOpenChange={(open) => { if (!open) onClose(); }}>
        <SheetContent title={row.employee.full_name} subtitle={`${label} · расчёт оплаты`}>
          <div className="grid gap-6">
            <div className="rounded-lg bg-accent-soft/50 p-4">
              <p className="text-[13px] text-ink-2">Итого по расчёту</p>
              <p className="mt-1 font-display text-[32px] font-semibold tracking-tight text-accent-ink tnum">{money(row.amounts.total)}</p>
              <p className="mt-1 text-[12px] text-ink-3">Оклад + переработка + проектные премии</p>
            </div>
            <section>
              <h2 className="mb-3 font-semibold">Как получилась сумма</h2>
              <dl className="grid gap-4 text-[13px]">
                <div><dt className="flex justify-between gap-3"><span className="font-medium">Оклад</span><span className="font-semibold tnum">{money(row.amounts.salary)}</span></dt><dd className="mt-1 text-ink-2">{hm(s.norm_sec)} ч нормы × {money(s.hourly_rate)} / ч. Выплачивается полностью при недоработке.</dd></div>
                <div><dt className="flex justify-between gap-3"><span className="font-medium">За переработку</span><span className="font-semibold tnum">{money(row.amounts.overtime_pay)}</span></dt><dd className="mt-1 text-ink-2">{hm(s.overtime_sec)} ч сверх нормы × {money(s.hourly_rate)} / ч.</dd></div>
                <div><dt className="flex justify-between gap-3"><span className="font-medium">Проектные премии</span><span className="font-semibold tnum">{money(row.amounts.project_bonuses)}</span></dt><dd className="mt-1 text-ink-2">Сумма действующих премий за этот месяц.</dd></div>
              </dl>
            </section>
            <section className="rounded-lg border border-line p-4">
              <h2 className="font-semibold">Часы для расчёта переработки</h2>
              <dl className="mt-3 grid grid-cols-[1fr_auto] gap-x-3 gap-y-2 text-[13px] tnum">
                <dt className="text-ink-2">По дейликам</dt><dd>{hm(s.worked_sec)}</dd>
                <dt className="text-ink-2">С учётом эффективности</dt><dd>{hm(s.result_sec)}</dd>
                <dt className="text-ink-2">Штраф за опоздания</dt><dd>− {hm(s.penalty_sec)}</dd>
                <dt className="font-medium">Зачтено</dt><dd className="font-semibold">{hm(s.total_sec)}</dd>
                <dt className="text-ink-2">Месячная норма</dt><dd>{hm(s.norm_sec)}</dd>
              </dl>
              <p className="mt-3 text-[12px] text-ink-3">Переработка появляется, когда зачтённые часы превышают норму. Оклад от этих часов не уменьшается.</p>
              {s.days_missing || s.days_without_efficiency || !s.days_worked ? <p className="mt-3 text-[12px] text-deviation-ink">{!s.days_worked ? "В этом месяце пока нет дейликов. " : ""}{s.days_missing ? `Дней без дейлика: ${s.days_missing}. ` : ""}{s.days_without_efficiency ? `Дейликов без эффективности: ${s.days_without_efficiency}. ` : ""}После уточнения данных переработка может измениться.</p> : null}
              {!Number(s.hourly_rate) ? <p className="mt-3 text-[12px] text-deviation-ink">Ставка не указана: оклад и переработка равны нулю. Укажите ставку в карточке сотрудника.</p> : null}
              <Button asChild variant="link" className="mt-3"><Link to={`/month/${year}/${month}`}>Открыть таблицу месяца</Link></Button>
            </section>
            <section>
              <div className="mb-3 flex items-center justify-between gap-3"><h2 className="font-semibold">Проектные премии</h2>{admin ? <Button size="sm" onClick={() => setEditing("new")}><Plus /> Добавить</Button> : null}</div>
              {!row.bonuses.length ? <p className="rounded-lg border border-dashed border-line p-4 text-[13px] text-ink-3">За этот месяц премий пока нет.{admin ? " Добавьте сумму и название проекта." : " Их добавляет администратор."}</p> : (
                <ul className="grid gap-3">{row.bonuses.map((bonus) => (
                  <li key={bonus.id} className="rounded-lg border border-line p-3">
                    <div className="flex flex-wrap items-baseline justify-between gap-2"><h3 className="min-w-0 break-words font-medium">{bonus.title}</h3><span className={`whitespace-nowrap font-semibold tnum ${bonus.cancelled_at ? "text-ink-3 line-through" : ""}`}>{money(bonus.amount)}</span></div>
                    {bonus.note ? <p className="mt-2 whitespace-pre-wrap break-words text-[13px] text-ink-2">{bonus.note}</p> : null}
                    {bonus.cancelled_at ? <div className="mt-2"><Badge>Отменена</Badge><p className="mt-1 break-words text-[12px] text-ink-3">{bonus.cancel_reason}</p></div> : admin ? <div className="mt-3 flex gap-2"><Button size="sm" variant="ghost" onClick={() => setEditing(bonus)}><Pencil /> Изменить</Button><Button size="sm" variant="ghost" onClick={() => setCancelling(bonus)}><X /> Отменить</Button></div> : null}
                  </li>
                ))}</ul>
              )}
            </section>
            <div className="flex flex-wrap gap-3"><Button asChild><Link to={`/people/${row.employee.id}`}>Профиль сотрудника</Link></Button>{admin ? <Button asChild><Link to={`/admin/employees?edit=${row.employee.id}`}>Норма и ставка</Link></Button> : null}</div>
          </div>
        </SheetContent>
      </Sheet>
      {editing ? <BonusForm month={`${year}-${String(month).padStart(2, "0")}-01`} label={label} employeeId={row.employee.id} bonus={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} /> : null}
      {cancelling ? <CancelBonus bonus={cancelling} onClose={() => setCancelling(null)} /> : null}
    </>
  );
}
