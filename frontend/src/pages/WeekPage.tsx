import { ChevronLeft, ChevronRight, Download, Filter, Rows2, Rows3, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { exportUrl } from "@/api/client";
import { useMeta, useWeek } from "@/api/queries";
import type { DayCell, EmployeeBrief, Week, WeekRow } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { DayDetailSheet } from "@/components/domain/DayDetail";
import { AxisTicks, DayStrip } from "@/components/domain/DayStrip";
import { axisFor, type Axis } from "@/lib/axis";
import { ErrorState, TruncationNote } from "@/components/domain/feedback";
import { DEVIATION, STATUS } from "@/components/domain/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dropdown, DropdownContent, DropdownItem, DropdownTrigger } from "@/components/ui/dropdown";
import { Input } from "@/components/ui/field";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { WEEKDAYS_SHORT, count, dayMonthShort, hm, isoWeek, parseDate, rangeShort, shiftWeek, span } from "@/lib/format";
import { hasDeviation } from "@/lib/cells";
import { useFlashed } from "@/lib/realtime";

import { WeekPulse } from "./week/WeekPulse";

type Density = "compact" | "detailed";
type FilterKind = "all" | "deviations" | "missing";

function useDensity(): [Density, (d: Density) => void] {
  const [d, setD] = useState<Density>(() => {
    try {
      return (localStorage.getItem("tt-density") as Density) || "detailed";
    } catch {
      return "detailed";
    }
  });
  return [
    d,
    (next) => {
      setD(next);
      try {
        localStorage.setItem("tt-density", next);
      } catch {
        /* ничего */
      }
    },
  ];
}

export default function WeekPage() {
  const params = useParams();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const meta = useMeta().data;
  const fallback = isoWeek(meta ? parseDate(meta.today) : new Date());
  const year = Number(params.year ?? fallback.year);
  const week = Number(params.week ?? fallback.week);
  const { data, error, refetch, isPlaceholderData } = useWeek(year, week);
  const [density, setDensity] = useDensity();
  const [filter, setFilter] = useState<FilterKind>("all");
  const [query, setQuery] = useState("");
  const selDay = search.get("day");
  const selEmployee = Number(search.get("e") ?? 0);

  const go = (delta: number) => {
    const t = shiftWeek(year, week, delta);
    navigate(`/week/${t.year}/${t.week}`);
  };
  const open = (employeeId: number, day: string) => setSearch({ day, e: String(employeeId) });
  const close = () => setSearch({});

  const rows = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    return data.rows.filter((r) => {
      if (q && !`${r.employee.full_name} ${r.employee.short_name} ${r.employee.position}`.toLowerCase().includes(q)) return false;
      if (filter === "deviations") return r.cells.some(hasDeviation);
      if (filter === "missing") return r.cells.some((c) => c.state === "missing");
      return true;
    });
  }, [data, filter, query]);
  // Фильтр оставляет людей, у кого за неделю есть нужные дни, а остальные дни приглушает:
  // иначе при опозданиях почти у всех таблица выглядела бы так же, как без фильтра.
  const dim = useMemo<((c: DayCell) => boolean) | undefined>(() => {
    if (filter === "deviations") return (c) => !hasDeviation(c);
    if (filter === "missing") return (c) => c.state !== "missing";
    return undefined;
  }, [filter]);

  const axis = useMemo(() => axisFor(data?.rows.flatMap((r) => r.cells) ?? []), [data]);
  const selectedRef = useMemo(() => {
    if (!data || !selDay || !selEmployee) return null;
    const row = data.rows.find((r) => r.employee.id === selEmployee);
    const cell = row?.cells.find((c) => c.date === selDay);
    return row && cell ? { employee: row.employee, cell } : null;
  }, [data, selDay, selEmployee]);

  const isCurrent = data && fallback.year === year && fallback.week === week;

  return (
    <div className="grid gap-5">
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="flex items-end gap-4">
          <h1 className="flex items-baseline gap-2 font-display" aria-label={`${week} неделя`}>
            <span className="text-[44px] font-semibold leading-[0.9] tracking-tight tnum">{week}</span>
            <span className="text-[20px] font-medium text-ink-2">неделя</span>
          </h1>
          <div className="pb-0.5 text-[13px] text-ink-2">
            {data ? rangeShort(data.days[0]!, data.days[6]!) : " "}
            <span className="text-ink-3">, {year}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center">
            <Button variant="ghost" size="icon" aria-label="Предыдущая неделя" onClick={() => go(-1)}>
              <ChevronLeft />
            </Button>
            <Button variant="secondary" size="sm" disabled={!!isCurrent} onClick={() => navigate("/week")}>
              Текущая
            </Button>
            <Button variant="ghost" size="icon" aria-label="Следующая неделя" onClick={() => go(1)}>
              <ChevronRight />
            </Button>
          </div>
          <Segmented
            label="Плотность"
            value={density}
            onChange={setDensity}
            className="hidden md:inline-flex"
            options={[
              { value: "compact", label: <><Rows3 /> Компактно</> },
              { value: "detailed", label: <><Rows2 /> Подробно</> },
            ]}
          />
          <Dropdown>
            <DropdownTrigger asChild>
              <Button size="sm">
                <Download /> Экспорт
              </Button>
            </DropdownTrigger>
            <DropdownContent>
              <DropdownItem asChild>
                <a href={exportUrl(`/weeks/${year}/${week}.xlsx`)} download>
                  Excel (XLSX), как в таблице
                </a>
              </DropdownItem>
              <DropdownItem asChild>
                <a href={exportUrl(`/weeks/${year}/${week}.csv`)} download>
                  CSV по дням
                </a>
              </DropdownItem>
            </DropdownContent>
          </Dropdown>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-2 size-4 text-ink-3" />
          <Input
            aria-label="Фильтр по имени"
            placeholder="Имя или должность"
            className="w-52 pl-8"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <Segmented
          label="Показать"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: "Все" },
            { value: "deviations", label: <><Filter /> С отклонениями</> },
            { value: "missing", label: "Без дейлика" },
          ]}
        />
        {data && (filter !== "all" || query.trim()) ? (
          <span className="text-[12px] text-ink-3 tnum">
            {count(rows.length, ["сотрудник", "сотрудника", "сотрудников"])} из {data.rows.length}
            {filter !== "all" ? ", остальные дни приглушены" : ""}
          </span>
        ) : null}
        <Legend />
      </div>

      {error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : !data ? (
        <WeekSkeleton />
      ) : (
        <div className={cn("transition-opacity", isPlaceholderData && "opacity-60")}>
          <div className="hidden md:block">
            <WeekTable data={data} rows={rows} axis={axis} density={density} dim={dim} onOpen={open} />
          </div>
          <div className="md:hidden">
            <WeekMobile data={data} rows={rows} axis={axis} dim={dim} onOpen={open} />
          </div>
          <div className="mt-2 flex flex-wrap justify-between gap-2">
            <TruncationNote />
            <p className="text-[12px] text-ink-3">
              Нажмите на день, чтобы увидеть задачи и исходное сообщение.
            </p>
          </div>
        </div>
      )}

      {data ? <WeekPulse data={data} /> : null}
      <DayDetailSheet value={selectedRef} onClose={close} />
    </div>
  );
}

