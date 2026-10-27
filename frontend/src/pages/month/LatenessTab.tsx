import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Fragment, useMemo, useState } from "react";
import {
  CartesianGrid, ComposedChart, LabelList, Line, ReferenceArea, ReferenceDot, ResponsiveContainer, Scatter,
  Tooltip, XAxis, YAxis,
} from "recharts";

import { api } from "@/api/client";
import type { Month, MonthRow } from "@/api/types";
import { TooltipBox } from "@/components/charts/ChartTooltip";
import { axisProps, chart } from "@/components/charts/theme";
import { Input } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import { useDebounced } from "@/hooks/useDebounced";
import { cn } from "@/lib/cn";
import { employeeColor } from "@/lib/colors";
import { WEEKDAYS_SHORT, clock, count, ddmm, hm, weekday } from "@/lib/format";
import { useTheme } from "@/lib/theme";

import { curve, penaltyHours } from "./penalty";
import { EmptyRows, PersonCell, SortTh, td } from "./shared";
import { sortRows, useSort } from "./sorting";

export function LatenessTab({ data, rows }: { data: Month; rows: MonthRow[] }) {
  return (
    <div className="grid gap-5">
      <LatenessTable rows={rows} />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <PenaltyChart data={data} />
        <Calculator data={data} />
      </div>
    </div>
  );
}

type LateKey = "name" | "count" | "sum" | "penalty" | "extra";
const LATE_GET: Record<LateKey, (r: MonthRow) => number | string> = {
  name: (r) => r.employee.short_name,
  count: (r) => r.summary.late_count,
  sum: (r) => r.summary.late_total_sec,
  penalty: (r) => r.summary.penalty_sec,
  extra: (r) => r.summary.penalty_sec - r.summary.late_total_sec,
};

