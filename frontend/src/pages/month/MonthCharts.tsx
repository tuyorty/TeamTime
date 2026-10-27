import { AlarmClock, CircleDashed, Hourglass, LogOut } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { Month } from "@/api/types";
import { TooltipBox } from "@/components/charts/ChartTooltip";
import { planFactShape } from "@/components/charts/PlanFactBar";
import { axisProps, chart } from "@/components/charts/theme";
import { Avatar } from "@/components/domain/Avatar";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";
import { WEEKDAYS_SHORT, ddmm, hm, isoWeek, parseDate, weekday } from "@/lib/format";

const H = 3600;

export function MonthCharts({ data }: { data: Month }) {
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <WeeksChart data={data} />
      <HistoryChart data={data} />
      <LateDistribution data={data} />
      <TopDeviations data={data} />
    </div>
  );
}

function WeeksChart({ data }: { data: Month }) {
  const weeks = useMemo(() => {
    const by = new Map<number, { label: string; worked: number; result: number; late: number }>();
    for (const r of data.rows)
      for (const w of r.weeks) {
        const cur = by.get(w.iso_week) ?? { label: w.label, worked: 0, result: 0, late: 0 };
        cur.worked += w.worked_sec;
        cur.result += w.result_sec;
        cur.late += w.late_sec;
        by.set(w.iso_week, cur);
      }
    return [...by.entries()].map(([week, v]) => ({ week: `${week}`, ...v, hours: v.worked / H }));
  }, [data]);
  return (
    <Panel title="Динамика по неделям" description="Часы(+) команды в днях этого месяца, по ISO-неделям">
      <div className="h-52">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={weeks} barCategoryGap="35%">
            <CartesianGrid vertical={false} stroke={chart.line} />
            <XAxis dataKey="week" {...axisProps} tickFormatter={(w: string) => `${w} нед.`} />
            <YAxis {...axisProps} width={36} />
            <Tooltip
              isAnimationActive={false}
              cursor={{ fill: "var(--surface-2)" }}
              content={({ active, payload }) => {
                const p = payload?.[0]?.payload as (typeof weeks)[number] | undefined;
                if (!active || !p) return null;
                return (
                  <TooltipBox
                    title={p.label}
                    rows={[
                      { label: "Часы(+)", value: hm(p.worked), color: chart.accent },
                      { label: "Часы(e%)", value: hm(p.result) },
                      { label: "Опоздания", value: hm(p.late) },
                    ]}
                  />
                );
              }}
            />
            <Bar dataKey="hours" fill={chart.accent} radius={[4, 4, 0, 0]} maxBarSize={44} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

const historyShape = planFactShape({
  outlineKey: "norm",
  fillKey: "total",
  outlineColor: chart.ink3,
  fillColor: chart.accent,
  fillRatio: 0.6,
  radius: 4,
});

function HistoryChart({ data }: { data: Month }) {
  const rows = data.history.map((h) => {
    const total = Math.max(0, h.total_sec) / H;
    const norm = h.norm_sec / H;
    return { ...h, total, norm, outer: Math.max(total, norm) };
  });
  return (
    <Panel title="Сравнение месяцев" description="Итого команды (заливка) и сумма норм (контур)">
      <div className="h-52">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} barCategoryGap="30%">
            <CartesianGrid vertical={false} stroke={chart.line} />
            <XAxis dataKey="label" {...axisProps} />
            <YAxis {...axisProps} width={40} />
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
                      { label: "Итого", value: hm(p.total_sec), color: chart.accent },
                      { label: "Нормы", value: hm(p.norm_sec) },
                      { label: "Штрафы", value: hm(p.penalty_sec) },
                    ]}
                  />
                );
              }}
            />
            <Bar dataKey="outer" shape={historyShape} activeBar={historyShape} maxBarSize={44} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {rows.length < 2 ? <p className="mt-1 text-[12px] text-ink-3">Сравнение появится, когда накопится второй месяц.</p> : null}
    </Panel>
  );
}

const BUCKETS = [
  { label: "до 10 мин", max: 10 * 60 },
  { label: "10–30 мин", max: 30 * 60 },
  { label: "30–60 мин", max: 60 * 60 },
  { label: "1–2 ч", max: 2 * H },
  { label: "больше 2 ч", max: Infinity },
];

function LateDistribution({ data }: { data: Month }) {
  const counts = useMemo(() => {
    const out = BUCKETS.map((b) => ({ label: b.label, n: 0 }));
    for (const r of data.rows)
      for (const d of r.late_days) {
        const i = BUCKETS.findIndex((b) => d.late_sec <= b.max);
        out[i]!.n += 1;
      }
    return out;
  }, [data]);
  const total = counts.reduce((s, c) => s + c.n, 0);
  return (
    <Panel title="Распределение опозданий" description={`Сколько дней с опозданием каждой длины, всего ${total}`}>
      <div className="h-52">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={counts} barCategoryGap="30%">
            <CartesianGrid vertical={false} stroke={chart.line} />
            <XAxis dataKey="label" {...axisProps} interval={0} />
            <YAxis {...axisProps} width={28} allowDecimals={false} />
            <Tooltip
              isAnimationActive={false}
              cursor={{ fill: "var(--surface-2)" }}
              content={({ active, payload }) => {
                const p = payload?.[0]?.payload as (typeof counts)[number] | undefined;
                if (!active || !p) return null;
                return <TooltipBox title={p.label} rows={[{ label: "Дней", value: p.n, color: chart.late }]} />;
              }}
            />
            <Bar dataKey="n" fill={chart.late} radius={[4, 4, 0, 0]} maxBarSize={44} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

const DEV = {
  late: { label: "опоздание", icon: AlarmClock, tone: "late" as const },
  early_leave: { label: "ранний уход", icon: LogOut, tone: "deviation" as const },
  undertime: { label: "недоработка", icon: Hourglass, tone: "deviation" as const },
  missing_daily: { label: "нет дейлика", icon: CircleDashed, tone: "neutral" as const },
  no_plan: { label: "без плана", icon: CircleDashed, tone: "neutral" as const },
};

function TopDeviations({ data }: { data: Month }) {
  return (
    <Panel title="Крупнейшие отклонения" description="Дни, где факт сильнее всего разошёлся с планом">
      {data.deviations.length ? (
        <ul className="grid max-h-52 gap-1 overflow-y-auto pr-1">
          {data.deviations.map((d, i) => {
            const meta = DEV[d.kind];
            const w = isoWeek(parseDate(d.date));
            return (
              <li key={i}>
                <Link
                  to={`/week/${w.year}/${w.week}?day=${d.date}&e=${d.employee.id}`}
                  className="flex items-center gap-2 rounded-md px-1 py-0.5 text-[13px] hover:bg-surface-2"
                >
                  <Avatar employee={d.employee} size={20} />
                  <span className="min-w-0 truncate">{d.employee.short_name}</span>
                  <span className="text-ink-3 tnum">
                    {WEEKDAYS_SHORT[weekday(d.date)]} {ddmm(d.date)}
                  </span>
                  <Badge tone={meta.tone} className="ml-auto">
                    <meta.icon />
                    {meta.label}
                    {d.value_sec ? <span className="tnum">{hm(d.value_sec)}</span> : null}
                  </Badge>
                </Link>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="py-6 text-center text-[13px] text-ink-2">Отклонений нет.</p>
      )}
    </Panel>
  );
}
