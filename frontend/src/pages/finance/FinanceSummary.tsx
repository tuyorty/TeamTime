import type { FinanceAmounts } from "@/api/types";
import { cn } from "@/lib/cn";
import { money } from "@/lib/format";

export function FinanceSummary({ amounts, count }: { amounts: FinanceAmounts; count: number }) {
  const items = [
    { label: "Всего по расчёту", value: amounts.total, hint: `Сотрудников: ${count}`, main: true },
    { label: "Оклады", value: amounts.salary, hint: "Полная норма × ставка" },
    { label: "За переработку", value: amounts.overtime_pay, hint: "Сверх нормы по той же ставке" },
    { label: "Проектные премии", value: amounts.project_bonuses, hint: "Добавлены администратором" },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
      {items.map((item) => (
        <section key={item.label} className={cn("min-w-0 rounded-lg border border-line bg-surface p-3 sm:p-4", item.main && "border-accent/40 bg-accent-soft/40")}>
          <h2 className="text-[13px] text-ink-2">{item.label}</h2>
          <p className={cn("mt-2 break-words font-display text-[18px] font-semibold leading-tight tracking-tight tnum sm:text-[25px]", item.main && "text-accent-ink")}>
            {money(item.value ?? "0")}
          </p>
          <p className="mt-2 text-[12px] text-ink-3">{item.hint}</p>
        </section>
      ))}
    </div>
  );
}
