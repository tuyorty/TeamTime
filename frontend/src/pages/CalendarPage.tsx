import { ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";

import { useCalendar, useEmployees, useMeta } from "@/api/queries";
import type { DayCell, Employee } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { DayDetailSheet, type DayRef } from "@/components/domain/DayDetail";
import { AxisTicks } from "@/components/domain/DayStrip";
import { ErrorState } from "@/components/domain/feedback";
import { STATUS } from "@/components/domain/states";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { employeeColor } from "@/lib/colors";
import { MONTHS, WEEKDAYS_SHORT, clock, dayMonth, isoDate, parseDate, weekday } from "@/lib/format";
import { useTheme } from "@/lib/theme";

const SLOT = 15 * 60;
const AXIS = { start: 7 * 3600, end: 23 * 3600 };

/** Интервалы человека в день: факт, если есть дейлик, иначе план (пунктиром). */
function presence(c: DayCell): { intervals: [number, number][]; planned: boolean } {
  if (c.status && c.status !== "remote" && !c.fact) return { intervals: [], planned: false };
  if (c.fact) return { intervals: c.fact.intervals as [number, number][], planned: false };
  if (c.plan?.kind === "work") return { intervals: c.plan.intervals as [number, number][], planned: true };
  return { intervals: [], planned: false };
}

export default function CalendarPage() {
  const today = useMeta().data?.today;
  const t = today ? parseDate(today) : new Date();
  const [cursor, setCursor] = useState({ y: t.getFullYear(), m: t.getMonth() });
  const first = new Date(cursor.y, cursor.m, 1);
  const last = new Date(cursor.y, cursor.m + 1, 0);
  const { data, error, refetch } = useCalendar(isoDate(first), isoDate(last));
  const employees = useEmployees().data ?? [];
  const [day, setDay] = useState<string | null>(null);
  const [selected, setSelected] = useState<DayRef | null>(null);
  const activeDay = day && data && Object.values(data)[0]?.some((c) => c.date === day) ? day : (today && today >= isoDate(first) && today <= isoDate(last) ? today : isoDate(first));

  const shift = (d: number) => {
    const n = new Date(cursor.y, cursor.m + d, 1);
    setCursor({ y: n.getFullYear(), m: n.getMonth() });
    setDay(null);
  };

  return (
    <div className="grid gap-5">
      <PageHeader
        title="Календарь команды"
        subtitle="Кто когда работает, кто на месте одновременно, отпуска и больничные"
        actions={
          <div className="flex items-center">
            <Button variant="ghost" size="icon" aria-label="Предыдущий месяц" onClick={() => shift(-1)}>
              <ChevronLeft />
            </Button>
            <span className="w-36 text-center font-display text-[15px] font-semibold">
              {MONTHS[cursor.m]} {cursor.y}
            </span>
            <Button variant="ghost" size="icon" aria-label="Следующий месяц" onClick={() => shift(1)}>
              <ChevronRight />
            </Button>
          </div>
        }
      />
      {error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : !data ? (
        <Skeleton className="h-[32rem]" />
      ) : (
        <>
          <MonthGrid data={data} employees={employees} first={first} today={today ?? ""} active={activeDay} onPick={setDay} />
          <Overlap data={data} employees={employees} day={activeDay} onOpen={setSelected} />
        </>
      )}
      <DayDetailSheet value={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function MonthGrid({
  data, employees, first, today, active, onPick,
}: {
  data: Record<string, DayCell[]>;
  employees: Employee[];
  first: Date;
  today: string;
  active: string;
  onPick: (d: string) => void;
}) {
  const byId = new Map(employees.map((e) => [String(e.id), e]));
  const days = Object.values(data)[0]?.map((c) => c.date) ?? [];
  const lead = (first.getDay() + 6) % 7;
  return (
    <Panel title="Месяц" description="Число — сколько человек работало (по дейликам) или работает по плану; ниже — отсутствия" bodyClassName="px-2 pb-2 sm:px-4 sm:pb-4">
      <div className="grid grid-cols-7 gap-px overflow-hidden rounded-md border border-line bg-line">
        {WEEKDAYS_SHORT.map((d) => (
          <div key={d} className="bg-surface-2 px-2 py-1 text-[12px] text-ink-3">
            {d}
          </div>
        ))}
        {Array.from({ length: lead }, (_, i) => (
          <div key={`e${i}`} className="bg-bg" />
        ))}
        {days.map((d, i) => {
          const cells = Object.entries(data).map(([id, cs]) => ({ e: byId.get(id), c: cs[i]! }));
          const working = cells.filter((x) => presence(x.c).intervals.length).length;
          const absent = cells.filter((x) => x.c.status && x.c.status !== "remote" && x.c.status !== "off");
          const isPast = d < today;
          return (
            <button
              key={d}
              type="button"
              onClick={() => onPick(d)}
              aria-pressed={d === active}
              className={cn(
                "flex min-h-24 flex-col gap-1 bg-surface p-1.5 text-left transition-colors hover:bg-surface-2/70",
                d === active && "ring-2 ring-inset ring-accent",
              )}
            >
              <span className="flex items-baseline justify-between">
                <span className={cn("text-[13px] font-semibold tnum", d === today && "text-accent-ink", weekday(d) >= 5 && "text-ink-2")}>
                  {parseDate(d).getDate()}
                </span>
                {working ? (
                  <span className={cn("text-[11px] tnum", isPast ? "text-ink-2" : "text-ink-3")} title={isPast ? "работали по дейликам" : "работают по плану"}>
                    {working} чел.{isPast ? "" : " в плане"}
                  </span>
                ) : null}
              </span>
              <span className="flex flex-wrap gap-0.5">
                {absent.slice(0, 4).map(({ e, c }) => {
                  if (!e || !c.status) return null;
                  const S = STATUS[c.status];
                  return (
                    <span key={e.id} className="inline-flex max-w-full items-center gap-0.5 truncate rounded-sm bg-absence-soft px-1 text-[11px] text-absence-ink [&_svg]:size-3">
                      <S.icon /> {e.short_name.split(" ")[0]}
                    </span>
                  );
                })}
                {absent.length > 4 ? <span className="text-[11px] text-ink-3">+{absent.length - 4}</span> : null}
              </span>
            </button>
          );
        })}
      </div>
    </Panel>
  );
}

function Overlap({
  data, employees, day, onOpen,
}: {
  data: Record<string, DayCell[]>;
  employees: Employee[];
  day: string;
  onOpen: (r: DayRef) => void;
}) {
  const { isDark } = useTheme();
  const rows = useMemo(
    () =>
      employees
        .map((e) => ({ e, c: data[String(e.id)]?.find((c) => c.date === day) }))
        .filter((r): r is { e: Employee; c: DayCell } => !!r.c),
    [data, employees, day],
  );
  const slots = useMemo(() => {
    const out: { t: number; names: string[] }[] = [];
    for (let t = AXIS.start; t < AXIS.end; t += SLOT) {
      const names = rows
        .filter(({ c }) => presence(c).intervals.some(([a, b]) => a <= t && t < (b < a ? b + 86400 : b)))
        .map(({ e }) => e.short_name);
      out.push({ t, names });
    }
    return out;
  }, [rows]);
  const peak = Math.max(1, ...slots.map((s) => s.names.length));
  const best = slots.reduce((a, s) => (s.names.length > a.names.length ? s : a), slots[0]!);
  const x = (s: number) => `${((s - AXIS.start) / (AXIS.end - AXIS.start)) * 100}%`;

  return (
    <Panel
      title={`Кто на месте одновременно: ${WEEKDAYS_SHORT[weekday(day)]}, ${dayMonth(day)}`}
      description={best.names.length ? `Больше всего людей — ${best.names.length} — с ${clock(best.t)}. Сплошные полосы — по дейликам, пунктир — по плану` : "В этот день ни плана, ни факта"}
    >
      <div className="grid grid-cols-[minmax(7rem,11rem)_1fr] gap-x-3 gap-y-1.5 max-sm:grid-cols-[6rem_1fr]">
        <span />
        <AxisTicks axis={AXIS} />
        <span className="self-end text-[12px] text-ink-3">одновременно</span>
        <div className="flex h-12 items-end gap-px" role="img" aria-label={`Пик присутствия: ${best.names.length} человек с ${clock(best.t)}`}>
          {slots.map((s) => (
            <Tooltip key={s.t} content={s.names.length ? `${clock(s.t)}: ${s.names.join(", ")}` : `${clock(s.t)}: никого`}>
              <div
                className="flex-1 rounded-t-[2px] bg-accent"
                style={{ height: `${(s.names.length / peak) * 100}%`, opacity: s.names.length ? 0.35 + 0.65 * (s.names.length / peak) : 0 }}
              />
            </Tooltip>
          ))}
        </div>
        {rows.map(({ e, c }) => {
          const p = presence(c);
          const color = employeeColor(e.color, e.id, isDark);
          return (
            <div key={e.id} className="contents">
              <button type="button" onClick={() => onOpen({ employee: e, cell: c })} className="flex min-w-0 items-center gap-2 text-left text-[13px] hover:underline">
                <Avatar employee={e} size={20} />
                <span className="truncate">{e.short_name}</span>
              </button>
              <div className="relative h-5 rounded-[3px] bg-surface-2">
                {!p.intervals.length && c.status && c.status !== "remote" ? (
                  <span className="hatch-absence absolute inset-0 flex items-center px-2 text-[11px] text-absence-ink">{STATUS[c.status].label}</span>
                ) : null}
                {p.intervals.map(([a, b], i) => {
                  const end = b < a ? b + 86400 : b;
                  return (
                    <div
                      key={i}
                      className={cn("absolute inset-y-[3px] rounded-[3px]", p.planned && "border border-dashed")}
                      style={{
                        left: x(Math.max(a, AXIS.start)),
                        width: `calc(${x(Math.min(end, AXIS.end))} - ${x(Math.max(a, AXIS.start))})`,
                        background: p.planned ? "transparent" : color,
                        borderColor: color,
                      }}
                      title={`${clock(a)}–${clock(b)}`}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
