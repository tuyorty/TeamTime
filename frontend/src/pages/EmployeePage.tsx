import { ArrowLeft, AtSign, Flame, ListChecks, NotebookPen, Target } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { useAudit, useEmployee, useMeta } from "@/api/queries";
import type { EmployeeDetail } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { DayDetailSheet, type DayRef } from "@/components/domain/DayDetail";
import { ErrorState, TruncationNote } from "@/components/domain/feedback";
import { STATUS } from "@/components/domain/states";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { WEEKDAYS_SHORT, count, dateTime, ddmm, hm, money, percent, weekday } from "@/lib/format";

import { NormBar } from "./month/shared";
import { EfficiencyChart, HoursChart, Punctuality } from "./employee/Charts";
import { MonthHeatmap } from "./employee/Heatmap";

export default function EmployeePage() {
  const id = Number(useParams().id);
  const { data, error, refetch } = useEmployee(id);
  const today = useMeta().data?.today;
  const [selected, setSelected] = useState<DayRef | null>(null);

  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!data || !today) {
    return (
      <div className="grid gap-4" aria-busy>
        <Skeleton className="h-16 w-80" />
        <Skeleton className="h-24" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }
  const e = data.employee;
  const brief = { id: e.id, short_name: e.short_name, full_name: e.full_name, position: e.position, color: e.color, is_active: e.is_active };

  return (
    <div className="grid gap-5">
      <Link to="/people" className="inline-flex w-fit items-center gap-1 text-[13px] text-ink-2 hover:text-ink">
        <ArrowLeft className="size-4" /> Люди
      </Link>
      <header className="flex flex-wrap items-center gap-4">
        <Avatar employee={brief} size={56} />
        <div className="min-w-0">
          <h1 className="font-display text-[26px] font-semibold leading-tight tracking-tight">{e.full_name}</h1>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-2">
            <span>{e.position || "Должность не указана"}</span>
            <span className="text-ink-3">в расписании: «{e.short_name}»</span>
            {data.identities.map((i) => (
              <span key={i.id} className="inline-flex items-center gap-0.5 text-ink-3">
                <AtSign className="size-3.5" />
                {i.username ?? i.display_name}
              </span>
            ))}
            {!e.is_active ? <Badge>не активен</Badge> : null}
          </p>
        </div>
      </header>

      <MonthStrip data={data} />

      <div className="grid gap-5 lg:grid-cols-2">
        <HoursChart data={data} />
        <EfficiencyChart data={data} />
        <MonthHeatmap data={data} today={today} />
        <div className="grid content-start gap-5">
          <Punctuality data={data} />
          <StreaksPanel data={data} />
        </div>
      </div>

      <RecentDays data={data} onOpen={(c) => setSelected({ employee: brief, cell: c })} />

      <div className="grid gap-5 lg:grid-cols-2">
        <TasksPanel data={data} />
        <NotesPanel data={data} />
      </div>
      <HistoryPanel employeeId={e.id} />
      <TruncationNote />
      <DayDetailSheet value={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function MonthStrip({ data }: { data: EmployeeDetail }) {
  const s = data.month;
  return (
    <section aria-label="Текущий месяц" className="grid gap-4 rounded-lg border border-line bg-surface p-4 md:grid-cols-[minmax(0,1.4fr)_repeat(4,minmax(0,1fr))]">
      <div className="grid content-start gap-2">
        <span className="text-[12px] text-ink-2">Итого за месяц и норма</span>
        <span className="font-display text-[30px] font-semibold leading-none tnum">
          {hm(s.total_sec)} <span className="text-[16px] font-medium text-ink-3">из {hm(s.norm_sec)}</span>
        </span>
        <NormBar total={s.total_sec} norm={s.norm_sec} max={Math.max(s.total_sec, s.norm_sec) * 1.1 || 1} />
        <span className={cn("text-[12px] tnum", s.norm_progress >= 1 ? "font-semibold text-accent-ink" : "text-ink-3")}>
          {percent(s.norm_progress)} нормы
        </span>
      </div>
      {[
        { label: "Часы(+)", value: hm(s.worked_sec), hint: `${count(s.days_worked, ["день", "дня", "дней"])} с дейликом` },
        { label: "Часы(e%)", value: hm(s.result_sec), hint: s.days_without_efficiency ? `без e%: ${s.days_without_efficiency}` : "по дейликам" },
        {
          label: "Опоздания(−)",
          value: s.penalty_sec ? `−${hm(s.penalty_sec)}` : "—",
          hint: s.late_count ? `${count(s.late_count, ["опоздание", "опоздания", "опозданий"])}, ${hm(s.late_total_sec)}` : "опозданий нет",
          tone: s.penalty_sec ? "text-late-ink" : "",
        },
        {
          label: "Премия",
          value: Number(s.bonus) > 0 ? money(s.bonus) : "—",
          hint: s.overtime_sec ? `переработка ${hm(s.overtime_sec)}` : `ставка ${Number(s.hourly_rate).toLocaleString("ru-RU")} ₽/ч`,
        },
      ].map((it) => (
        <div key={it.label} className="grid content-start gap-1 border-line md:border-l md:pl-4">
          <span className="text-[12px] text-ink-2">{it.label}</span>
          <span className={cn("font-display text-[20px] font-semibold tnum", it.tone)}>{it.value}</span>
          <span className="text-[12px] text-ink-3">{it.hint}</span>
        </div>
      ))}
    </section>
  );
}

function StreaksPanel({ data }: { data: EmployeeDetail }) {
  const s = data.streaks;
  return (
    <Panel title="Серии" description="Считаются по дням с дейликом">
      <dl className="grid grid-cols-3 gap-3">
        {[
          { icon: Target, label: "без опозданий сейчас", value: s.current_on_time },
          { icon: Flame, label: "лучшая серия без опозданий", value: s.best_on_time },
          { icon: ListChecks, label: "рабочих дней подряд с дейликом", value: s.current_dailies },
        ].map((it) => (
          <div key={it.label} className="grid gap-1">
            <it.icon className="size-4 text-ink-3" />
            <dd className="font-display text-[22px] font-semibold leading-none tnum">{it.value}</dd>
            <dt className="text-[12px] leading-4 text-ink-2">{it.label}</dt>
          </div>
        ))}
      </dl>
    </Panel>
  );
}

function RecentDays({ data, onOpen }: { data: EmployeeDetail; onOpen: (c: EmployeeDetail["days"][number]) => void }) {
  const days = [...data.days].reverse().filter((d) => d.fact || d.plan || d.status).slice(0, 14);
  return (
    <Panel title="Последние дни" description="План против факта. Нажмите на день, чтобы увидеть задачи и исходное сообщение" bodyClassName="px-0 pb-0">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-[13px]">
          <thead className="border-y border-line bg-surface-2/60 text-left text-[12px] text-ink-3">
            <tr>
              <th scope="col" className="px-4 py-2 font-medium">День</th>
              <th scope="col" className="px-3 py-2 font-medium">План</th>
              <th scope="col" className="px-3 py-2 font-medium">Факт</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Часы</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">e%</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Итог</th>
              <th scope="col" className="px-4 py-2 font-medium">Отметки</th>
            </tr>
          </thead>
          <tbody>
            {days.map((d) => (
              <tr key={d.date} className="cursor-pointer border-b border-line last:border-b-0 hover:bg-surface-2/50" onClick={() => onOpen(d)}>
                <th scope="row" className="px-4 py-2 text-left font-normal whitespace-nowrap tnum">
                  <button type="button" className="text-left hover:underline" onClick={() => onOpen(d)}>
                    {WEEKDAYS_SHORT[weekday(d.date)]} {ddmm(d.date)}
                  </button>
                </th>
                <td className="px-3 py-2 text-ink-2 tnum">
                  {d.plan?.kind === "work" ? `${hm(d.plan.start)}–${hm(d.plan.end)}` : d.plan?.kind === "off" ? "выходной" : d.plan?.note ? <i>{d.plan.note}</i> : "—"}
                </td>
                <td className="px-3 py-2 tnum">{d.fact ? d.fact.intervals.map(([a, b]) => `${hm(a)}–${hm(b)}`).join("; ") : d.status ? STATUS[d.status].label : d.state === "missing" ? "нет дейлика" : "—"}</td>
                <td className="px-3 py-2 text-right tnum">{d.fact ? hm(d.fact.worked_sec) : "—"}</td>
                <td className="px-3 py-2 text-right tnum">{d.fact?.efficiency ?? "—"}</td>
                <td className="px-3 py-2 text-right font-medium tnum">{d.fact?.result_sec !== null && d.fact?.result_sec !== undefined ? hm(d.fact.result_sec) : "—"}</td>
                <td className="px-4 py-2">
                  <span className="flex flex-wrap gap-1">
                    {d.late_sec ? <Badge tone="late">опоздание {hm(d.late_sec)}</Badge> : null}
                    {d.early_leave_sec ? <Badge tone="deviation">ранний уход {hm(d.early_leave_sec)}</Badge> : null}
                    {d.no_plan ? <Badge>без плана</Badge> : null}
                    {d.fact?.edited ? <Badge tone="outline">правка</Badge> : null}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function TasksPanel({ data }: { data: EmployeeDetail }) {
  return (
    <Panel title="Задачи спринта и сделанное" description="Слева — из расписания, справа — из дейликов">
      <div className="grid max-h-[28rem] gap-4 overflow-y-auto pr-1">
        {data.tasks.slice(0, 6).map((w) => (
          <section key={`${w.iso_year}-${w.iso_week}`} className="grid gap-2">
            <h3 className="text-[13px] font-semibold">{w.label}</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <ul className="grid content-start gap-1 text-[13px]">
                {w.planned.length ? (
                  w.planned.map((t, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="mt-[7px] size-1.5 shrink-0 rounded-full border border-ink-3" />
                      {t}
                    </li>
                  ))
                ) : (
                  <li className="text-ink-3">задач в расписании нет</li>
                )}
              </ul>
              <ul className="grid content-start gap-1 text-[13px] text-ink-2">
                {w.done.length ? (
                  w.done.flatMap(([day, tasks]) =>
                    tasks.map((t, i) => (
                      <li key={`${day}-${i}`} className="flex gap-2">
                        <span className="mt-[7px] size-1.5 shrink-0 rounded-full bg-accent" />
                        <span>
                          {t} <span className="text-[11px] text-ink-3 tnum">{ddmm(day)}</span>
                        </span>
                      </li>
                    )),
                  )
                ) : (
                  <li className="text-ink-3">дейликов с задачами нет</li>
                )}
              </ul>
            </div>
          </section>
        ))}
      </div>
    </Panel>
  );
}

function NotesPanel({ data }: { data: EmployeeDetail }) {
  return (
    <Panel title="Заметки и статусы" description="Свободный текст из расписаний и отметки дней">
      {data.notes.length ? (
        <ul className="grid max-h-[28rem] gap-2 overflow-y-auto pr-1">
          {data.notes.map((n, i) => {
            const S = n.status ? STATUS[n.status] : null;
            return (
              <li key={i} className="flex items-start gap-2.5 text-[13px]">
                <span className="w-[4.5rem] shrink-0 whitespace-nowrap text-ink-3 tnum">
                  {WEEKDAYS_SHORT[weekday(n.date)]} {ddmm(n.date)}
                </span>
                {S ? (
                  <Badge tone={S.tone === "absence" ? "absence" : "neutral"}>
                    <S.icon /> {S.label}
                  </Badge>
                ) : (
                  <NotebookPen className="mt-0.5 size-3.5 shrink-0 text-ink-3" />
                )}
                <span className="text-ink-2">{n.kind === "status" && S && n.text === S.label ? "" : n.text}</span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-[13px] text-ink-2">Ни заметок, ни статусов за период.</p>
      )}
    </Panel>
  );
}

const ACTION_LABEL: Record<string, string> = {
  "daily.set": "факт исправлен",
  "daily.retract": "факт убран",
  "plan_day.set": "план дня изменён",
  "status.set": "статус",
  "status.clear": "статус снят",
  "employee.create": "добавлен в справочник",
  "employee.update": "карточка изменена",
  "identity.link": "привязан аккаунт Telegram",
};

function HistoryPanel({ employeeId }: { employeeId: number }) {
  const { data } = useAudit(employeeId);
  const items = (data ?? []).filter((a) => a.actor !== "seed").slice(0, 15);
  if (!items.length) return null;
  return (
    <Panel title="Журнал правок" description="Кто, когда и что поменял по этому сотруднику">
      <ul className="grid gap-1.5 text-[13px]">
        {items.map((a) => (
          <li key={a.id} className="flex flex-wrap gap-x-3">
            <span className="text-ink-3 tnum">{dateTime(a.at)}</span>
            <span>{ACTION_LABEL[a.action] ?? a.action}</span>
            <span className="text-ink-3">{a.actor === "admin" ? "админ" : a.actor.startsWith("bot:") ? "через бота" : a.actor}</span>
            {a.reason ? <span className="text-ink-2">«{a.reason}»</span> : null}
          </li>
        ))}
      </ul>
    </Panel>
  );
}
