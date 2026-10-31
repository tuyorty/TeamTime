import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Clock3, MapPin, Monitor, MoonStar, Users, WifiOff } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "@/api/client";
import { useMeta } from "@/api/queries";
import type { Meta, Today, TodayRow } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { AxisTicks, DayStrip } from "@/components/domain/DayStrip";
import { STATUS } from "@/components/domain/states";
import { clock, count, dayMonth, timezoneLabel, WEEKDAYS_LONG, weekday } from "@/lib/format";
import { useRealtime } from "@/lib/realtime";
import { useTheme } from "@/lib/theme";
import { axisFor, type Axis } from "@/lib/axis";
import { scheduleCell } from "@/lib/schedule";

import { GROUPS, groupCounts, groupFor, nextDate, sortTeam, timedPlan, tomorrowSummary, tvClock, upcomingEvents, type TvEvent } from "./tv/model";
import "./tv/tv.css";

/** Экран офиса: только расписание, автоматическое обновление и смена страниц. */
export default function TvPage() {
  useRealtime(false);
  useTheme();
  const meta = useMeta();
  const today = useQuery({
    queryKey: ["today", "tv"],
    queryFn: () => api.get<Today>("/today"),
    refetchInterval: 30_000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: "always",
  });
  const tomorrowDate = today.data ? nextDate(today.data.date) : undefined;
  const tomorrow = useQuery({
    queryKey: ["today", "tv", tomorrowDate],
    queryFn: () => api.get<Today>(`/today?day=${tomorrowDate}`),
    enabled: !!tomorrowDate,
    refetchInterval: 60_000,
    refetchOnWindowFocus: "always",
  });
  const [tick, setTick] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setTick(Date.now()), 5_000);
    const visible = () => { if (!document.hidden) setTick(Date.now()); };
    document.addEventListener("visibilitychange", visible);
    const previousTitle = document.title;
    document.title = "xTime · Команда сегодня";
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", visible);
      document.title = previousTitle;
    };
  }, []);

  const data = today.data;
  const counts = data ? groupCounts(data.rows) : null;
  const serverNow = meta.data ? new Date(Date.parse(meta.data.now) + (
    meta.data.demo ? 0 : Math.max(0, tick - meta.dataUpdatedAt)
  )) : null;
  const serverDay = meta.data && serverNow
    ? new Intl.DateTimeFormat("en-CA", { timeZone: meta.data.timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(serverNow)
    : data?.date;
  const stale = today.isError || meta.isError || (!!data && (tick - today.dataUpdatedAt > 90_000 || serverDay !== data.date));
  const updatedTime = clock(data?.now_sec);

  return (
    <main className="tv-screen" aria-label="Экран команды для телевизора">
      <header className="tv-header">
        <div>
          <div className="tv-eyebrow"><span className="tv-brand">
            <svg width="28" height="28" viewBox="0 0 22 22" aria-hidden>
              <rect x="1.5" y="6.5" width="19" height="9" rx="2.5" fill="none" stroke="var(--ink-3)" />
              <rect x="6" y="8.5" width="12.5" height="5" rx="1.5" fill="var(--accent)" />
              <rect x="1.5" y="6.5" width="4.5" height="9" rx="2.5" fill="var(--late)" />
            </svg>
            xTime
          </span><span>Расписание команды</span></div>
          <h1>Сегодня{data ? <><span className="tv-separator"> · </span>{dayMonth(data.date)}</> : null}</h1>
          <p className="tv-weekday">{data ? WEEKDAYS_LONG[weekday(data.date)] : "Загружаем расписание"}</p>
        </div>
        <div className="tv-clock">
          {meta.data ? <TeamClock key={meta.data.demo ? meta.data.now : "live"} meta={meta.data} updatedAt={meta.dataUpdatedAt} /> : <time aria-label="Текущее время команды">—:—:—</time>}
          <span>{meta.data ? timezoneLabel(meta.data.timezone, meta.data.now) : "Время команды"}</span>
        </div>
      </header>

      {data ? <>
        <section className="tv-summary" aria-label="Команда по расписанию сейчас">
          <div className="tv-summary-heading"><h2><Users aria-hidden />Вся команда <strong>{data.rows.length}</strong></h2><span>Сейчас по расписанию</span></div>
          <div className="tv-stats">
          {GROUPS.map((group) => <div key={group.key} className="tv-stat" data-tone={group.key}>
            <span className="tv-stat-value">{counts![group.key]}</span>
            <span className="tv-stat-label"><i />{group.label}</span>
          </div>)}
          </div>
        </section>
        <div className="tv-content">
          <Team key={data.date} rows={data.rows} now={data.now_sec} />
          <aside className="tv-aside" aria-label="Ближайшее по расписанию">
            <Upcoming rows={data.rows} now={data.now_sec} />
            <Tomorrow date={tomorrowDate!} data={tomorrow.data} error={tomorrow.isError} />
          </aside>
        </div>
      </> : <div className="tv-waiting" role="status">
        {today.isError ? <WifiOff /> : <CalendarDays />}
        <h2>{today.isError ? "Ждём соединения с сервером" : "Загружаем расписание"}</h2>
        <p>{today.isError ? "Экран обновится автоматически, когда связь восстановится." : "Скоро здесь появится день команды."}</p>
      </div>}

      <footer className="tv-footer">
        <span><MapPin aria-hidden />Время и место работы — по расписанию</span>
        <span className={stale ? "tv-connection tv-connection-stale" : "tv-connection"} role="status">
          <i />{stale ? `Нет свежих данных · обновлено в ${updatedTime}` : data ? `Обновлено в ${updatedTime}` : "Подключаемся"}
          {meta.data?.demo ? " · Демо" : ""}
        </span>
      </footer>
    </main>
  );
}

/** Секундный тик обновляет только часы; демо не сбрасывается при повторном запросе meta. */
function TeamClock({ meta, updatedAt }: { meta: Meta; updatedAt: number }) {
  const [startedAt] = useState(() => Date.now());
  const [tick, setTick] = useState(startedAt);
  useEffect(() => {
    const update = () => setTick(Date.now());
    const timer = window.setInterval(update, 1_000);
    const visible = () => { if (!document.hidden) update(); };
    document.addEventListener("visibilitychange", visible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", visible);
    };
  }, []);
  const now = new Date(Date.parse(meta.now) + Math.max(0, tick - (meta.demo ? startedAt : updatedAt)));
  const time = new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23", timeZone: meta.timezone,
  }).format(now);
  return <time dateTime={now.toISOString()} aria-label="Текущее время команды">{time}</time>;
}

