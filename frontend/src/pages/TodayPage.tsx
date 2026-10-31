import { ArrowRight, CalendarDays, CircleAlert, ListChecks, MapPin, MonitorPlay, PencilLine, Users } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { useMeta, useToday } from "@/api/queries";
import type { FeedItem, Today, TodayRow } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { TaskList } from "@/components/domain/TaskList";
import { DayDetailSheet, type DayRef } from "@/components/domain/DayDetail";
import { AxisTicks, DayStrip } from "@/components/domain/DayStrip";
import { EmptyState, ErrorState } from "@/components/domain/feedback";
import { STATUS } from "@/components/domain/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { Segmented } from "@/components/ui/segmented";
import { axisFor } from "@/lib/axis";
import { cn } from "@/lib/cn";
import {
  WEEKDAYS_LONG,
  clock,
  count,
  dayMonth,
  relative,
  timezoneLabel,
  weekday,
  isoDate,
  parseDate,
} from "@/lib/format";
import { useFlashed } from "@/lib/realtime";
import { scheduleCell } from "@/lib/schedule";
import { DaySummary } from "./DaySummaryPage";

type Presence = TodayRow["presence"];
const PRESENCE: Record<Presence, { label: string; order: number; color: string }> = {
  on_site: { label: "В офисе", order: 0, color: "bg-accent" },
  remote: { label: "На удалёнке", order: 1, color: "bg-sky-500" },
  expected_later: { label: "Начнут позже", order: 2, color: "bg-deviation" },
  left: { label: "Закончили", order: 3, color: "bg-ink-3" },
  off: { label: "Выходной", order: 4, color: "bg-ink-3" },
  absent: { label: "Отсутствуют", order: 5, color: "bg-absence" },
  no_plan: { label: "Нет расписания", order: 6, color: "bg-deviation" },
};

function presenceText(row: TodayRow): string {
  if (row.cell.status && row.presence === "absent") return STATUS[row.cell.status].label;
  if (row.presence === "no_plan" && row.cell.plan?.note) return row.cell.plan.note;
  if (row.presence === "expected_later") return `Начнёт в ${clock(row.cell.plan?.start)}`;
  if (row.presence === "left") return `До ${clock(row.cell.plan?.end)} по расписанию`;
  return PRESENCE[row.presence].label;
}

