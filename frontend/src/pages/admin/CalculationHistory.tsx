import { useCalculationHistory } from "@/api/queries";
import type { AppSettings } from "@/api/types";
import { Button } from "@/components/ui/button";
import { hm } from "@/lib/format";

export function CalculationHistory({
  employeeId,
  onSelect,
}: {
  employeeId?: number;
  onSelect?: (month: string, value: Partial<AppSettings>) => void;
}) {
  const { data } = useCalculationHistory();
  if (!data) return null;
  return (
    <details className="rounded-md border border-line bg-surface p-3 text-[12px]">
      <summary className="cursor-pointer font-medium">История условий расчёта</summary>
      <p className="my-3 text-ink-3">
        Версия с 01.01.2000 — исходные условия на момент обновления. Более ранние изменения, которых не было в
        базе, восстановить нельзя.
      </p>
      <div className="grid max-h-64 gap-2 overflow-y-auto">
        {employeeId
          ? data.terms
              .filter((row) => Number(row.employee_id) === employeeId)
              .map((row, index) => (
                <p key={index}>
                  С {String(row.effective_from)} · норма {hm(Number(row.monthly_norm_minutes) * 60)} ·{" "}
                  {String(row.hourly_rate)} ₽/ч
                </p>
              ))
          : data.calculations.map((row, index) => {
              const value = row.value as Partial<AppSettings>;
              return (
                <div key={index} className="rounded bg-surface-2 p-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <b>С {String(row.effective_from)}</b>
                    {onSelect ? (
                      <Button
                        size="sm"
                        onClick={() => onSelect(String(row.effective_from).slice(0, 7), value)}
                      >
                        Загрузить условия
                      </Button>
                    ) : null}
                  </div>
                  <p className="mt-2 leading-5 text-ink-3">
                    Допуск опоздания: {value.late_tolerance_min ?? 0} мин · раннего ухода:{" "}
                    {value.early_tolerance_min ?? 0} мин · недоработки: {value.undertime_tolerance_min ?? 0}{" "}
                    мин. Изменения расписания: за {value.plan_notice_hours ?? 12} ч. Праздников:{" "}
                    {value.holidays?.length ?? 0}. Пояс: {value.timezone ?? "по умолчанию"}. Штраф: пороги{" "}
                    {value.penalty?.soft_limit_h ?? "5"} / {value.penalty?.hard_limit_h ?? "12"} ч.
                  </p>
                </div>
              );
            })}
      </div>
    </details>
  );
}