function Legend() {
  return (
    <div className="ml-auto hidden flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-ink-2 xl:flex" aria-label="Легенда">
      <span className="flex items-center gap-1.5">
        <span className="h-2.5 w-5 rounded-[2px] border border-ink-3/70" /> план
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-2.5 w-5 rounded-[2px] bg-accent" /> факт
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-2.5 w-2 rounded-[2px] bg-late" /> опоздание
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-1 w-3 rounded-[2px] bg-deviation" /> ранний уход
      </span>
      <span className="flex items-center gap-1.5">
        <span className="hatch-absence h-2.5 w-5 rounded-[2px]" /> отсутствие
      </span>
    </div>
  );
}

function WeekSkeleton() {
  return (
    <div className="grid gap-px overflow-hidden rounded-lg border border-line bg-line">
      {Array.from({ length: 7 }, (_, i) => (
        <div key={i} className="grid grid-cols-[13rem_repeat(7,1fr)_6rem] gap-3 bg-surface p-3">
          <Skeleton className="h-8" />
          {Array.from({ length: 7 }, (_, j) => (
            <div key={j} className="grid gap-1.5">
              <Skeleton className="h-3.5" />
              <Skeleton className="h-3 w-2/3" />
            </div>
          ))}
          <Skeleton className="h-8" />
        </div>
      ))}
    </div>
  );
}