function Team({ rows, now }: { rows: TodayRow[]; now: number }) {
  const [size, setSize] = useState(() => capacity());
  const [page, setPage] = useState(0);
  const sorted = sortTeam(rows);
  const axis = axisFor(rows.filter((row) => row.presence !== "off" && row.presence !== "absent").map(scheduleCell), { start: 8 * 3600, end: 22 * 3600 });
  const pages = Math.max(1, Math.ceil(rows.length / size));
  const currentPage = page % pages;
  useEffect(() => {
    const resize = () => setSize(capacity());
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  useEffect(() => {
    if (pages === 1) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) setPage((value) => (value + 1) % pages);
    }, 15_000);
    return () => window.clearInterval(timer);
  }, [pages]);
  return <section className="tv-team" aria-label="Расписание сотрудников">
    <div className="tv-section-heading">
      <div><h2>День команды</h2><p>Время и место работы — по расписанию команды</p></div>
      <span>{pages > 1 ? `Страница ${currentPage + 1} из ${pages}` : count(rows.length, ["сотрудник", "сотрудника", "сотрудников"])}</span>
    </div>
    {rows.length ? <>
      <div className="tv-columns"><span>Сотрудник</span><AxisTicks axis={axis} className="tv-axis" /></div>
      <div className="tv-people" data-testid="tv-people" style={{ gridTemplateRows: `repeat(${Math.min(size, rows.length)}, minmax(0, 1fr))` }}>
        {sorted.slice(currentPage * size, (currentPage + 1) * size).map((row) => <Person key={row.employee.id} row={row} axis={axis} now={now} />)}
      </div>
      <div className="tv-team-foot"><span><i />Линия на шкале — сейчас</span><span>{pages > 1 ? "Страницы меняются каждые 15 с" : "Все сотрудники на экране"}</span></div>
    </> : <div className="tv-empty-team"><h2>Команда пока не добавлена</h2><p>Сотрудники появятся здесь после настройки справочника.</p></div>}
  </section>;
}