export default function TodayPage() {
  const meta = useMeta().data;
  const [search, setSearch] = useSearchParams();
  const tomorrow = search.get("day") === "tomorrow";
  const nextDay = meta ? parseDate(meta.today) : null;
  nextDay?.setDate(nextDay.getDate() + 1);
  const { data, error, refetch, isPlaceholderData } = useToday(
    tomorrow && nextDay ? isoDate(nextDay) : undefined,
  );
  const view = !tomorrow && search.get("view") === "summary" ? "summary" : "work";
  const [detail, setDetail] = useState<DayRef | null>(null);
  const [employeeId, setEmployeeId] = useState<number | null>(null);
  const [filter, setFilter] = useState<Presence | null>(null);
  const rows = useMemo(
    () =>
      [...(data?.rows ?? [])].sort(
        (a, b) =>
          PRESENCE[a.presence].order - PRESENCE[b.presence].order ||
          (a.cell.plan?.start ?? 86400) - (b.cell.plan?.start ?? 86400) ||
          a.employee.short_name.localeCompare(b.employee.short_name, "ru"),
      ),
    [data?.rows],
  );

  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!data) return <TodaySkeleton />;
  const selectedDay = tomorrow && nextDay ? isoDate(nextDay) : (meta?.today ?? data.date);
  const currentTime = meta
    ? new Intl.DateTimeFormat("ru-RU", {
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
        timeZone: meta.timezone,
      }).format(new Date(meta.now))
    : clock(data.now_sec);
  const visible = rows.filter((row) => !filter || row.presence === filter);
  const selected = visible.find((row) => row.employee.id === employeeId) ?? visible[0];
  const axis = axisFor(rows.map(scheduleCell), { start: 8 * 3600, end: 22 * 3600 });

  return (
    <div className="grid grid-cols-1 gap-5">
      <header className="grid gap-5">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-4">
          <div className="min-w-0">
            <h1 className="min-h-[2.5em] font-display text-[28px] font-semibold leading-tight sm:min-h-0 tracking-tight sm:text-[40px]">
              {tomorrow ? "Завтра" : "Сегодня"} <span className="text-ink-3">·</span>{" "}
              <span className="whitespace-nowrap">{dayMonth(selectedDay)}</span>
            </h1>
            <div className="mt-2 flex h-5 items-center gap-3 text-[13px]">
              <p className="truncate capitalize text-ink-2">
                {WEEKDAYS_LONG[weekday(selectedDay)]}
                {tomorrow ? " · расписание на завтра" : ""}
              </p>
              {!tomorrow ? <Link to="/tv" target="_blank" rel="noopener noreferrer" className="flex shrink-0 items-center gap-1.5 text-accent-ink hover:underline" aria-label="Открыть экран для телевизора">
                <MonitorPlay className="size-3.5" />Экран ТВ
              </Link> : null}
            </div>
          </div>
          <div className="text-right" aria-label="Часы команды">
            <time
              dateTime={meta?.now}
              className="block font-display text-[36px] font-semibold leading-none tracking-tight tnum sm:text-[48px]"
              aria-label="Текущее время команды"
            >
              {currentTime}
            </time>
            <p className="mt-2 max-w-44 text-[11px] text-ink-3 sm:text-[12px]" title={meta?.timezone}>
              {meta ? timezoneLabel(meta.timezone, meta.now) : "Время команды"}
            </p>
          </div>
        </div>
        <div className="grid gap-3 sm:flex sm:items-center sm:justify-between">
          <div
            role="group"
            aria-label="Выбор дня"
            className="inline-flex h-11 rounded-lg border border-line bg-surface-2 p-1 sm:w-64"
          >
            {(
              [
                ["today", "Сегодня"],
                ["tomorrow", "Завтра"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                aria-pressed={(tomorrow ? "tomorrow" : "today") === key}
                className="flex flex-1 items-center justify-center rounded-md px-4 text-[13px] font-medium text-ink-2 transition-colors hover:bg-surface aria-pressed:bg-surface aria-pressed:text-accent-ink aria-pressed:shadow-sm"
                onClick={() => {
                  setEmployeeId(null);
                  setFilter(null);
                  setSearch((previous) => {
                    const result = new URLSearchParams(previous);
                    if (key === "tomorrow") {
                      result.set("day", key);
                      result.delete("view");
                    } else result.delete("day");
                    return result;
                  });
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <Segmented
            label="Режим Сегодня"
            value={view}
            onChange={(next) =>
              setSearch((previous) => {
                const result = new URLSearchParams(previous);
                if (next === "summary") result.set("view", "summary");
                else result.delete("view");
                return result;
              })
            }
            options={[
              {
                value: "work",
                label: (
                  <>
                    <Users /> Рабочий день
                  </>
                ),
              },
              {
                value: "summary",
                label: (
                  <>
                    <CalendarDays /> Итоги дня
                  </>
                ),
                disabled: tomorrow,
                title: tomorrow ? "Итоги доступны за сегодня и прошедшие дни" : undefined,
              },
            ]}
            className="h-11 w-full sm:w-[21rem] [&_button]:h-9 [&_button]:flex-1 [&_button]:justify-center [&_button]:whitespace-nowrap [&_button]:px-4 [&_button]:text-[13px] [&_button:disabled]:opacity-40"
          />
        </div>
      </header>
      {view === "summary" ? (
        <DaySummary />
      ) : (
        <>
          <KeyNumbers data={data} filter={filter} onFilter={setFilter} future={tomorrow} />
          <div
            className={cn(
              "grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_19rem]",
              isPlaceholderData && "opacity-50",
            )}
            inert={isPlaceholderData}
            aria-busy={isPlaceholderData}
          >
            <div className="grid min-w-0 gap-5">
              <Panel
                title="День команды"
                description="Время и место работы — по расписанию команды"
                actions={
                  filter ? (
                    <Button size="sm" variant="ghost" onClick={() => setFilter(null)}>
                      Показать всех
                    </Button>
                  ) : (
                    <Badge>{count(rows.length, ["сотрудник", "сотрудника", "сотрудников"])}</Badge>
                  )
                }
                bodyClassName="px-0 pb-1"
              >
                {visible.length ? (
                  <>
                    <div className="grid grid-cols-[minmax(10rem,13rem)_1fr_5.5rem] gap-3 px-4 pb-2 max-sm:hidden">
                      <span className="text-[11px] text-ink-3">Сотрудник</span>
                      <AxisTicks axis={axis} />
                      <span />
                    </div>
                    <ul aria-label="Расписание команды" className="divide-y divide-line border-t border-line">
                      {visible.map((row) => (
                        <TeamRow
                          key={row.employee.id}
                          row={row}
                          axis={axis}
                          now={data.now_sec}
                          selected={selected?.employee.id === row.employee.id}
                          onSelect={() => setEmployeeId(row.employee.id)}
                          onDetails={() => setDetail({ employee: row.employee, cell: row.cell })}
                        />
                      ))}
                    </ul>
                  </>
                ) : (
                  <div className="p-4">
                    <EmptyState title={rows.length ? "Здесь пока никого" : "Сотрудников пока нет"}>
                      {rows.length
                        ? "Выберите другую категорию или покажите всю команду."
                        : "Добавьте сотрудников в админке."}
                    </EmptyState>
                  </div>
                )}
                <p className="px-4 pt-3 pb-2 text-[12px] text-ink-3">
                  Нажмите на сотрудника, чтобы увидеть его задачи ниже.
                </p>
              </Panel>
              {selected ? <EmployeeTasks row={selected} /> : null}
            </div>
            <aside className="grid min-w-0 content-start gap-5">
              <Upcoming data={data} />
              <ScheduleFeed items={data.feed} />
            </aside>
          </div>
          <DayDetailSheet value={detail} onClose={() => setDetail(null)} />
        </>
      )}
    </div>
  );
}

function KeyNumbers({
  data,
  filter,
  onFilter,
  future = false,
}: {
  data: Today;
  filter: Presence | null;
  onFilter: (value: Presence | null) => void;
  future?: boolean;
}) {
  return (
    <section
      aria-label="Ключевые числа дня"
      className="overflow-hidden rounded-lg border border-line bg-surface"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
        <button
          type="button"
          onClick={() => onFilter(null)}
          className="flex items-center gap-2 text-[14px] font-semibold"
        >
          <Users className="size-4 text-ink-3" /> Вся команда{" "}
          <span className="tnum text-accent-ink">{data.rows.length}</span>
        </button>
        <span className="text-[12px] text-ink-3">
          {future ? "По расписанию на завтра" : "Сейчас по расписанию"}
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-7">
        {(Object.entries(PRESENCE) as [Presence, (typeof PRESENCE)[Presence]][]).map(([key, item]) => (
          <button
            key={key}
            type="button"
            aria-pressed={filter === key}
            onClick={() => onFilter(filter === key ? null : key)}
            className={cn(
              "grid min-h-23 content-center gap-2 border-line px-4 py-3 text-left transition-colors hover:bg-surface-2",
              filter === key && "bg-accent/8 ring-1 ring-inset ring-accent/40",
            )}
          >
            <span className="font-display text-[30px] font-semibold leading-none tnum">
              {data.counts[key] ?? 0}
            </span>
            <span className="flex items-center gap-1.5 text-[12px] text-ink-2">
              <span className={cn("size-1.5 shrink-0 rounded-full", item.color)} />
              {item.label}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function TeamRow({
  row,
  axis,
  now,
  selected,
  onSelect,
  onDetails,
}: {
  row: TodayRow;
  axis: ReturnType<typeof axisFor>;
  now: number;
  selected: boolean;
  onSelect: () => void;
  onDetails: () => void;
}) {
  const flashed = useFlashed(row.employee.id, row.cell.date);
  const timed = row.cell.plan?.kind === "work" && row.presence !== "absent" && row.presence !== "off";
  return (
    <li
      className={cn(
        "flex items-center gap-1 pr-3 transition-colors",
        selected ? "bg-accent/6" : "hover:bg-surface-2/60",
        flashed && "flash",
      )}
    >
      <button
        type="button"
        aria-label={`Задачи: ${row.employee.short_name}`}
        aria-pressed={selected}
        onClick={onSelect}
        className={cn(
          "grid min-w-0 flex-1 grid-cols-[minmax(10rem,13rem)_1fr] items-center gap-x-3 gap-y-2 border-l-2 px-3.5 py-3 text-left max-sm:grid-cols-1",
          selected ? "border-accent" : "border-transparent",
        )}
      >
        <span className="flex min-w-0 items-center gap-2.5">
          <Avatar employee={row.employee} size={32} />
          <span className="min-w-0">
            <span className="block truncate text-[13px] font-semibold">{row.employee.short_name}</span>
            <span className="mt-0.5 flex items-center gap-1 text-[11px] text-ink-3">
              <span className={cn("size-1.5 shrink-0 rounded-full", PRESENCE[row.presence].color)} />
              {presenceText(row)}
            </span>
          </span>
        </span>
        <span className="grid min-w-0 gap-1.5">
          {timed ? (
            <>
              <span className="flex flex-wrap items-center gap-x-2 text-[12px]">
                <span className="font-medium tnum">
                  {row.cell.plan!.intervals.map(([a, b]) => `${clock(a)}–${clock(b)}`).join(" · ")}
                </span>
                <span className="ml-auto text-[11px] text-ink-3">
                  {row.cell.status === "remote" ? "Удалённо" : "Офис"}
                </span>
              </span>
              <DayStrip
                label="Рабочее время по расписанию"
                cell={scheduleCell(row)}
                axis={axis}
                now={now}
                height={10}
              />
            </>
          ) : (
            <span className="flex min-h-8 items-center rounded-md bg-surface-2/60 px-2 text-[12px] text-ink-2">
              {row.presence === "off"
                ? "В этот день не работает"
                : row.cell.status_note || row.cell.plan?.note || presenceText(row)}
            </span>
          )}
        </span>
      </button>
      <Button
        size="sm"
        variant="ghost"
        aria-label={`Подробнее: ${row.employee.short_name}`}
        onClick={onDetails}
        className="shrink-0 text-[11px]"
      >
        Подробнее
      </Button>
    </li>
  );
}

export function EmployeeTasks({ row }: { row: TodayRow }) {
  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          <ListChecks className="size-4 text-accent-ink" /> Задачи · {row.employee.short_name}
        </span>
      }
      description="Из расписания на текущую неделю"
      actions={
        <Link
          to={`/people/${row.employee.id}`}
          className="flex items-center gap-1 text-[12px] text-accent-ink hover:underline"
        >
          Профиль <ArrowRight className="size-3.5" />
        </Link>
      }
    >
      {row.cell.plan?.note ? (
        <p className="mb-3 rounded-md bg-surface-2 px-3 py-2 text-[13px] text-ink-2">
          <span className="font-medium text-ink">Примечание к дню: </span>
          {row.cell.plan.note}
        </p>
      ) : null}
      {row.tasks?.length ? (
        <TaskList key={row.employee.id} tasks={row.tasks} numbered label="Задачи выбранного сотрудника" />
      ) : (
        <p className="py-2 text-[13px] text-ink-2">Задачи в расписании не указаны.</p>
      )}
    </Panel>
  );
}

function Upcoming({ data }: { data: Today }) {
  const changes = data.rows
    .flatMap((row) => {
      if (
        !row.cell.plan ||
        row.cell.plan.kind !== "work" ||
        row.presence === "absent" ||
        row.presence === "off"
      )
        return [];
      return [
        { row, time: row.cell.plan.start, start: true },
        { row, time: row.cell.plan.end, start: false },
      ].filter((event) => event.time !== null && event.time! > data.now_sec);
    })
    .sort(
      (a, b) => a.time! - b.time! || a.row.employee.short_name.localeCompare(b.row.employee.short_name, "ru"),
    )
    .slice(0, 6);
  return (
    <Panel title="Дальше по расписанию" description="Ближайшие начала и окончания работы">
      {changes.length ? (
        <ul className="grid gap-3.5">
          {changes.map(({ row, time, start }) => (
            <li key={`${row.employee.id}-${start}`} className="flex items-start gap-2.5">
              <span className="mt-0.5 rounded bg-surface-2 px-1.5 py-0.5 text-[12px] font-medium tnum">
                {clock(time)}
              </span>
              <div className="min-w-0">
                <Link
                  to={`/people/${row.employee.id}`}
                  className="block truncate text-[12px] font-medium hover:text-accent-ink"
                >
                  {row.employee.short_name}
                </Link>
                <span className="text-[11px] text-ink-3">
                  {start
                    ? row.cell.status === "remote"
                      ? "Начнёт удалённо"
                      : "Начнёт в офисе"
                    : "Закончит работу"}
                </span>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[13px] text-ink-2">На сегодня больше нет запланированных изменений.</p>
      )}
      <p className="mt-4 flex items-start gap-1.5 border-t border-line pt-3 text-[11px] text-ink-3">
        <MapPin className="mt-0.5 size-3.5 shrink-0" /> Присутствие определяется расписанием.
      </p>
    </Panel>
  );
}

function ScheduleFeed({ items }: { items: FeedItem[] }) {
  return (
    <Panel title="Изменения расписания">
      {items.length ? (
        <ul className="divide-y divide-line">
          {items.slice(0, 5).map((item) => (
            <li key={item.id} className="flex gap-2 py-2 first:pt-0">
              <Avatar
                employee={
                  item.employee ?? {
                    id: 0,
                    short_name: item.author_name,
                    full_name: item.author_name,
                    position: "",
                    color: "",
                    is_active: true,
                    avatar_url: "",
                  }
                }
                size={24}
              />
              <div className="min-w-0">
                <p className="text-[12px] font-medium">{item.employee?.short_name ?? item.author_name}</p>
                <p className="text-[12px] text-ink-2">{item.summary}</p>
                <p className="mt-1 flex items-center gap-1 text-[11px] text-ink-3">
                  {relative(item.at)}
                  {item.edited ? <PencilLine className="size-3" /> : null}
                  {item.resolution === "pending" ? (
                    <Link to="/inbox" aria-label="Проблема в инбоксе">
                      <CircleAlert className="size-3 text-deviation-ink" />
                    </Link>
                  ) : null}
                </p>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[13px] text-ink-2">Новых расписаний пока нет.</p>
      )}
    </Panel>
  );
}

function TodaySkeleton() {
  return (
    <div className="grid gap-5" aria-busy>
      <Skeleton className="h-20 w-80" />
      <Skeleton className="h-36" />
      <div className="grid gap-5 xl:grid-cols-[1fr_19rem]">
        <Skeleton className="h-96" />
        <Skeleton className="h-80" />
      </div>
    </div>
  );
}
