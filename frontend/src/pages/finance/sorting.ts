import type { FinanceRow } from "@/api/types";
import type { SortOption } from "@/components/domain/SortSelect";

export type FinanceSortKey = "name" | "norm" | "rate" | "salary" | "overtime_pay" | "project_bonuses" | "total";

export const FINANCE_VALUES: Record<FinanceSortKey, (row: FinanceRow) => number | string> = {
  name: (row) => row.employee.short_name,
  norm: (row) => row.summary.norm_sec,
  rate: (row) => Number(row.summary.hourly_rate),
  salary: (row) => Number(row.amounts.salary),
  overtime_pay: (row) => Number(row.amounts.overtime_pay),
  project_bonuses: (row) => Number(row.amounts.project_bonuses),
  total: (row) => Number(row.amounts.total),
};

export const FINANCE_SORT_OPTIONS: SortOption<FinanceSortKey>[] = [
  { key: "total", dir: "desc", label: "Итого: больше → меньше" },
  { key: "total", dir: "asc", label: "Итого: меньше → больше" },
  { key: "project_bonuses", dir: "desc", label: "Премии: больше → меньше" },
  { key: "project_bonuses", dir: "asc", label: "Премии: меньше → больше" },
  { key: "overtime_pay", dir: "desc", label: "За переработку: больше → меньше" },
  { key: "overtime_pay", dir: "asc", label: "За переработку: меньше → больше" },
  { key: "salary", dir: "desc", label: "Оклад: больше → меньше" },
  { key: "salary", dir: "asc", label: "Оклад: меньше → больше" },
  { key: "rate", dir: "desc", label: "Ставка: больше → меньше" },
  { key: "rate", dir: "asc", label: "Ставка: меньше → больше" },
  { key: "norm", dir: "desc", label: "Норма: больше → меньше" },
  { key: "norm", dir: "asc", label: "Норма: меньше → больше" },
  { key: "name", dir: "asc", label: "Сотрудник: А–Я" },
  { key: "name", dir: "desc", label: "Сотрудник: Я–А" },
];