function capacity() {
  if (window.innerWidth < 750) return window.innerHeight < 650 ? 2 : 3;
  return window.innerHeight >= 900 ? 9 : window.innerHeight >= 650 ? 6 : 4;
}

function Person({ row, axis, now }: { row: TodayRow; axis: Axis; now: number }) {
  const group = groupFor(row);
  const plan = timedPlan(row);
  const away = group === "off" || group === "absent";
  const remote = !away && row.cell.status === "remote";
  const label = away
    ? row.presence === "off" ? "Выходной" : row.cell.status ? STATUS[row.cell.status].label : "Не работает"
    : group === "unknown" ? "Время не указано"
      : group === "later" ? "Начнёт позже"
        : group === "finished" ? "День завершён по плану"
          : remote ? "Удалённо по плану" : "В офисе по плану";
  return <article className="tv-person" data-tone={group} aria-label={`${row.employee.short_name}: ${label}`}>
    <div className="tv-person-head">
      <Avatar employee={row.employee} size={44} className="tv-avatar" />
      <div><h3>{row.employee.short_name}</h3>
        <p className="tv-person-status"><i />{away ? "Не работает сегодня" : group === "unknown" ? remote ? "Удалённо · без времени" : "Нужно расписание" : label}</p>
      </div>
    </div>
    <div className="tv-person-schedule">
      {!away && plan ? <>
        <div className="tv-plan-label">
          <strong>{plan.intervals.map(([start, end]) => `${tvClock(start)}–${tvClock(end)}`).join(" · ")}</strong>
          {plan.intervals.length > 1 ? <span className="tv-interval-count">{count(plan.intervals.length, ["интервал", "интервала", "интервалов"])}</span> : null}
          <span className="tv-person-location">{remote ? <Monitor aria-hidden /> : <MapPin aria-hidden />}{remote ? "Удалённо" : "Офис"}</span>
        </div>
        <DayStrip cell={scheduleCell(row)} axis={axis} now={now} height={12} label={`Рабочее время по расписанию: ${row.employee.short_name}`} className="tv-strip" />
      </> : <p className="tv-person-day-label">{label}</p>}
    </div>
  </article>;
}

function eventLabel(event: TvEvent) {
  return event.kind === "end" ? "Конец рабочего дня" : event.row.cell.status === "remote" ? "Начало удалённо" : "Начало в офисе";
}

function Upcoming({ rows, now }: { rows: TodayRow[]; now: number }) {
  const events = upcomingEvents(rows, now).slice(0, 6);
  return <section className="tv-upcoming">
    <h2><Clock3 aria-hidden />Дальше по расписанию</h2>
    <p className="tv-aside-description">Ближайшие начала и окончания работы</p>
    {events.length ? <ol className="tv-events">{events.map((event) => <li key={`${event.row.employee.id}-${event.kind}`}>
        <time>{tvClock(event.time)}</time>
        <div><strong>{event.row.employee.short_name}</strong><span>{eventLabel(event)}</span></div>
      </li>)}</ol> : <div className="tv-quiet"><MoonStar /><strong>Дальше без изменений</strong><p>По расписанию на сегодня больше нет начал и окончаний работы.</p></div>}
  </section>;
}

function Tomorrow({ date, data, error }: { date: string; data?: Today; error: boolean }) {
  const summary = data ? tomorrowSummary(data.rows) : null;
  return <section className="tv-tomorrow">
    <h2><CalendarDays aria-hidden />Завтра <span>{dayMonth(date)}</span></h2>
    {summary && !error ? <>
      <div className="tv-tomorrow-counts">
        <div><strong>{summary.office}</strong><span>офис</span></div>
        <div><strong>{summary.remote}</strong><span>удалённо</span></div>
        <div><strong>{summary.away}</strong><span>не работают</span></div>
      </div>
      <p className="tv-tomorrow-note">{summary.firstStart !== null ? <>Первое начало в <strong>{tvClock(summary.firstStart)}</strong></> : "Рабочее время пока не запланировано"}</p>
      {summary.unknown > 0 ? <p className="tv-tomorrow-missing">Без времени в расписании: {summary.unknown}</p> : null}
    </> : <p className="tv-tomorrow-note">{error ? "Пока не удалось обновить расписание" : "Загружаем расписание…"}</p>}
  </section>;
}
