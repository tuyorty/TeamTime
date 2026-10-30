import { ArrowUpRight, Clock3, ListChecks, Moon, Sparkles, Sun, Timer, Users } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import type { HighlightRecord, PeriodHighlights } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import { count, dayMonth, hm, isoWeek, parseDate, rangeShort } from "@/lib/format";

function dayHref(day: string, employeeId?: number) {
  if (!employeeId) return `/?view=summary&date=${day}`;
  const week = isoWeek(parseDate(day));
  return `/week/${week.year}/${week.week}?day=${day}&e=${employeeId}`;
}

function timeLabel(value: number) {
  const days = Math.floor(value / 86400);
  return `${hm(value % 86400)}${days ? ` (+${days} дн.)` : ""}`;
}

function RecordCard({
  title,
  record,
  clock = false,
  empty,
  icon: Icon,
  tone = false,
  onNavigate,
}: {
  title: string;
  record: HighlightRecord | null | undefined;
  clock?: boolean;
  empty: string;
  icon: typeof Sun;
  tone?: boolean;
  onNavigate: () => void;
}) {
  return (
    <section className="min-w-0 rounded-lg border border-line bg-surface p-4">
      <h3 className="flex items-center gap-2 text-[13px] font-medium text-ink-2">
        <Icon className="size-4 shrink-0 text-ink-3" />
        {title}
      </h3>
      {record ? (
        <>
          <p className={cn("mt-3 font-display text-[28px] font-semibold tnum", tone && "text-late-ink")}>
            {clock ? timeLabel(record.value_sec) : hm(record.value_sec)}
          </p>
          <ul className="mt-3 grid gap-2">
            {record.occurrences.map((entry, index) => (
              <li key={index} className="flex min-w-0 items-center gap-2 text-[12px]">
                {entry.employee ? <Avatar employee={entry.employee} size={22} /> : null}
                <Link
                  to={dayHref(entry.date, entry.employee?.id)}
                  onClick={onNavigate}
                  className="group min-w-0 flex-1 hover:text-accent-ink"
                >
                  <span className="flex items-center gap-1 font-medium">
                    {entry.employee?.short_name ?? dayMonth(entry.date)}
                    <ArrowUpRight className="size-3 shrink-0 opacity-50 group-hover:opacity-100" />
                  </span>
                  <span className="text-[11px] text-ink-3">
                    {entry.employee
                      ? dayMonth(entry.date)
                      : count(entry.participants ?? 0, [
                          "сотрудник с дейликом",
                          "сотрудника с дейликом",
                          "сотрудников с дейликом",
                        ])}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          {record.total_occurrences > record.occurrences.length ? (
            <p className="mt-2 text-[11px] text-ink-3">
              Ещё{" "}
              {count(record.total_occurrences - record.occurrences.length, ["совпадение", "совпадения", "совпадений"])}{" "}
              с таким же значением.
            </p>
          ) : null}
        </>
      ) : (
        <p className="mt-4 text-[13px] text-ink-3">{empty}</p>
      )}
    </section>
  );
}

export function PeriodFacts({
  data,
  period,
  start,
  end,
  incomplete = false,
  disabled = false,
}: {
  data: PeriodHighlights;
  period: "week" | "month";
  start: string;
  end: string;
  incomplete?: boolean;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const title = period === "week" ? "Факты недели" : "Факты месяца";
  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)} disabled={disabled}>
        <Sparkles />
        {title}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          title={title}
          description={`${rangeShort(start, end)} · вся команда, по данным дейликов`}
          className="top-[5vh] max-h-[90dvh] w-[min(94vw,58rem)] overflow-y-auto"
        >
          {incomplete ? (
            <Badge tone="deviation" className="mb-4">
              Период ещё идёт — факты предварительные
            </Badge>
          ) : null}
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: "Дейликов", value: data.reported_days },
              { label: "Сотрудников с дейликом", value: data.employees_reported },
              { label: "Отработано", value: hm(data.worked_sec) },
              { label: "Без дейлика за прошедшие дни", value: data.missing_days },
              { label: "Работа в выходные по календарю", value: hm(data.calendar_off_sec ?? 0) },
              { label: "Вечерние и ночные часы · 20:00–06:00", value: hm(data.evening_night_sec ?? 0) },
              { label: "Дней дольше 10 часов", value: data.long_days ?? 0 },
              { label: "Самая длинная серия дней с работой", value: data.longest_daily_series ?? 0 },
              { label: "Изменённых дней расписания", value: data.changed_schedule_days ?? 0 },
            ].map((item) => (
              <div key={item.label} className="rounded-md bg-surface-2/70 p-3">
                <p className="font-display text-[23px] font-semibold tnum">{item.value}</p>
                <p className="mt-1 text-[11px] text-ink-3">{item.label}</p>
              </div>
            ))}
          </div>
          {data.reported_days ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <RecordCard
                title="Самое раннее начало"
                icon={Sun}
                onNavigate={() => setOpen(false)}
                clock
                record={data.earliest_start}
                empty="Нет времени начала."
              />
              <RecordCard
                title="Самое позднее окончание"
                icon={Moon}
                onNavigate={() => setOpen(false)}
                clock
                record={data.latest_finish}
                empty="Нет времени окончания."
              />
              <RecordCard
                title="Самый длинный рабочий день"
                icon={Timer}
                onNavigate={() => setOpen(false)}
                record={data.longest_day}
                empty="Нет данных о часах."
              />
              <RecordCard
                title="Самое большое опоздание"
                icon={Clock3}
                onNavigate={() => setOpen(false)}
                record={data.largest_lateness}
                tone
                empty={
                  data.comparable_days ? "Опозданий не было." : "Нет дейликов с рабочим расписанием для сравнения."
                }
              />
              <RecordCard
                title="Самый насыщенный день команды"
                icon={Users}
                onNavigate={() => setOpen(false)}
                record={data.busiest_day}
                empty="Нет данных о часах команды."
              />
              <section className="rounded-lg border border-line bg-surface p-4">
                <h3 className="flex items-center gap-2 text-[13px] font-medium text-ink-2">
                  <ListChecks className="size-4 text-ink-3" />
                  Ещё о периоде
                </h3>
                <dl className="mt-4 grid gap-4 text-[12px]">
                  <div>
                    <dt className="text-ink-3">Средний рабочий день по дейликам</dt>
                    <dd className="mt-1 text-[20px] font-semibold tnum">{hm(data.average_day_sec)}</dd>
                  </div>
                  <div>
                    <dt className="text-ink-3">Задач записано в дейликах</dt>
                    <dd className="mt-1 text-[20px] font-semibold tnum">{data.tasks_reported}</dd>
                  </div>
                  <div>
                    <dt className="text-ink-3">Дней без учтённых опозданий</dt>
                    <dd className="mt-1 text-[20px] font-semibold tnum">
                      {data.comparable_days
                        ? `${data.on_time_days} из ${data.comparable_days}`
                        : "Нет дней для сравнения"}
                    </dd>
                  </div>
                </dl>
              </section>
            </div>
          ) : (
            <p className="py-8 text-center text-[13px] text-ink-2">
              За этот период ещё нет дейликов. Факты появятся после первых отчётов.
            </p>
          )}
          <p className="mt-4 text-[11px] leading-relaxed text-ink-3">
            Начало и окончание — из интервалов в дейликах. Длительность — сумма интервалов, без перерывов. Опоздания
            учитывают действующий план и допуски таблицы. Фильтры таблицы на эти факты не влияют. Нажмите на запись,
            чтобы открыть её источник.
          </p>
        </DialogContent>
      </Dialog>
    </>
  );
}
