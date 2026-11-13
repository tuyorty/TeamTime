import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  const availability = await (await page.request.get("/api/v1/team/session")).json();
  test.skip(!availability.module_available, "Фонд в разработке: нужны отдельная сборка и явное включение");
  await page.request.post("/api/v1/auth/login", { data: { password: "demo" } });
  const people = await (await page.request.get("/api/v1/team/demo-users")).json();
  await page.request.post("/api/v1/team/demo-login", {
    headers: { "X-Requested-With": "teamtime" }, data: { employee_id: people[0].id },
  });
  const state = await (await page.request.get("/api/v1/team/session")).json();
  if (!state.module_enabled) {
    const response = await page.request.put("/api/v1/admin/finance-module", {
      headers: { "X-Requested-With": "teamtime" }, data: { module_enabled: true, expected_enabled: false },
    });
    expect(response.ok()).toBe(true);
  }
});

test("новые финансы: таблица, фильтр и детализация", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto("/finances/2026/11");
  await expect(page.getByRole("columnheader", { name: "Целевая сумма / ставка" })).toBeVisible();
  const before = await page.locator("tbody tr").count();
  await page.getByLabel("Отдел", { exact: true }).selectOption("laboratory");
  await expect.poll(() => page.locator("tbody tr").count()).toBeLessThan(before);
  await page.locator("tbody tr").first().getByRole("button").first().click();
  await expect(page.getByRole("heading", { name: "Как получилась сумма" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("черновик выплаты открывается и без randomUUID по HTTP", async ({ page }) => {
  await page.addInitScript("Object.defineProperty(window.crypto, 'randomUUID', {value: undefined})");
  await page.goto("/finances/2026/11?tab=fund");
  await page.getByRole("button", { name: "Операция", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Операция фонда", exact: true })).toBeVisible();
  await expect(page.getByLabel("Вид операции", { exact: true }).last()).toBeVisible();
});

test("пустой отбор не выгружает всю команду", async ({ page }) => {
  await page.goto("/finances/2026/11");
  await page.getByLabel("Поиск в расчёте фонда").fill("нет такого сотрудника");
  await expect(page.getByText("Нет сотрудников по выбранным условиям")).toBeVisible();
  await expect(page.getByRole("link", { name: "Excel по отбору" })).toHaveAttribute("aria-disabled", "true");
});

test("мобильный финансовый раздел не растягивает страницу", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/finances/2026/11");
  await expect(page.getByRole("columnheader", { name: "Целевая сумма / ставка" })).toBeVisible();
  expect(await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")).toBe(true);
  await page.getByRole("button", { name: "Расходы и компенсации", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Расходы за свой счёт" })).toBeVisible();
  await page.getByRole("button", { name: "Переплаты и займы", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Переплаты участников" })).toBeVisible();
});

test("администратор переключает финансы, другие вкладки получают новый режим", async ({ page, context }) => {
  const second = await context.newPage();
  await page.goto("/finances/2026/11");
  await second.goto("/finances/2026/11?fund=1");
  await expect(second.getByRole("navigation", { name: "Разделы финансов" })).toBeVisible();
  try {
    await page.getByRole("button", { name: "Режим финансов", exact: true }).click();
    await page.getByRole("radio", { name: /Обычные финансы/ }).click();
    await page.getByRole("button", { name: "Применить режим" }).click();
    await expect(page.getByText("Оклады, переработки и премии команды")).toBeVisible();
    await expect(second.getByText("Оклады, переработки и премии команды")).toBeVisible();
    await expect(second.getByRole("navigation", { name: "Разделы финансов" })).toHaveCount(0);
    expect((await page.request.get("/api/v1/fund/overview")).status()).toBe(409);
    await page.getByRole("button", { name: "Режим финансов", exact: true }).click();
    await page.getByRole("radio", { name: /Модуль фонда/ }).click();
    await page.getByRole("button", { name: "Применить режим" }).click();
    await expect(page.getByRole("navigation", { name: "Разделы финансов" })).toBeVisible();
    await expect(second.getByRole("navigation", { name: "Разделы финансов" })).toBeVisible();
    await page.goto("/admin/settings");
    await expect(page.getByRole("radio", { name: /Модуль фонда/ })).toHaveAttribute("aria-checked", "true");
  } finally {
    const state = await (await page.request.get("/api/v1/team/session")).json();
    if (!state.module_enabled) await page.request.put("/api/v1/admin/finance-module", {
      headers: { "X-Requested-With": "teamtime" }, data: { module_enabled: true, expected_enabled: false },
    });
    await second.close();
  }
});
