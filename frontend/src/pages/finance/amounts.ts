import type { FinanceAmounts, FinanceRow } from "@/api/types";

/** Денежные суммы уже рассчитаны сервером; складываем их без погрешности дробных чисел. */
export function sumMoney(values: readonly string[]): string {
  const cents = values.reduce((total, value) => {
    const [rubles, fraction = ""] = value.split(".");
    return total + BigInt(rubles!) * 100n + BigInt(fraction.padEnd(2, "0"));
  }, 0n);
  return `${cents / 100n}.${String(cents % 100n).padStart(2, "0")}`;
}

/** Складываем готовые серверные суммы в копейках, без округления ставок и часов на клиенте. */
export function sumAmounts(rows: FinanceRow[]): FinanceAmounts {
  const sum = (key: keyof FinanceAmounts) => sumMoney(rows.map((row) => row.amounts[key]));
  return { salary: sum("salary"), overtime_pay: sum("overtime_pay"), project_bonuses: sum("project_bonuses"), total: sum("total") };
}