function LatenessTable({ rows }: { rows: MonthRow[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const { sort, toggle } = useSort<LateKey>();
  const sorted = sortRows(rows, sort, LATE_GET);
  const col = { sort, onSort: toggle };
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full min-w-[640px] border-collapse">
        <caption className="sr-only">Опоздания за месяц</caption>
        <thead className="border-b border-line bg-surface-2/60 text-left">
          <tr>
            <SortTh label="Сотрудник" sortKey="name" align="left" {...col} />
            <SortTh label="Количество" sortKey="count" title="Дней с опозданием больше нуля" {...col} />
            <SortTh label="Сумма" sortKey="sum" title="Сумма опозданий за месяц" {...col} />
            <SortTh label="Штраф" sortKey="penalty" title="Опоздания(−): штраф по шкале" {...col} />
            <SortTh label="Надбавка шкалы" sortKey="extra" title="Насколько штраф больше суммы опозданий" {...col} />
          </tr>
        </thead>
        <tbody>
          {sorted.length ? null : <EmptyRows colSpan={5} />}
          {sorted.map((r) => {
            const s = r.summary;
            const expanded = open === r.employee.id;
            const extra = s.penalty_sec - s.late_total_sec;
            return (
              <Fragment key={r.employee.id}>
                <tr className="border-b border-line">
                  <th scope="row" className="px-3 py-2 text-left font-normal">
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        aria-expanded={expanded}
                        aria-label={`Дни с опозданием: ${r.employee.short_name}`}
                        disabled={!r.late_days.length}
                        onClick={() => setOpen(expanded ? null : r.employee.id)}
                        className="rounded p-0.5 text-ink-3 hover:bg-surface-2 disabled:invisible"
                      >
                        {expanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                      </button>
                      <PersonCell employee={r.employee} />
                    </div>
                  </th>
                  <td className={cn(td, "text-right")}>{s.late_count || "—"}</td>
                  <td className={cn(td, "text-right")}>{s.late_total_sec ? hm(s.late_total_sec) : "—"}</td>
                  <td className={cn(td, "text-right font-semibold", s.penalty_sec && "text-late-ink")}>
                    {s.penalty_sec ? hm(s.penalty_sec) : "—"}
                  </td>
                  <td className={cn(td, "text-right text-ink-2")}>{extra >= 60 ? `+${hm(extra)}` : "—"}</td>
                </tr>
                {expanded ? (
                  <tr className="border-b border-line bg-bg/60">
                    <td colSpan={5} className="px-3 py-2">
                      <LateDays row={r} />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function LateDays({ row }: { row: MonthRow }) {
  return (
    <ul className="grid gap-1.5 py-1 pl-8 sm:grid-cols-2 lg:grid-cols-3">
      {row.late_days.map((d) => (
        <li key={d.date} className="flex items-center gap-3 rounded-md border border-line bg-surface px-2.5 py-1.5 text-[13px] tnum">
          <span className="shrink-0 whitespace-nowrap text-ink-2">
            {WEEKDAYS_SHORT[weekday(d.date)]} {ddmm(d.date)}
          </span>
          <span className="min-w-0 truncate text-ink-3">
            план {clock(d.plan_start)}, пришёл {clock(d.fact_start)}
          </span>
          <span className="ml-auto font-medium text-late-ink">+{hm(d.late_sec)}</span>
        </li>
      ))}
    </ul>
  );
}

interface Point {
  x: number;
  y: number;
  name: string;
  /** Прямая подпись только у точек, которые не сливаются с соседями. */
  label: string;
  color: string;
}

function withSparseLabels(points: Omit<Point, "label">[], minGap: number): Point[] {
  const sorted = [...points].sort((a, b) => a.x - b.x);
  let last = -Infinity;
  return sorted.map((p, i) => {
    const next = sorted[i + 1];
    const free = p.x - last >= minGap && (!next || next.x - p.x >= minGap || i === sorted.length - 1);
    if (free) last = p.x;
    return { ...p, label: free ? p.name : "" };
  });
}

function PenaltyChart({ data }: { data: Month }) {
  const { isDark } = useTheme();
  const s = data.scale;
  const raw = data.rows
    .filter((r) => r.summary.late_total_sec > 0)
    .map((r) => ({
      x: r.summary.late_total_sec / 3600,
      y: r.summary.penalty_sec / 3600,
      name: r.employee.short_name.split(" ")[0]!,
      color: employeeColor(r.employee.color, r.employee.id, isDark),
    }));
  const maxX = Math.max(s.hard_limit_h + 3, Math.ceil(Math.max(0, ...raw.map((p) => p.x)) + 1));
  const points = withSparseLabels(raw, maxX * 0.07);
  const line = useMemo(() => curve(s, maxX), [s, maxX]);
  const maxY = Math.ceil(penaltyHours(maxX, s) / 10) * 10;

  return (
    <Panel
      title="Шкала штрафа"
      description={`До ${s.soft_limit_h} ч штраф равен опозданию, до ${s.hard_limit_h} ч растёт квадратично, дальше — по ${s.tail_slope} ч за час`}
    >
      {s.problems.length ? (
        <p className="mb-2 rounded-md bg-deviation-soft px-2.5 py-1.5 text-[12px] text-deviation-ink">{s.problems.join(". ")}</p>
      ) : null}
      <div className="h-72" role="img" aria-label="Кривая штрафа за опоздания и точки сотрудников">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart margin={{ top: 12, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid stroke={chart.line} />
            <ReferenceArea x1={0} x2={s.soft_limit_h} fill="var(--surface-2)" fillOpacity={0.6} ifOverflow="hidden" />
            <ReferenceArea x1={s.hard_limit_h} x2={maxX} fill="var(--late-soft)" fillOpacity={0.6} ifOverflow="hidden" />
            <XAxis
              type="number"
              dataKey="x"
              domain={[0, maxX]}
              ticks={Array.from({ length: Math.floor(maxX / 2) + 1 }, (_, i) => i * 2)}
              {...axisProps}
              label={{ value: "сумма опозданий за месяц, ч", position: "insideBottom", offset: -4, fill: "var(--ink-3)", fontSize: 11 }}
              height={36}
            />
            <YAxis
              type="number"
              dataKey="y"
              domain={[0, maxY]}
              ticks={Array.from({ length: maxY / 10 + 1 }, (_, i) => i * 10)}
              {...axisProps}
              width={36}
            />
            <Tooltip
              isAnimationActive={false}
              cursor={false}
              content={({ active, payload }) => {
                const p = payload?.[0]?.payload as Point | { x: number; y: number } | undefined;
                if (!active || !p) return null;
                return (
                  <TooltipBox
                    title={"name" in p ? p.name : "Шкала"}
                    rows={[
                      { label: "Опоздания", value: hm(p.x * 3600) },
                      { label: "Штраф", value: hm(p.y * 3600) },
                    ]}
                  />
                );
              }}
            />
            <Line data={line} dataKey="y" stroke={chart.ink2} strokeWidth={2} dot={false} activeDot={false} isAnimationActive={false} type="linear" />
            <Scatter
              data={points}
              isAnimationActive={false}
              shape={(props: { cx?: number; cy?: number; payload?: Point }) => (
                <circle cx={props.cx} cy={props.cy} r={6} fill={props.payload?.color} stroke="var(--surface)" strokeWidth={2} />
              )}
            >
              <LabelList dataKey="label" position="top" offset={10} fill="var(--ink)" fontSize={11} />
            </Scatter>
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-ink-2" aria-label="Сотрудники на шкале">
        {[...points].sort((a, b) => b.x - a.x).map((p) => (
          <li key={p.name} className="flex items-center gap-1.5 tnum">
            <span className="size-2.5 rounded-full" style={{ background: p.color }} />
            <span className="text-ink">{p.name}</span> {hm(p.x * 3600)} → {hm(p.y * 3600)}
          </li>
        ))}
      </ul>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 border-t border-line pt-2 text-[12px] text-ink-3">
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-sm bg-surface-2" />штраф = опоздание</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-sm border border-line" />квадратичный рост</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-sm bg-late-soft" />{s.tail_slope} ч штрафа за каждый час</span>
      </div>
    </Panel>
  );
}

function parseHm(text: string): number | null {
  const m = /^\s*(\d{1,3})(?::(\d{1,2}))?\s*$/.exec(text);
  if (!m) return null;
  const minutes = Number(m[2] ?? 0);
  if (minutes > 59) return null;
  return Number(m[1]) * 60 + minutes;
}

function Calculator({ data }: { data: Month }) {
  const [minutes, setMinutes] = useState(6 * 60 + 45);
  const [text, setText] = useState("6:45");
  const debounced = useDebounced(minutes, 150);
  const { data: result } = useQuery({
    queryKey: ["penalty", debounced],
    queryFn: () => api.get<{ late_sec: number; penalty_sec: number }>(`/penalty?late_minutes=${debounced}`),
    placeholderData: (prev) => prev,
  });
  const extra = result ? result.penalty_sec - result.late_sec : 0;
  const s = data.scale;
  const zone = minutes / 60 <= s.soft_limit_h ? "linear" : minutes / 60 <= s.hard_limit_h ? "quad" : "steep";
  // Точку считаем на месте той же формулой, что и кривая: ответ сервера приходит с задержкой,
  // и пока ползунок двигается, точка шла бы мимо кривой.
  const point = { x: minutes / 60, y: penaltyHours(minutes / 60, s) };

  return (
    <Panel title="Сколько штрафа за N часов" description="Калькулятор считает на сервере тем же кодом, что и таблица">
      <div className="grid gap-4">
        <label className="grid gap-1.5 text-[13px] font-medium">
          Сумма опозданий за месяц
          <div className="flex items-center gap-3">
            <Input
              className="w-24 text-[15px]"
              value={text}
              aria-describedby="calc-hint"
              onChange={(e) => {
                setText(e.target.value);
                const v = parseHm(e.target.value);
                if (v !== null) setMinutes(Math.min(v, 100 * 60));
              }}
            />
            <input
              type="range"
              min={0}
              max={18 * 60}
              step={5}
              value={Math.min(minutes, 18 * 60)}
              aria-label="Сумма опозданий, минуты"
              onChange={(e) => {
                const v = Number(e.target.value);
                setMinutes(v);
                setText(hm(v * 60));
              }}
              className="flex-1 accent-[var(--accent)]"
            />
          </div>
          <span id="calc-hint" className="text-[12px] font-normal text-ink-3">Формат Ч:ММ, например 5:20</span>
        </label>
        <div className="rounded-lg bg-bg p-4">
          <div className="text-[12px] text-ink-2">Штраф, Опоздания(−)</div>
          <div role="status" aria-label="Рассчитанный штраф" className="font-display text-[40px] font-semibold leading-tight text-late-ink tnum">
            {result ? hm(result.penalty_sec) : "…"}
          </div>
          <div className="text-[13px] text-ink-2">
            {extra >= 60 ? <>на {hm(extra)} больше самих опозданий</> : "равен сумме опозданий"}
          </div>
        </div>
        <p className="text-[12px] leading-5 text-ink-3">
          {zone === "linear"
            ? `До ${s.soft_limit_h} часов шкала мягкая: каждая минута опоздания — минута штрафа.`
            : zone === "quad"
              ? `Между ${s.soft_limit_h} и ${s.hard_limit_h} часами каждая следующая минута дороже предыдущей.`
              : `После ${s.hard_limit_h} часов каждый час опозданий — ${count(s.tail_slope, ["час", "часа", "часов"])} штрафа.`}
        </p>
        <MiniCurve data={data} point={point} />
      </div>
    </Panel>
  );
}

function MiniCurve({ data, point }: { data: Month; point: { x: number; y: number } }) {
  const s = data.scale;
  const maxX = Math.max(s.hard_limit_h + 4, Math.ceil(point.x) + 1);
  const line = useMemo(() => curve(s, maxX, 0.5), [s, maxX]);
  return (
    <div className="h-28" aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart margin={{ top: 6, right: 6, bottom: 0, left: -24 }}>
          <XAxis type="number" dataKey="x" domain={[0, maxX]} {...axisProps} tick={false} height={4} />
          <YAxis type="number" dataKey="y" domain={[0, "auto"]} {...axisProps} tick={false} />
          <Line data={line} dataKey="y" stroke={chart.ink3} strokeWidth={1.5} dot={false} isAnimationActive={false} />
          <ReferenceDot x={point.x} y={point.y} r={6} fill="var(--late)" stroke="var(--surface)" strokeWidth={2} ifOverflow="extendDomain" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
