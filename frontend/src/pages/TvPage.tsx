import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Clock3, MapPin, Monitor, Users, WifiOff } from "lucide-react";
import { Fragment, useEffect, useRef, useState } from "react";
import { employeeGroups } from "@/lib/departments";

import { api } from "@/api/client";
import { useMeta } from "@/api/queries";
import type { Meta, Today, TodayRow } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { AxisTicks, DayStrip } from "@/components/domain/DayStrip";
import { TeamTimeline } from "@/components/domain/TeamTimeline";
import { STATUS } from "@/components/domain/states";
import { clock, count, dayMonth, timezoneLabel, WEEKDAYS_LONG, weekday } from "@/lib/format";
import { useRealtime } from "@/lib/realtime";
import { useTheme } from "@/lib/theme";
import { axisFor, type Axis } from "@/lib/axis";
import { scheduleCell } from "@/lib/schedule";

import { GROUPS, groupCounts, groupFor, sortTeam, timedPlan, tvClock, upcomingEvents } from "./tv/model";
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
        <div className="tv-content">
          <Team key={data.date} rows={data.rows} now={data.now_sec} />
          <aside className="tv-aside" aria-label="Команда и ближайшие события">
          <section className="tv-summary" aria-label="Команда по расписанию сейчас">
            <div className="tv-summary-heading"><h2><Users aria-hidden />Вся команда <strong>{data.rows.length}</strong></h2><span>Сейчас по расписанию</span></div>
            <div className="tv-stats">
              {GROUPS.map((group) => <div key={group.key} className="tv-stat" data-tone={group.key}>
                <span className="tv-stat-value">{counts![group.key]}</span>
                <span className="tv-stat-label"><i />{group.label}</span>
              </div>)}
            </div>
          </section>
          <Upcoming rows={data.rows} now={data.now_sec} />
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
  const people = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState(() => capacity());
  const [page, setPage] = useState(0);
  const sorted = sortTeam(rows);
  const axis = axisFor(rows.filter((row) => row.presence !== "off" && row.presence !== "absent").map(scheduleCell), { start: 8 * 3600, end: 22 * 3600 });
  const pages = Math.max(1, Math.ceil(rows.length / size));
  const currentPage = page % pages;
  const shownGroups = employeeGroups(sorted.slice(currentPage * size, (currentPage + 1) * size));
  const maxIntervals = Math.max(0, ...rows.map((row) => row.cell.plan?.intervals.length ?? 0));
  useEffect(() => {
    const element = people.current;
    if (!element) return;
    const resize = () => {
      const rowHeight = window.innerWidth < 750 ? 96 : maxIntervals >= 5 ? 60 : 37;
      const headings = employeeGroups(rows).length * 20;
      setSize(Math.max(1, Math.floor((element.clientHeight - headings) / rowHeight)));
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    return () => observer.disconnect();
  }, [rows, maxIntervals]);
  useEffect(() => {
    if (pages === 1) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) setPage((value) => (value + 1) % pages);
    }, 15_000);
    return () => window.clearInterval(timer);
  }, [pages]);
  return <section className="tv-team" aria-label="Расписание сотрудников">
    <div className="tv-section-heading">
      <div><h2>День команды</h2></div>
      <span>{pages > 1 ? `Страница ${currentPage + 1} из ${pages}` : count(rows.length, ["сотрудник", "сотрудника", "сотрудников"])}</span>
    </div>
    {rows.length ? <>
      <div className="tv-columns"><span>Сотрудник</span><AxisTicks axis={axis} className="tv-axis" /></div>
      <TeamTimeline axis={axis} now={now} className="tv-timeline">
        <div ref={people} className="tv-people" data-testid="tv-people" style={{ gridTemplateRows: shownGroups.flatMap((group) => ["20px", `repeat(${group.rows.length}, minmax(0, 1fr))`]).join(" ") }}>
          {shownGroups.map((group) => <Fragment key={group.department}>
            <h3 className="tv-department" data-department={group.department}>{group.label}</h3>
            {group.rows.map((row) => <Person key={row.employee.id} row={row} axis={axis} />)}
          </Fragment>)}
        </div>
      </TeamTimeline>
      <div className="tv-team-foot"><span><i />Линия на шкале — сейчас</span><span>{pages > 1 ? "Страницы меняются каждые 15 с" : "Все сотрудники на экране"}</span></div>
    </> : <div className="tv-empty-team"><h2>Команда пока не добавлена</h2><p>Сотрудники появятся здесь после настройки справочника.</p></div>}
  </section>;
}

function capacity() {
  return Math.max(1, Math.floor((window.innerHeight - 230) / (window.innerWidth < 750 ? 96 : 40)));
}


function Upcoming({ rows, now }: { rows: TodayRow[]; now: number }) {
  const list = useRef<HTMLOListElement>(null);
  const [limit, setLimit] = useState(3);
  const events = upcomingEvents(rows, now);
  useEffect(() => {
    const element = list.current;
    if (!element) return;
    const observer = new ResizeObserver(() => {
      // Строка 48 px и промежуток 8 px; используем только свободную высоту справа.
      setLimit(Math.max(0, Math.min(6, Math.floor((element.clientHeight + 8) / 56))));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [events.length]);
  return <section className="tv-upcoming" aria-label="Дальше по расписанию">
    <h2><Clock3 aria-hidden />Дальше по расписанию</h2>
    {events.length ? <ol ref={list} className="tv-events">
      {events.slice(0, limit).map((event) => <li key={`${event.row.employee.id}-${event.kind}`}>
        <time>{tvClock(event.time)}</time>
        <div>
          <strong>{event.row.employee.short_name}</strong>
          <span>{event.kind === "end" ? "Конец работы" : event.row.cell.status === "remote" ? "Начало удалённо" : "Начало в офисе"}</span>
        </div>
      </li>)}
    </ol> : <p className="tv-no-events">На сегодня больше нет начал и окончаний работы.</p>}
  </section>;
}

function Person({ row, axis }: { row: TodayRow; axis: Axis }) {
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
        <DayStrip cell={scheduleCell(row)} axis={axis} height={8} label={`Рабочее время по расписанию: ${row.employee.short_name}`} className={remote ? "tv-strip tv-strip-remote" : "tv-strip"} />
      </> : <p className="tv-person-day-label">{label}</p>}
    </div>
  </article>;
}
