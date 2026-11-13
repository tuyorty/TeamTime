import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { FundRow } from "@/api/fund";
import { money } from "@/lib/format";
import { sumMoney } from "../finance/amounts";
import { Card } from "./shared";

export function FundCharts({
  rows,
  onSelect,
}: {
  rows: FundRow[];
  onSelect: (id: number) => void;
}) {
  const sum = (key: "received" | "supplement" | "compensation") =>
    sumMoney(rows.map((r) => r.amounts?.[key] ?? "0"));
  const parts = [
    {
      name: "Получено из источников",
      value: Number(sum("received")),
      color: "var(--color-accent)",
    },
    {
      name: "Доплата фонда",
      value: Number(sum("supplement")),
      color: "#6577cf",
    },
    {
      name: "Компенсации",
      value: Number(sum("compensation")),
      color: "#bb8c4b",
    },
  ];
  const max = Math.max(
    1,
    ...rows.map(
      (r) =>
        Math.max(0, Number(r.amounts?.received ?? 0)) +
        Number(r.amounts?.accrued ?? 0),
    ),
  );
  return (
    <div
      className="grid gap-4 lg:grid-cols-[0.8fr_1.2fr]"
      aria-label="Графики фонда"
    >
      <Card>
        <h2 className="font-semibold">Источники и фонд</h2>
        <p className="mt-1 text-xs text-ink-3">
          Полученные выплаты и начисления фонда · по отбору
        </p>
        <div className="mx-auto h-56 max-w-72">
          {parts.some((p) => p.value > 0) ? (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart margin={{ top: 16, bottom: 16, left: 16, right: 16 }}>
                <Pie
                  data={parts.filter((p) => p.value > 0)}
                  dataKey="value"
                  innerRadius="65%"
                  outerRadius="94%"
                  paddingAngle={2}
                  isAnimationActive={false}
                  stroke="var(--color-surface)"
                >
                  {parts
                    .filter((p) => p.value > 0)
                    .map((p) => (
                      <Cell key={p.name} fill={p.color} />
                    ))}
                </Pie>
                <Tooltip formatter={(value) => money(String(value))} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-ink-3">
              Начислений пока нет
            </div>
          )}
        </div>
        <div className="grid gap-2">
          {parts.map((p) => (
            <div key={p.name} className="flex justify-between gap-3 text-xs">
              <span className="flex items-center gap-2">
                <i
                  className="size-2 rounded-full"
                  style={{ background: p.color }}
                />
                {p.name}
              </span>
              <span className="tnum font-medium">{money(String(p.value))}</span>
            </div>
          ))}
        </div>
      </Card>
      <Card>
        <h2 className="font-semibold">По сотрудникам</h2>
        <p className="mt-1 text-xs text-ink-3">
          Нажмите на строку для разбора расчёта
        </p>
        <div className="mt-4 max-h-80 space-y-3 overflow-y-auto pr-1">
          {rows.map((r) => (
            <button
              key={r.employee.id}
              className="block w-full rounded-md p-1 text-left hover:bg-surface-2"
              onClick={() => onSelect(r.employee.id)}
            >
              <div className="mb-1 flex justify-between gap-2 text-xs">
                <span>{r.employee.short_name}</span>
                <span className="tnum">
                  {r.amounts
                    ? money(sumMoney([r.amounts.received, r.amounts.accrued]))
                    : "Требует уточнения"}
                </span>
              </div>
              <div className="flex h-2 overflow-hidden rounded-full bg-surface-2">
                {parts.map((p, i) => (
                  <span
                    key={p.name}
                    style={{
                      background: p.color,
                      width: `${(Math.max(0, Number(r.amounts?.[(["received", "supplement", "compensation"] as const)[i]!] ?? 0)) / max) * 100}%`,
                    }}
                  />
                ))}
              </div>
            </button>
          ))}
        </div>
      </Card>
    </div>
  );
}
