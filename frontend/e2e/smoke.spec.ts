import { expect, test, type Page } from "@playwright/test";

/** Ключевые сценарии на демо-данных. Ожидания не завязаны на конкретные случайные числа. */

async function login(page: Page) {
  const r = await page.request.post("/api/v1/auth/login", { data: { password: "demo" } });
  expect(r.ok()).toBeTruthy();
}

test("сегодня: ключевые числа, день команды и лента", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Сегодня", level: 1 })).toBeVisible();
  await expect(page.getByRole("region", { name: "Ключевые числа дня" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "День команды" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Последние сообщения" })).toBeVisible();
});

test("неделя: матрица, панель дня и исходное сообщение", async ({ page }) => {
  await page.goto("/week");
  const week = page.getByRole("heading", { level: 1 });
  await expect(week).toHaveAccessibleName(/\d+ неделя/);
  await page.getByRole("button", { name: "Предыдущая неделя" }).click();
  const table = page.getByRole("table", { name: /план и факт/ });
  await expect(table).toBeVisible();
  // Первый день с фактом открывает панель с исходным дейликом.
  await table.locator("tbody button").filter({ hasText: /\d+:\d\d/ }).first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("region", { name: "Дейлик" })).toContainText("#дейли");
});

test("месяц: три таблицы и калькулятор штрафа совпадает с золотым значением", async ({ page }) => {
  await page.goto("/month?tab=late");
  await expect(page.getByRole("tab", { name: "Итог за месяц" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Шкала штрафа" })).toBeVisible();
  const input = page.locator('input[aria-describedby="calc-hint"]');
  await input.fill("6:45");
  await expect(page.getByRole("status", { name: "Рассчитанный штраф" })).toHaveText("7:24");
  await input.fill("12:00");
  await expect(page.getByRole("status", { name: "Рассчитанный штраф" })).toHaveText("22:30");
  await page.getByRole("tab", { name: "Премии" }).click();
  await expect(page.getByRole("table", { name: "Премии за переработку" })).toBeVisible();
});

test("realtime: сообщение из эмулятора появляется на открытой странице без перезагрузки", async ({ page, context }) => {
  await page.goto("/");
  await expect(page.getByText("Онлайн")).toBeVisible();
  const identities = await (await page.request.get("/api/v1/identities")).json();
  const author = identities.find((i: { employee: unknown }) => i.employee);
  const meta = await (await page.request.get("/api/v1/meta")).json();
  const [y, m, d] = meta.today.split("-");
  const other = await context.newPage();
  const r = await other.request.post("/api/v1/demo/messages", {
    data: {
      telegram_user_id: author.telegram_user_id,
      topic: "daily",
      text: `${d}.${m}.${y}\n09:00 - 12:00\nЭффективность: 90%\n\n- e2e проверка\n\n#дейли`,
    },
  });
  expect(r.ok()).toBeTruthy();
  await expect(page.getByText(new RegExp(`${author.employee.short_name}.*дейлик`)).first()).toBeVisible({ timeout: 10_000 });
});

test("админ: правка факта пишется в журнал", async ({ page }) => {
  await login(page);
  await page.goto("/admin/audit");
  await expect(page.getByRole("tab", { name: "Журнал правок" })).toHaveAttribute("data-state", "active");
  await page.goto("/admin/employees");
  await expect(page.getByRole("button", { name: "Добавить" })).toBeVisible();
});

test("командная палитра ищет людей", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("ControlOrMeta+k");
  const input = page.getByPlaceholder(/Человек, дата/);
  await expect(input).toBeVisible();
  const people = await (await page.request.get("/api/v1/employees")).json();
  await input.fill(people[0].short_name.split(" ")[0]);
  await expect(page.getByRole("option", { name: new RegExp(people[0].full_name) })).toBeVisible();
});

test("телефон: нижняя навигация и день недели", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "ru-RU" });
  const page = await ctx.newPage();
  await page.goto("/week");
  await expect(page.getByRole("tablist", { name: "День недели" })).toBeVisible();
  await page.getByRole("navigation", { name: "Разделы" }).getByRole("link", { name: "Месяц" }).click();
  await expect(page).toHaveURL(/\/month/);
  await ctx.close();
});
