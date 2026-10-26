import { useMemo, useState } from "react";

import type { MonthRow } from "@/api/types";

export type Quick = "all" | "under" | "met" | "late" | "bonus";

export const QUICK: { value: Quick; label: string; title: string; test: (r: MonthRow) => boolean }[] = [
  { value: "all", label: "Все", title: "Все сотрудники", test: () => true },
  { value: "under", label: "Ниже нормы", title: "Итого меньше месячной нормы", test: (r) => r.summary.norm_progress < 1 },
  { value: "met", label: "Норма выполнена", title: "Итого не меньше нормы", test: (r) => r.summary.norm_progress >= 1 },
  { value: "late", label: "С опозданиями", title: "Хотя бы одно опоздание за месяц", test: (r) => r.summary.late_count > 0 },
  { value: "bonus", label: "С премией", title: "Есть переработка и премия", test: (r) => Number(r.summary.bonus) > 0 },
];

export interface MonthFilter {
  query: string;
  position: string;
  quick: Quick;
}

const EMPTY: MonthFilter = { query: "", position: "", quick: "all" };

/** Фильтры таблиц месяца: общие для «Итога», «Опозданий» и «Премий». */
export function useMonthFilter(rows: readonly MonthRow[]) {
  const [filter, setFilter] = useState<MonthFilter>(EMPTY);
  const positions = useMemo(
    () => [...new Set(rows.map((r) => r.employee.position).filter(Boolean))].sort((a, b) => a.localeCompare(b, "ru")),
    [rows],
  );
  const visible = useMemo(() => {
    const q = filter.query.trim().toLowerCase();
    const quick = QUICK.find((x) => x.value === filter.quick)!;
    return rows.filter(
      (r) =>
        (!q || `${r.employee.full_name} ${r.employee.short_name} ${r.employee.position}`.toLowerCase().includes(q)) &&
        (!filter.position || r.employee.position === filter.position) &&
        quick.test(r),
    );
  }, [rows, filter]);
  const active = filter.query.trim() !== "" || filter.position !== "" || filter.quick !== "all";
  return { filter, setFilter, positions, visible, active, reset: () => setFilter(EMPTY) };
}