function EmployeeCell({ employee, row, planHref }: { employee: EmployeeBrief; row: WeekRow; planHref: string }) {
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <Avatar employee={employee} size={28} />
      <div className="min-w-0">
        <Link to={`/people/${employee.id}`} className="block truncate text-[13px] font-medium hover:underline">
          {employee.short_name}
        </Link>
        <div className="flex items-center gap-1.5 truncate text-[12px] text-ink-3">
          {employee.position}
          {row.plan && row.plan.versions > 1 ? (
            <Tooltip content={`План менялся: версия ${row.plan.version} из ${row.plan.versions}`}>
              <Link to={planHref} className="shrink-0" aria-label={`План, версия ${row.plan.version}`}>
                <Badge tone="outline">v{row.plan.version}</Badge>
              </Link>
            </Tooltip>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function CellBody({ cell, density }: { cell: DayCell; density: Density }) {
  const f = cell.fact;
  if (!f) {
    if (cell.status && cell.status !== "remote") {
      const S = STATUS[cell.status];
      return (
        <span className="flex items-center gap-1 text-[12px] text-absence-ink [&_svg]:size-3.5">
          <S.icon /> {S.label}
        </span>
      );
    }
    if (cell.state === "missing") return <span className="text-[12px] text-ink-2">нет дейлика</span>;
    if (cell.state === "pending")
      return (
        <span className="text-[12px] whitespace-nowrap text-ink-3 tnum" aria-label="план">
          {cell.plan?.kind === "work" ? span(cell.plan.start, cell.plan.end) : "ждём"}
        </span>
      );
    if (cell.plan?.kind === "note")
      return (
        <span className={cn("block truncate text-[12px] italic text-ink-3", cell.plan.note_has_time && "text-deviation-ink")} title={cell.plan.note ?? ""}>
          {cell.plan.note}
        </span>
      );
    return <span className="text-[12px] text-ink-3">{cell.state === "off" ? "выходной" : ""}</span>;
  }
  return (
    <div className="grid gap-0.5 text-[12px] leading-4 tnum">
      {density === "detailed" ? (
        <span className="text-ink-2">{span(f.start, f.end)}</span>
      ) : null}
      <span className="block truncate">
        <span className="mr-1.5 text-[13px] font-semibold text-ink">{hm(f.worked_sec)}</span>
        {f.efficiency !== null && f.efficiency !== undefined ? (
          <span className="text-ink-3" title={`${f.efficiency}% = ${hm(f.result_sec)}`}>
            {f.efficiency}%{density === "detailed" ? <> = {hm(f.result_sec)}</> : null}
          </span>
        ) : (
          <span className="text-deviation-ink">e% ?</span>
        )}
      </span>
      {density === "detailed" ? (
        // Строка отклонений есть всегда (пустая — невидимая): высота строк не прыгает между неделями.
        <span
          className="block min-h-4 truncate [&>*]:mr-1"
          title={
            [
              cell.late_sec ? `опоздание ${hm(cell.late_sec)}` : "",
              cell.early_leave_sec ? `ранний уход ${hm(cell.early_leave_sec)}` : "",
              cell.status === "remote" ? "удалёнка" : "",
              cell.no_plan ? "без плана" : "",
            ]
              .filter(Boolean)
              .join(", ") || undefined
          }
        >
          {cell.late_sec ? (
            <span className="inline-flex items-center gap-0.5 font-medium text-late-ink">
              <DEVIATION.late.icon className="size-3" />+{hm(cell.late_sec)}
            </span>
          ) : null}
          {cell.early_leave_sec ? (
            <span className="inline-flex items-center gap-0.5 text-deviation-ink">
              <DEVIATION.early_leave.icon className="size-3" />−{hm(cell.early_leave_sec)}
            </span>
          ) : null}
          {cell.status === "remote" ? (
            <span className="inline-flex items-center gap-0.5 text-ink-3">
              <STATUS.remote.icon className="size-3" /> удалёнка
            </span>
          ) : null}
          {cell.no_plan ? <span className="text-ink-3">без плана</span> : null}
        </span>
      ) : null}
    </div>
  );
}

function DayCellButton({
  employeeId,
  cell,
  axis,
  density,
  today,
  dimmed = false,
  onOpen,
}: {
  employeeId: number;
  cell: DayCell;
  axis: Axis;
  density: Density;
  today: string;
  dimmed?: boolean;
  onOpen: (e: number, d: string) => void;
}) {
  const flashed = useFlashed(employeeId, cell.date);
  return (
    <td className={cn("border-l border-line p-0 align-top", cell.date === today && "bg-accent-soft/40", flashed && "flash")}>
      <button
        type="button"
        onClick={() => onOpen(employeeId, cell.date)}
        className={cn(
          "grid h-full w-full gap-1.5 px-2.5 text-left transition-colors hover:bg-surface-2/70 focus-visible:-outline-offset-2",
          density === "compact" ? "py-2" : "py-2.5",
          dimmed && "opacity-30 hover:opacity-100",
        )}
      >
        <DayStrip cell={cell} axis={axis} height={density === "compact" ? 10 : 14} />
        <CellBody cell={cell} density={density} />
      </button>
    </td>
  );
}

function WeekTable({
  data,
  rows,
  axis,
  density,
  dim,
  onOpen,
}: {
  data: Week;
  rows: WeekRow[];
  axis: Axis;
  density: Density;
  dim?: (c: DayCell) => boolean;
  onOpen: (e: number, d: string) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full min-w-[1000px] table-fixed border-collapse">
        <colgroup>
          <col className="w-[14rem]" />
          {data.days.map((d) => (
            <col key={d} />
          ))}
          <col className="w-[7.5rem]" />
        </colgroup>
        <caption className="sr-only">
          {data.label}: план и факт по сотрудникам и дням
        </caption>
        <thead className="sticky top-0 z-10">
          <tr className="border-b border-line bg-surface-2/60 text-left">
            <th scope="col" className="px-3 py-2 text-[12px] font-medium text-ink-3">
              {count(rows.length, ["сотрудник", "сотрудника", "сотрудников"])}
            </th>
            {data.days.map((d, i) => (
              <th
                key={d}
                scope="col"
                className={cn("border-l border-line px-2.5 pt-2 pb-1 font-normal", d === data.today && "bg-accent-soft/60")}
              >
                <div className="flex items-baseline gap-1.5 text-[13px]">
                  <span className={cn("font-semibold", i >= 5 ? "text-ink-2" : "text-ink")}>{WEEKDAYS_SHORT[i]}</span>
                  <span className="whitespace-nowrap text-ink-3 tnum">{dayMonthShort(d)}</span>
                  {d === data.today ? (
                    <span className="ml-auto size-1.5 shrink-0 self-center rounded-full bg-accent" title="Сегодня">
                      <span className="sr-only">сегодня</span>
                    </span>
                  ) : null}
                </div>
                <AxisTicks axis={axis} className="mt-1" />
              </th>
            ))}
            <th scope="col" className="border-l border-line px-3 py-2 text-right text-[12px] font-medium text-ink-3">
              Итого
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.employee.id} className="border-b border-line last:border-b-0">
              <th scope="row" className="px-3 py-2 text-left font-normal">
                <EmployeeCell employee={r.employee} row={r} planHref={`/plans/${data.iso_year}/${data.iso_week}`} />
              </th>
              {r.cells.map((c) => (
                <DayCellButton key={c.date} employeeId={r.employee.id} cell={c} axis={axis} density={density} today={data.today} dimmed={dim?.(c)} onOpen={onOpen} />
              ))}
              <td className="border-l border-line px-3 py-2.5 text-right align-top whitespace-nowrap tnum">
                <div className="text-[14px] font-semibold">{hm(r.totals.worked_sec)}</div>
                <div className="text-[12px] text-ink-2">итог {hm(r.totals.result_sec)}</div>
                {/* План и опоздания занимают место всегда, чтобы строки не меняли высоту между неделями. */}
                <div className="h-[18px] text-[12px] leading-[18px] text-ink-3">{r.totals.planned_sec ? `план ${hm(r.totals.planned_sec)}` : null}</div>
                <div className="h-[18px] text-[12px] leading-[18px] font-medium text-late-ink">
                  {r.totals.late_count ? (
                    <span className="inline-flex items-center gap-0.5 align-top">
                      <DEVIATION.late.icon className="size-3" />
                      {r.totals.late_count}, {hm(r.totals.late_sec)}
                    </span>
                  ) : null}
                </div>
              </td>
            </tr>
          ))}
          {!rows.length ? (
            <tr>
              <td colSpan={9} className="px-3 py-10 text-center text-[13px] text-ink-2">
                Никого не нашлось. Сбросьте фильтр.
              </td>
            </tr>
          ) : null}
        </tbody>
        <tfoot>
          <tr className="border-t border-line bg-surface-2/60 text-[12px] text-ink-2 tnum">
            <th scope="row" className="px-3 py-2 text-left align-top font-normal">
              <div className="font-medium text-ink">Команда</div>
              <div className="text-ink-3">часы, дейлики из плана</div>
            </th>
            {data.day_totals.map((t) => (
              <td key={t.date} className="border-l border-line px-2.5 py-2 align-top whitespace-nowrap">
                <div className="font-medium text-ink">{t.worked_sec ? hm(t.worked_sec) : "—"}</div>
                <div>
                  {t.worked_count} из {Math.max(t.planned_count, t.worked_count)}
                </div>
                {t.late_count ? (
                  <div className="inline-flex items-center gap-0.5 text-late-ink">
                    <DEVIATION.late.icon className="size-3" />
                    {t.late_count}
                  </div>
                ) : null}
              </td>
            ))}
            <td className="border-l border-line px-3 py-2 text-right align-top">
              <div className="font-semibold text-ink">{hm(data.totals.worked_sec)}</div>
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function WeekMobile({
  data,
  rows,
  axis,
  dim,
  onOpen,
}: {
  data: Week;
  rows: WeekRow[];
  axis: Axis;
  dim?: (c: DayCell) => boolean;
  onOpen: (e: number, d: string) => void;
}) {
  const initial = data.days.includes(data.today) ? data.days.indexOf(data.today) : 0;
  const [day, setDay] = useState(initial);
  const date = data.days[day]!;
  return (
    <div className="grid gap-3">
      <div className="grid grid-cols-7 gap-1" role="tablist" aria-label="День недели">
        {data.days.map((d, i) => (
          <button
            key={d}
            role="tab"
            aria-selected={i === day}
            onClick={() => setDay(i)}
            className={cn(
              "flex flex-col items-center rounded-md border border-transparent py-1.5 text-[12px] text-ink-2",
              i === day && "border-line bg-surface text-ink shadow-sm",
              d === data.today && "text-accent-ink",
            )}
          >
            <span className="font-semibold">{WEEKDAYS_SHORT[i]}</span>
            <span className="tnum">{parseDate(d).getDate()}</span>
          </button>
        ))}
      </div>
      <div className="overflow-hidden rounded-lg border border-line bg-surface">
        <div className="border-b border-line px-3 py-2">
          <AxisTicks axis={axis} />
        </div>
        <ul className="divide-y divide-line">
          {rows.map((r) => {
            const c = r.cells[day]!;
            return (
              <li key={r.employee.id}>
                <button
                  type="button"
                  onClick={() => onOpen(r.employee.id, date)}
                  className={cn("grid w-full gap-2 px-3 py-3 text-left", dim?.(c) && "opacity-30")}
                >
                  <div className="flex items-center gap-2">
                    <Avatar employee={r.employee} size={24} />
                    <span className="text-[14px] font-medium">{r.employee.short_name}</span>
                    {c.late_sec ? <Badge tone="late" className="ml-auto">+{hm(c.late_sec)}</Badge> : null}
                  </div>
                  <DayStrip cell={c} axis={axis} height={14} />
                  <CellBody cell={c} density="detailed" />
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
