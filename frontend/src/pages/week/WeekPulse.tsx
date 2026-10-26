import { AlarmClock, CircleDashed, Hourglass, LogOut } from "lucide-react";
import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { Week } from "@/api/types";
import { TooltipBox } from "@/components/charts/ChartTooltip";
import { planFactShape } from "@/components/charts/PlanFactBar";
import { axisProps, chart } from "@/components/charts/theme";
import { Avatar } from "@/components/domain/Avatar";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";
import { WEEKDAYS_SHORT, count, dayMonthShort, hm, weekday } from "@/lib/format";

interface Item {
  key: string;
  employee: Week["rows"][number]["employee"];
  date: string;
  kind: "late" | "early_leave" | "undertime" | "missing";
  value: number | null;
}

const ICON = { late: AlarmClock, early_leave: LogOut, undertime: Hourglass, missing: CircleDashed };
const LABEL = { late: "опоздание", early_leave: "ранний уход", undertime: "недоработка", missing: "нет дейлика" };
const TONE = { late: "late", early_leave: "deviation", undertime: "deviation", missing: "neutral" } as const;

const pulseShape = planFactShape({
  outlineKey: "plan",
  fillKey: "fact",
  outlineColor: chart.ink3,
  fillColor: chart.accent,
  fillRatio: 0.6,
  radius: 4,
});

/** «Пульс недели»: сколько часов план и факт по дням, и где они разошлись. */
export function WeekPulse({ data }: { data: Week }) {
  const planned = useMemo(
    () =>
      data.days.map((d, i) => {
        const plan = data.rows.reduce((s, r) => s + (r.cells[i]!.plan?.planned_sec ?? 0), 0);
        const fact = data.day_totals[i]!.worked_sec;
        return {
          day: WEEKDAYS_SHORT[weekday(d)]!,
          date: d,
          plan: plan / 3600,
          fact: fact / 3600,
          outer: Math.max(plan, fact) / 3600,
          late: data.day_totals[i]!.late_count,
          planned: data.day_totals[i]!.planned_count,
          reported: data.day_totals[i]!.worked_count,
        };
      }),
    [data],
  );

  const items = useMemo(() => {
    const out: Item[] = [];
    for (const r of data.rows)
      for (const c of r.cells) {
        const add = (kind: Item["kind"], value: number | null) =>
          out.push({ key: `${r.employee.id}-${c.date}-${kind}`, employee: r.employee, date: c.date, kind, value });
        if (c.late_sec) add("late", c.late_sec);
        if (c.early_leave_sec) add("early_leave", c.early_leave_sec);
        if (c.undertime_sec && !c.early_leave_sec) add("undertime", c.undertime_sec);
        if (c.state === "missing") add("missing", null);
      }
    return out.sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  }, [data]);

  const planTotal = planned.reduce((s, d) => s + d.plan, 0);
  const factTotal = planned.reduce((s, d) => s + d.fact, 0);

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
      <Panel
        title="Пульс недели"
        description={`Часы команды по дням: план ${hm(planTotal * 3600)}, факт ${hm(factTotal * 3600)}`}
      >
        <div className="h-48" role="img" aria-label="План и факт часов команды по дням недели">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={planned} barCategoryGap="30%">
              <CartesianGrid vertical={false} stroke={chart.line} />
              <XAxis dataKey="day" {...axisProps} />
              <YAxis {...axisProps} width={28} tickFormatter={(v: number) => `${v}`} />
              <Tooltip
                cursor={{ fill: "var(--surface-2)" }}
                content={({ active, payload }) => {
                  const p = payload?.[0]?.payload as (typeof planned)[number] | undefined;
                  if (!active || !p) return null;
                  return (
                    <TooltipBox
                      title={`${p.day}, ${dayMonthShort(p.date)}`}
                      rows={[
                        { label: "План", value: hm(p.plan * 3600) },
                        { label: "Факт", value: hm(p.fact * 3600), color: chart.accent },
                        { label: "Дейликов", value: p.planned ? `${p.reported} из ${p.planned}` : p.reported },
                        { label: "Опоздали", value: p.late },
                      ]}
                    />
                  );
                }}
              />
              <Bar dataKey="outer" shape={pulseShape} activeBar={pulseShape} maxBarSize={36} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <table className="sr-only">
          <caption>План и факт по дням</caption>
          <tbody>
            {planned.map((p) => (
              <tr key={p.date}>
                <th>{p.day}</th>
                <td>план {hm(p.plan * 3600)}</td>
                <td>факт {hm(p.fact * 3600)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Panel
        title="Расхождения плана и факта"
        description={items.length ? count(items.length, ["случай", "случая", "случаев"]) + " за неделю" : "Всё по плану"}
      >
        {items.length ? (
          <ul className="grid max-h-48 gap-1 overflow-y-auto pr-1">
            {items.slice(0, 30).map((it) => {
              const Icon = ICON[it.kind];
              return (
                <li key={it.key} className="flex items-center gap-2 text-[13px]">
                  <Avatar employee={it.employee} size={20} />
                  <span className="min-w-0 truncate">{it.employee.short_name}</span>
                  <span className="text-ink-3 tnum">{WEEKDAYS_SHORT[weekday(it.date)]} {dayMonthShort(it.date)}</span>
                  <Badge tone={TONE[it.kind]} className="ml-auto">
                    <Icon />
                    {LABEL[it.kind]}
                    {it.value ? <span className="tnum">{hm(it.value)}</span> : null}
                  </Badge>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="py-6 text-center text-[13px] text-ink-2">Опозданий, ранних уходов и пропущенных дейликов нет.</p>
        )}
      </Panel>
    </div>
  );
}
