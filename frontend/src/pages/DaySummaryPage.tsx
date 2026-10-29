import { ArrowLeft, ArrowRight, CheckCircle2, ChevronLeft, ChevronRight, Clock3 } from "lucide-react";
import { useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router";

import { useDaySummary, useMeta } from "@/api/queries";
import type { TodayRow } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { DayDetailSheet, type DayRef } from "@/components/domain/DayDetail";
import { ErrorState } from "@/components/domain/feedback";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { clock, dayMonth, hm, isoDate, parseDate } from "@/lib/format";

function shiftDay(day: string, delta: number) {
  const value = parseDate(day);
  value.setDate(value.getDate() + delta);
  return isoDate(value);
}

function waitingForDaily(row: TodayRow) {
  return (
    row.cell.plan?.kind === "work" &&
    row.cell.plan.planned_sec &&
    !row.cell.fact &&
    !["absent", "off"].includes(row.presence)
  );
}

/** Сохраняем ранее выданные ссылки; отдельного раздела итогов больше нет. */
export default function DaySummaryRedirect() {
  const [search] = useSearchParams();
  const next = new URLSearchParams(search);
  next.set("view", "summary");
  return <Navigate to={`/?${next}`} replace />;
}

export function DaySummary() {
  const { data: meta } = useMeta();
  const [search, setSearch] = useSearchParams();
  const requested = search.get("date");
  const validDate =
    requested &&
    /^\d{4}-\d{2}-\d{2}$/.test(requested) &&
    !Number.isNaN(parseDate(requested).getTime()) &&
    isoDate(parseDate(requested)) === requested;
  const day = meta ? (validDate && requested <= meta.today ? requested : shiftDay(meta.today, -1)) : undefined;
  const { data, error, refetch } = useDaySummary(day);
  const [detail, setDetail] = useState<DayRef | null>(null);
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!data || !meta || !day)
    return (
      <div className="grid gap-5" aria-busy>
        <Skeleton className="h-20" />
        <Skeleton className="h-28" />
        <Skeleton className="h-96" />
      </div>
    );
  const waiting = data.rows.filter(waitingForDaily);
  const received = data.rows.filter((row) => row.cell.fact);
  const late = received.filter((row) => row.cell.late_sec);
  const rows = [...data.rows]
    .filter((row) => row.cell.fact || waitingForDaily(row))
    .sort(
      (a, b) =>
        Number(!!a.cell.fact) - Number(!!b.cell.fact) ||
        a.employee.short_name.localeCompare(b.employee.short_name, "ru"),
    );
  const changeDay = (date: string) =>
    setSearch((previous) => {
      const next = new URLSearchParams(previous);
      next.set("view", "summary");
      next.set("date", date);
      return next;
    });
  const isToday = day === meta.today;

  return (
    <div className="grid grid-cols-1 gap-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-[22px] font-semibold">Итоги дня</h2>
          <p className="mt-1 text-[13px] text-ink-2">
            {dayMonth(day)} ·{" "}
            {isToday ? "День ещё идёт, итоги предварительные" : "Часы, задачи и опоздания по дейликам"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="icon" aria-label="Предыдущий день" onClick={() => changeDay(shiftDay(day, -1))}>
            <ChevronLeft />
          </Button>
          <Input
            type="date"
            aria-label="Дата итогов"
            className="w-36"
            value={day}
            max={meta.today}
            onChange={(event) => event.target.value && changeDay(event.target.value)}
          />
          <Button
            size="icon"
            aria-label="Следующий день"
            disabled={day >= meta.today}
            onClick={() => changeDay(shiftDay(day, 1))}
          >
            <ChevronRight />
          </Button>
          <Button size="sm" variant="ghost" onClick={() => changeDay(meta.today)}>
            За сегодня
          </Button>
        </div>
      </header>
      <section aria-label="Итоги по дейликам" className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          { label: "Прислали дейлик", value: received.length },
          { label: isToday ? "Ещё не прислали" : "Без дейлика", value: waiting.length },
          { label: "Отработано командой", value: hm(data.worked_sec) },
          { label: "Опоздания по дейликам", value: late.length },
        ].map((item) => (
          <div key={item.label} className="rounded-lg border border-line bg-surface p-4">
            <p className="font-display text-[30px] font-semibold tnum">{item.value}</p>
            <p className="mt-1 text-[12px] text-ink-2">{item.label}</p>
          </div>
        ))}
      </section>
      <Panel
        title={`Отчёты за ${dayMonth(day)}`}
        description={
          isToday
            ? "Дейлики появятся по мере завершения работы."
            : "В списке сотрудники с рабочим расписанием или дейликом за эту дату."
        }
      >
        {rows.length ? (
          <ul className="divide-y divide-line">
            {rows.map((row) => (
              <li
                key={row.employee.id}
                className="grid grid-cols-[2rem_minmax(0,1fr)] items-start gap-3 py-3 sm:flex sm:items-center"
              >
                <Avatar employee={row.employee} size={32} />
                <div className="min-w-0 flex-1">
                  <Link to={`/people/${row.employee.id}`} className="text-[13px] font-semibold hover:text-accent-ink">
                    {row.employee.short_name}
                  </Link>
                  <p className="mt-0.5 text-[12px] text-ink-3">
                    {row.cell.plan?.kind === "work"
                      ? `Расписание ${clock(row.cell.plan.start)}–${clock(row.cell.plan.end)}`
                      : "Без рабочего расписания"}
                  </p>
                  {row.cell.fact?.tasks.length ? (
                    <p className="mt-1 max-w-xl text-[12px] text-ink-2">{row.cell.fact.tasks.join(" · ")}</p>
                  ) : null}
                </div>
                <div className="col-span-2 flex flex-wrap items-center justify-between gap-2 pl-11 sm:contents">
                  <div className="grid justify-items-start gap-1 sm:justify-items-end">
                    {row.cell.fact ? (
                      <>
                        <span className="flex items-center gap-1 text-[13px] font-medium tnum">
                          <CheckCircle2 className="size-3.5 text-accent" />
                          {hm(row.cell.fact.worked_sec)}
                          {row.cell.fact.efficiency != null ? ` · ${row.cell.fact.efficiency}%` : ""}
                        </span>
                        <span className={cn("text-[12px]", row.cell.late_sec ? "text-late-ink" : "text-ink-3")}>
                          {row.cell.late_sec
                            ? `Опоздание ${hm(row.cell.late_sec)}`
                            : row.cell.late_sec === 0
                              ? "Без опоздания"
                              : "Опоздание не рассчитывается"}
                        </span>
                      </>
                    ) : (
                      <Badge
                        className="whitespace-normal"
                        tone={isToday && !row.daily_overdue ? undefined : "deviation"}
                      >
                        <Clock3 />
                        {isToday
                          ? row.daily_overdue
                            ? "Работа закончилась, дейлика нет"
                            : "Рабочий день ещё идёт"
                          : "Дейлик не прислан"}
                      </Badge>
                    )}
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Подробнее: ${row.employee.short_name}`}
                    onClick={() => setDetail({ employee: row.employee, cell: row.cell })}
                  >
                    Подробнее
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="py-5 text-[13px] text-ink-2">На эту дату нет рабочих смен и дейликов.</p>
        )}
      </Panel>
      <div className="flex flex-wrap justify-between gap-3 text-[13px]">
        <Link to="/" className="flex items-center gap-1 text-ink-2 hover:text-ink">
          <ArrowLeft className="size-4" /> К расписанию
        </Link>
        <Link to="/week" className="flex items-center gap-1 text-accent-ink hover:underline">
          Таблица недели <ArrowRight className="size-4" />
        </Link>
      </div>
      <DayDetailSheet value={detail} onClose={() => setDetail(null)} />
    </div>
  );
}
