import { ArrowRight, GitCompareArrows } from "lucide-react";

import type { PlanDay, ScheduleChangePreview } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { dayMonth, hm, WEEKDAYS_SHORT, weekday } from "@/lib/format";
import { TaskList } from "./TaskList";

function planText(plan: PlanDay | null) {
  if (!plan) return "Расписание не задано";
  if (plan.kind === "off") return `Выходной${plan.note ? ` · ${plan.note}` : ""}`;
  if (plan.kind === "note") return plan.note || "Пометка без времени";
  const intervals = plan.intervals.map(([start, end]) => `${hm(start)}–${hm(end)}`).join(" · ");
  return `${intervals}${plan.note ? ` · ${plan.note}` : ""}`;
}

export function ScheduleComparison({ preview, pending = true }: { preview: ScheduleChangePreview; pending?: boolean }) {
  return (
    <section
      aria-label="Изменения расписания"
      className="grid min-w-0 gap-3 rounded-md border border-line bg-surface-2/30 p-3"
    >
      <h3 className="flex flex-wrap items-center gap-2 text-[13px] font-semibold">
        <GitCompareArrows className="size-4 text-accent-ink" />
        Изменения расписания<Badge>Версия {preview.version}</Badge>
      </h3>
      <div className="grid max-h-96 min-w-0 gap-3 overflow-y-auto pr-1">
        {preview.days.map((day) => {
          const approval = pending && preview.late_change && day.affects_calculation;
          const before = approval ? day.current.plan : day.previous;
          const after = approval ? day.if_accepted.plan : day.submitted;
          return (
            <section key={day.date} className="min-w-0 rounded border border-line bg-surface p-3">
              <h4 className="mb-2 text-[12px] font-semibold">
                {WEEKDAYS_SHORT[weekday(day.date)]}, {dayMonth(day.date)}
              </h4>
              <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 text-[12px]">
                <div className="min-w-0">
                  <p className="mb-1 text-[11px] text-ink-3">{approval ? "В таблице сейчас" : "Предыдущая версия"}</p>
                  <p className="break-words font-medium tnum">{planText(before)}</p>
                </div>
                <ArrowRight className="size-3.5 text-ink-3" />
                <div className="min-w-0">
                  <p className="mb-1 text-[11px] text-ink-3">{approval ? "После одобрения" : "Новая версия"}</p>
                  <p className="break-words font-medium tnum">{planText(after)}</p>
                </div>
              </div>
              {approval ? (
                <div className="mt-3 border-t border-line pt-2 text-[12px]">
                  {day.current.fact ? (
                    <>
                      <p className="text-ink-3">
                        Дейлик:{" "}
                        {day.current.fact.intervals.map(([start, end]) => `${hm(start)}–${hm(end)}`).join(" · ")}
                      </p>
                      <p className="mt-1 font-medium">
                        Опоздание:{" "}
                        <span className="tnum">
                          {day.current.late_sec == null ? "не рассчитывается" : hm(day.current.late_sec)} →{" "}
                          {day.if_accepted.late_sec == null ? "не рассчитывается" : hm(day.if_accepted.late_sec)}
                        </span>
                      </p>
                      {day.current.late_sec &&
                      (day.if_accepted.late_sec == null || day.if_accepted.late_sec < day.current.late_sec) ? (
                        <p className="mt-1 text-deviation-ink">
                          По новому плану учтённое опоздание уменьшится или перестанет рассчитываться.
                        </p>
                      ) : null}
                    </>
                  ) : (
                    <p className="text-ink-3">Дейлика ещё нет. Опоздание будет рассчитано после его получения.</p>
                  )}
                </div>
              ) : pending && preview.late_change ? (
                <p className="mt-3 border-t border-line pt-2 text-[12px] text-ink-3">
                  Одобрение не изменит текущий расчёт этого дня: уже действует такой же или более новый план.
                </p>
              ) : null}
            </section>
          );
        })}
        {!preview.days.length ? <p className="text-[12px] text-ink-3">Время и пометки дней не изменились.</p> : null}
      </div>
      {preview.tasks_added.length ? (
        <div>
          <p className="mb-2 text-[12px] font-medium text-accent-ink">
            Добавлены задачи · {preview.tasks_added.length}
          </p>
          <TaskList tasks={preview.tasks_added} previewCount={3} label="Добавленные задачи" />
        </div>
      ) : null}
      {preview.tasks_removed.length ? (
        <div>
          <p className="mb-2 text-[12px] font-medium text-late-ink">Убраны задачи · {preview.tasks_removed.length}</p>
          <TaskList tasks={preview.tasks_removed} previewCount={3} label="Убранные задачи" />
        </div>
      ) : null}
    </section>
  );
}
