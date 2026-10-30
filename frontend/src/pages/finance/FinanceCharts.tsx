import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip as ChartTooltip } from "recharts";

import type { FinanceAmounts, FinanceRow } from "@/api/types";
import { TooltipBox } from "@/components/charts/ChartTooltip";
import { chart } from "@/components/charts/theme";
import { Panel } from "@/components/ui/panel";
import { Segmented } from "@/components/ui/segmented";
import { Tooltip } from "@/components/ui/tooltip";
import { money } from "@/lib/format";
import { useTheme } from "@/lib/theme";

import { sumAmounts, sumMoney } from "./amounts";

type Part = { key: Exclude<keyof FinanceAmounts, "total">; label: string; color: string };
const percentFormat = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });

function share(value: number, total: number) {
  const percent = total > 0 ? value / total * 100 : 0;
  return percent > 0 && percent < 0.1 ? "< 0,1%" : `${percentFormat.format(percent)}%`;
}

export function FinanceCharts({ rows, onSelect }: { rows: FinanceRow[]; onSelect: (id: number) => void }) {
  const { isDark } = useTheme();
  const [mode, setMode] = useState<"all" | "extra">("all");
  if (!rows.length) return null;
  const totals = sumAmounts(rows);
  const parts: Part[] = [
    { key: "salary", label: "Оклады", color: chart.accent },
    { key: "overtime_pay", label: "Переработки", color: chart.absence },
    { key: "project_bonuses", label: "Проектные премии", color: isDark ? "#9085e9" : "#6250d6" },
  ];
  const sectors = parts.map((part) => ({ ...part, value: Number(totals[part.key]) }));
  const total = Number(totals.total);
  const visibleParts = mode === "extra" ? parts.slice(1) : parts;
  const employees = rows.map((row) => ({
    ...row,
    shown: mode === "extra" ? sumMoney([row.amounts.overtime_pay, row.amounts.project_bonuses]) : row.amounts.total,
  }));
  const maximum = Math.max(...employees.map((row) => Number(row.shown)));

  return (
    <div aria-label="Графики финансов" role="region" className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
      <Panel title="Состав начислений" description={`Выбранный месяц · сотрудников в отборе: ${rows.length}`}>
        <div className="relative mx-auto h-[240px] w-full max-w-[280px]">
          {total > 0 ? (
            <div role="img" aria-label={`Оклады ${money(totals.salary)}, переработки ${money(totals.overtime_pay)}, проектные премии ${money(totals.project_bonuses)}`} className="h-full">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart margin={{ top: 12, right: 12, bottom: 12, left: 12 }}>
                  <Pie data={sectors.filter((part) => part.value > 0)} dataKey="value" nameKey="label" innerRadius="72%" outerRadius="96%" startAngle={90} endAngle={-270} paddingAngle={2} stroke={chart.surface} strokeWidth={3} isAnimationActive={false}>
                    {sectors.filter((part) => part.value > 0).map((part) => <Cell key={part.key} fill={part.color} />)}
                  </Pie>
                  <ChartTooltip isAnimationActive={false} content={({ active, payload }) => {
                    const part = payload?.[0]?.payload as (typeof sectors)[number] | undefined;
                    return active && part ? <TooltipBox title={part.label} rows={[
                      { label: "Сумма", value: money(totals[part.key]), color: part.color },
                      { label: "Доля начислений", value: share(part.value, total) },
                    ]} /> : null;
                  }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : <div className="absolute left-1/2 top-1/2 size-48 -translate-x-1/2 -translate-y-1/2 rounded-full border-[22px] border-line" />}
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-1">
            <span className="text-[12px] text-ink-3">Всего по отбору</span>
            <span className="max-w-40 break-words text-center font-display text-[18px] font-semibold tracking-tight tnum">{money(totals.total)}</span>
          </div>
        </div>
        <dl aria-label="Суммы на диаграмме" className="mt-1 grid gap-1">
          {sectors.map((part) => (
            <div key={part.key} className="flex items-center justify-between gap-3 rounded-md px-1 py-2.5">
              <dt className="flex min-w-0 items-center gap-2 text-[13px] text-ink-2"><span className="size-2.5 shrink-0 rounded-sm" style={{ background: part.color }} />{part.label}</dt>
              <dd className="shrink-0 text-right tnum"><span className="block text-[14px] font-medium">{money(totals[part.key])}</span><span className="text-[12px] text-ink-3">{share(part.value, total)}</span></dd>
            </div>
          ))}
        </dl>
        {total === 0 ? <p className="mt-2 text-[12px] text-ink-3">По этому отбору начислений пока нет.</p> : null}
      </Panel>
      <Panel title="Начисления по сотрудникам" description="Нажмите на сотрудника, чтобы открыть расчёт" actions={
        <Segmented value={mode} onChange={setMode} label="Состав графика сотрудников" options={[
          { value: "all", label: "Все начисления" }, { value: "extra", label: "Только доплаты" },
        ]} />
      }>
        <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-ink-3">
          {visibleParts.map((part) => <span key={part.key} className="flex items-center gap-1.5"><span className="size-2 shrink-0 rounded-sm" style={{ background: part.color }} />{part.label}</span>)}
        </div>
        <div className="max-h-[25rem] overflow-y-auto pr-1 [scrollbar-gutter:stable]" tabIndex={0} role="region" aria-label="График начислений по сотрудникам">
          <ul aria-label="Сотрудники на графике" className="grid gap-1">
            {employees.map((row) => (
              <li key={row.employee.id}>
                <Tooltip content={<div className="py-0.5"><p className="mb-1 font-medium">{row.employee.full_name}</p><dl className="grid gap-1">
                  {parts.map((part) => <div key={part.key} className="flex items-center justify-between gap-4"><dt className="flex items-center gap-1.5 text-ink-2"><span className="size-2 shrink-0 rounded-sm" style={{ background: part.color }} />{part.label}</dt><dd className="whitespace-nowrap font-medium tnum">{money(row.amounts[part.key])}</dd></div>)}
                </dl></div>}>
                  <button onClick={() => onSelect(row.employee.id)} aria-label={`График: ${row.employee.short_name}, ${money(row.shown)}`} className="group w-full rounded-md px-2 py-2.5 text-left hover:bg-surface-2">
                    <span className="mb-1.5 flex items-baseline justify-between gap-3 text-[12px]"><span className="truncate text-ink-2">{row.employee.short_name}</span><span className="flex shrink-0 items-center gap-1 font-medium tnum">{money(row.shown)}<ChevronRight className="size-3 text-ink-3" /></span></span>
                    <span aria-hidden className="flex h-3.5 overflow-hidden rounded-[4px] bg-surface-2 ring-1 ring-inset ring-line/40">
                      {visibleParts.filter((part) => Number(row.amounts[part.key]) > 0).map((part) => <span key={part.key} className="block h-full shrink-0 border-r border-surface/50 last:border-0" style={{ width: `${maximum > 0 ? Number(row.amounts[part.key]) / maximum * 100 : 0}%`, background: part.color }} />)}
                    </span>
                  </button>
                </Tooltip>
              </li>
            ))}
          </ul>
        </div>
        {mode === "extra" && maximum === 0 ? <p className="mt-3 text-[12px] text-ink-3">За выбранный месяц и отбор переработок и проектных премий нет.</p> : null}
      </Panel>
    </div>
  );
}
