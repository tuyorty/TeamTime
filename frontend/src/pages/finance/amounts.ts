import type { FinanceAmounts, FinanceRow } from "@/api/types";

/** Складываем готовые серверные суммы в копейках, без округления ставок и часов на клиенте. */
export function sumAmounts(rows: FinanceRow[]): FinanceAmounts {
  const sum = (key: keyof FinanceAmounts) => {
    const cents = rows.reduce((total, row) => {
      const [rubles, fraction = ""] = row.amounts[key].split(".");
      return total + BigInt(rubles!) * 100n + BigInt(fraction.padEnd(2, "0"));
    }, 0n);
    return `${cents / 100n}.${String(cents % 100n).padStart(2, "0")}`;
  };
  return { salary: sum("salary"), overtime_pay: sum("overtime_pay"), project_bonuses: sum("project_bonuses"), total: sum("total") };
}
