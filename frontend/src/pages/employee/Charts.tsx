import { useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import type { EmployeeDetail } from "@/api/types";
import { TooltipBox } from "@/components/charts/ChartTooltip";
import { planFactShape } from "@/components/charts/PlanFactBar";
import { axisProps, chart } from "@/components/charts/theme";
import { Panel } from "@/components/ui/panel";
import { Segmented } from "@/components/ui/segmented";
import { WEEKDAYS_SHORT, ddmm, hm, weekday } from "@/lib/format";

const H = 3600;

const daysShape = planFactShape({ outlineKey: "plan", fillKey: "fact", outlineColor: chart.ink3, fillColor: chart.accent, fillRatio: 0.6 });
const weeksShape = planFactShape({
  outlineKey: "fact",
  fillKey: "result",
  outlineColor: chart.accent,
  fillColor: chart.accent,
  fillRatio: 0.6,
  radius: 4,
});

/** Часы: план контуром, факт заливкой — та же грамматика, что у полосы дня. */
export function HoursChart({ data }: { data: EmployeeDetail }) {
  const [mode, setMode] = useState<"days" | "weeks">("days");
  const days = useMemo(
    () =>
      data.days
        .filter((d) => d.fact || d.plan?.kind === "work")
        .map((d) => ({
          key: d.date,
          label: ddmm(d.date),
          plan: (d.plan?.planned_sec ?? 0) / H,
          fact: (d.fact?.worked_sec ?? 0) / H,
          result: (d.fact?.result_sec ?? 0) / H,
          missing: d.state === "missing",
        }))
        .map((r) => ({ ...r, outer: Math.max(r.plan, r.fact) })),
    [data.days],
  );
  const weeks = data.weeks.map((w) => ({
    key: `${w.iso_week}`,
    label: `${w.iso_week} нед.`,
    plan: 0,
    fact: w.worked_sec / H,
    result: w.result_sec / H,
    missing: false,
    outer: w.worked_sec / H,
  }));
  const rows = mode === "days" ? days : weeks;
  return (
    <Panel
      title="Часы"
      description={mode === "days" ? "План (контур) и факт (заливка) по дням" : "Часы(+) по неделям, внутри — Часы(e%)"}
      actions={
        <Segmented
          label="Группировка"
          value={mode}
          onChange={setMode}
          options={[
            { value: "days", label: "По дням" },
            { value: "weeks", label: "По неделям" },
          ]}
        />
      }
    >
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} barCategoryGap={mode === "days" ? "18%" : "35%"}>
            <CartesianGrid vertical={false} stroke={chart.line} />
            <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" minTickGap={18} />
            <YAxis {...axisProps} width={28} />
            <Tooltip
              isAnimationActive={false}
              cursor={{ fill: "var(--surface-2)" }}
              content={({ active, payload }) => {
                const p = payload?.[0]?.payload as (typeof rows)[number] | undefined;
                if (!active || !p) return null;
                return (
                  <TooltipBox
                    title={p.label}
                    rows={[
                      ...(mode === "days" ? [{ label: "План", value: hm(p.plan * H) }] : []),
                      { label: "Часы", value: p.missing ? "нет дейлика" : hm(p.fact * H), color: chart.accent },
                      { label: "Итог (e%)", value: hm(p.result * H) },
                    ]}
                  />
                );
              }}
            />
            <Bar
              key={mode}
              dataKey="outer"
              shape={mode === "days" ? daysShape : weeksShape}
              activeBar={mode === "days" ? daysShape : weeksShape}
              maxBarSize={mode === "days" ? 16 : 40}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

export function EfficiencyChart({ data }: { data: EmployeeDetail }) {
  const rows = data.days
    .filter((d) => d.fact?.efficiency !== null && d.fact?.efficiency !== undefined)
    .map((d) => ({ label: ddmm(d.date), date: d.date, e: d.fact!.efficiency! }));
  const avg = rows.length ? Math.round(rows.reduce((s, r) => s + r.e, 0) / rows.length) : null;
  return (
    <Panel title="Эффективность" description={avg !== null ? `Как указано в дейликах, в среднем ${avg}%` : "Нет дейликов с эффективностью"}>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 8 }}>
            <CartesianGrid vertical={false} stroke={chart.line} />
            <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" minTickGap={18} />
            <YAxis {...axisProps} width={40} domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickFormatter={(v: number) => `${v}%`} />
            {avg !== null ? <ReferenceLine y={avg} stroke={chart.ink3} strokeDasharray="4 4" /> : null}
            <Tooltip
              isAnimationActive={false}
              content={({ active, payload }) => {
                const p = payload?.[0]?.payload as (typeof rows)[number] | undefined;
                if (!active || !p) return null;
                return (
                  <TooltipBox
                    title={`${WEEKDAYS_SHORT[weekday(p.date)]}, ${p.label}`}
                    rows={[{ label: "Эффективность", value: `${p.e}%`, color: chart.accent }]}
                  />
                );
              }}
            />
            <Line dataKey="e" stroke={chart.accent} strokeWidth={2} dot={{ r: 3, fill: chart.accent, strokeWidth: 0 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-[12px] text-ink-3">e% — это данные из дейлика, а не оценка: система не ранжирует людей.</p>
    </Panel>
  );
}

const PUNCT = [
  { label: "раньше 15+", min: -Infinity, max: -15, late: false },
  { label: "раньше", min: -15, max: 0, late: false },
  { label: "вовремя", min: 0, max: 1, late: false },
  { label: "1–15 мин", min: 1, max: 16, late: true },
  { label: "15–30", min: 16, max: 31, late: true },
  { label: "30–60", min: 31, max: 61, late: true },
  { label: "1 ч+", min: 61, max: Infinity, late: true },
];

/** Пунктуальность: распределение «приход минус плановое начало», минуты. */
export function Punctuality({ data }: { data: EmployeeDetail }) {
  const counts = PUNCT.map((b) => ({
    ...b,
    n: data.late_minutes.filter((m) => m >= b.min && m < b.max).length,
  }));
  const onTime = counts.filter((c) => !c.late).reduce((s, c) => s + c.n, 0);
  const total = data.late_minutes.length;
  return (
    <Panel
      title="Пунктуальность"
      description={total ? `Вовремя или раньше: ${onTime} из ${total} дней с планом и дейликом` : "Нет дней с планом и дейликом"}
    >
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={counts} barCategoryGap="22%">
            <CartesianGrid vertical={false} stroke={chart.line} />
            <XAxis dataKey="label" {...axisProps} interval={0} fontSize={10} />
            <YAxis {...axisProps} width={24} allowDecimals={false} />
            <Tooltip
              isAnimationActive={false}
              cursor={{ fill: "var(--surface-2)" }}
              content={({ active, payload }) => {
                const p = payload?.[0]?.payload as (typeof counts)[number] | undefined;
                if (!active || !p) return null;
                return <TooltipBox title={p.label} rows={[{ label: "Дней", value: p.n, color: p.late ? chart.late : chart.ink3 }]} />;
              }}
            />
            <Bar dataKey="n" radius={[3, 3, 0, 0]} isAnimationActive={false}>
              {counts.map((c) => (
                <Cell key={c.label} fill={c.late ? chart.late : chart.ink3} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {data.avg_start_sec !== null && data.avg_start_sec !== undefined ? (
        <p className="mt-1 text-[12px] text-ink-3">
          Средний приход — <span className="text-ink-2 tnum">{hm(data.avg_start_sec)}</span>
        </p>
      ) : null}
    </Panel>
  );
}
