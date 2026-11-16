import { expect, type APIRequestContext, type Page } from "@playwright/test";

import type { Employee, EmployeeDetail, Finance, Meta, MonthSummary } from "../src/api/types";

/** Предсказуемые суммы только в ответах браузеру: демо-база остаётся без изменений. */
export async function calculatorExample(request: APIRequestContext) {
  const meta: Meta = await (await request.get("/api/v1/meta")).json();
  expect(meta.demo, "Калькулятор проверяется только на демо-стенде").toBe(true);
  const employees: Employee[] = await (await request.get("/api/v1/employees")).json();
  const employee = employees.find((item) => item.is_active)!;
  expect(employee, "Нужен активный сотрудник из демо-данных").toBeDefined();
  const response = await request.get(`/api/v1/employees/${employee.id}?start=2026-10-01&end=2026-10-31`);
  expect(response.ok()).toBe(true);
  const profile: EmployeeDetail = await response.json();
  const summary: MonthSummary = {
    ...profile.month,
    fund_model: false,
    calculation_ready: true,
    calculation_issues: [],
    fund_salary: null,
    worked_sec: 125 * 3600,
    result_sec: 100 * 3600,
    late_total_sec: 3 * 3600,
    late_count: 2,
    penalty_sec: 5 * 3600,
    total_sec: 95 * 3600,
    norm_sec: 160 * 3600,
    contract_norm_sec: 160 * 3600,
    norm_reduction_sec: 0,
    norm_working_days: 22,
    norm_excluded_days: 0,
    norm_progress: 95 / 160,
    overtime_sec: 0,
    bonus: "0.00",
    hourly_rate: "500.00",
    days_worked: 16,
    days_missing: 0,
    days_no_plan: 0,
    days_without_efficiency: 0,
    statuses: {},
  };
  const amounts = { salary: "80000.00", overtime_pay: "0.00", project_bonuses: "2000.00", total: "82000.00" };
  const finance: Finance = {
    year: 2026,
    month: 10,
    label: "Октябрь 2026",
    complete: true,
    rows: [{ employee, summary, amounts, bonuses: [] }],
    totals: amounts,
  };
  return {
    employee,
    finance,
    profile: {
      ...profile,
      employee: { ...profile.employee, hourly_rate: "500.00", monthly_norm_minutes: 9600 },
      month: summary,
    },
    url: `/people/${employee.id}?period=1m&month=2026-10`,
  };
}

export type CalculatorExample = Awaited<ReturnType<typeof calculatorExample>>;

export async function installCalculatorExample(page: Page, example: CalculatorExample) {
  await page.route((url) => url.pathname === `/api/v1/employees/${example.employee.id}`, (route) =>
    route.fulfill({ json: example.profile }),
  );
  await page.route("**/api/v1/finances/2026/10", (route) => route.fulfill({ json: example.finance }));
}

export async function openCalculator(page: Page) {
  await page.getByRole("button", { name: "Калькулятор эффективности", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Калькулятор эффективности", exact: true });
  await expect(dialog).toBeVisible();
  return dialog;
}
