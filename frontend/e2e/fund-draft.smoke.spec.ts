import { expect, test } from "@playwright/test";

test("фонд в разработке: обычные финансы и запрет включения", async ({ page }) => {
  const session = await (await page.request.get("/api/v1/team/session")).json();
  test.skip(session.module_available, "Проверка обычного выпуска без модуля фонда");
  expect(session.module_enabled).toBe(false);
  await page.request.post("/api/v1/auth/login", { data: { password: "demo" } });
  await page.goto("/finances/2026/11?fund=1");
  await expect(page.getByText("Оклады, переработки и премии команды")).toBeVisible();
  await expect(page.getByRole("button", { name: "Режим финансов", exact: true })).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "Разделы финансов" })).toHaveCount(0);
  await page.goto("/admin/settings");
  await expect(page.getByText("Модуль фонда — в разработке", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Применить режим" })).toHaveCount(0);
  expect((await page.request.put("/api/v1/admin/finance-module", {
    headers: { "X-Requested-With": "teamtime" }, data: { module_enabled: true, expected_enabled: false },
  })).status()).toBe(409);
  expect((await page.request.get("/api/v1/fund/overview")).status()).toBe(409);
});
