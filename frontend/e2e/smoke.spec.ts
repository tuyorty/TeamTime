import { expect, test, type Page } from "@playwright/test";
import { lateScheduleExample } from "./fixtures";

/** Ключевые сценарии на демо-данных. Ожидания не завязаны на конкретные случайные числа. */

async function login(page: Page) {
  const r = await page.request.post("/api/v1/auth/login", { data: { password: "demo" } });
  expect(r.ok()).toBeTruthy();
}

test("сегодня: ключевые числа, день команды и лента", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /^Сегодня/, level: 1 })).toBeVisible();
  await expect(page.getByRole("region", { name: "Ключевые числа дня" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "День команды" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Изменения расписания" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Эта неделя", exact: true })).toHaveCount(0);
  await expect(page.getByText("опоздали по дейликам", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Выходной/ })).toBeVisible();
});

test("сегодня: строка выбирает задачи, подробнее открывает день, профиль показывает контакты", async ({ page }) => {
  const today = await (await page.request.get("/api/v1/today")).json();
  const employee = today.rows.find((row: { tasks: string[] }) => row.tasks.length)?.employee ?? today.rows[0].employee;
  await page.goto("/");
  await page.getByRole("button", { name: `Задачи: ${employee.short_name}`, exact: true }).click();
  await expect(page.getByRole("heading", { name: `Задачи · ${employee.short_name}` })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: `Подробнее: ${employee.short_name}`, exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "Профиль", exact: true }).click();
  await expect(page.getByRole("heading", { name: employee.full_name, level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Контакты", exact: true })).toBeVisible();
});

test("итоги дня: выбор даты и дейлики отделены от рабочего экрана", async ({ page }) => {
  const meta = await (await page.request.get("/api/v1/meta")).json();
  await page.goto("/");
  await page.getByRole("radio", { name: "Итоги дня", exact: true }).click();
  await expect(page).toHaveURL(/view=summary/);
  await expect(page.getByRole("navigation", { name: "Разделы" }).getByRole("link", { name: "Итоги дня", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "За сегодня", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Итоги дня", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Итоги по дейликам" })).toBeVisible();
  await expect(page.getByLabel("Дата итогов")).toHaveValue(meta.today);
  await page.getByRole("button", { name: "Предыдущий день" }).click();
  await expect(page.getByLabel("Дата итогов")).not.toHaveValue(meta.today);
  await page.getByRole("radio", { name: "Рабочий день", exact: true }).click();
  await expect(page.getByRole("heading", { name: "День команды", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Итоги по дейликам" })).toHaveCount(0);
  await page.goto(`/day?date=${meta.today}`);
  await expect(page).toHaveURL((url) => url.pathname === "/" && url.searchParams.get("view") === "summary" && url.searchParams.get("date") === meta.today);
  await expect(page.getByLabel("Дата итогов")).toHaveValue(meta.today);
});

test("неделя: матрица, панель дня и исходное сообщение", async ({ page }) => {
  await page.goto("/week");
  const week = page.getByRole("heading", { level: 1 });
  await expect(week).toHaveAccessibleName(/\d+ неделя/);
  await page.getByRole("button", { name: "Предыдущая неделя" }).click();
  const table = page.getByRole("table", { name: /план и факт/ });
  await expect(table).toBeVisible();
  // Первый день с фактом открывает панель с исходным дейликом.
  await table.getByRole("button", { name: /факт \d/ }).first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("region", { name: "Дейлик" })).toContainText("#дейли");
});

test("факты недели и месяца: записи ведут к исходному дню", async ({ page }) => {
  await page.goto("/week");
  await page.getByRole("button", { name: "Факты недели", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Самое раннее начало", exact: true })).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "Самое позднее окончание", exact: true })).toBeVisible();
  await dialog.getByRole("link").first().click();
  await expect(page.getByRole("heading", { name: "Факты недели", exact: true })).toHaveCount(0);
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("region", { name: "Дейлик", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.goto("/month");
  await page.getByRole("button", { name: "Факты месяца", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("heading", { name: "Самый насыщенный день команды", exact: true })).toBeVisible();
});

test("длинный список задач раскрывается внутри ограниченного блока", async ({ page }) => {
  const today = await (await page.request.get("/api/v1/today")).json();
  const employee = today.rows[0].employee;
  today.rows[0].tasks = Array.from({ length: 100 }, (_, index) => `Задача ${index + 1}: ${"описание ".repeat(30)}`);
  await page.route("**/api/v1/today", (route) => route.fulfill({ json: today }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: `Задачи: ${employee.short_name}`, exact: true }).click();
  const list = page.getByRole("region", { name: "Задачи выбранного сотрудника", exact: true });
  await expect(list.getByRole("listitem")).toHaveCount(4);
  await page.getByRole("button", { name: "Показать все задачи (100)", exact: true }).click();
  await expect(list.getByRole("listitem")).toHaveCount(100);
  const bounds = await list.boundingBox();
  expect(bounds!.height).toBeLessThanOrEqual(290);
  expect(await list.evaluate((element) => {
    const node = element as unknown as { scrollHeight: number; clientHeight: number };
    return node.scrollHeight > node.clientHeight;
  })).toBeTruthy();
  expect(await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")).toBeTruthy();
  await page.getByRole("button", { name: "Свернуть задачи", exact: true }).click();
  await expect(list.getByRole("listitem")).toHaveCount(4);
});

test("инбокс: правка показывает последствия до одобрения", async ({ page }) => {
  await login(page);
  const { item, employee, date } = await lateScheduleExample(page.request);
  const change = item.plan_change!.days.find((day) => day.date === date)!;
  expect(change.current.late_sec).toBeGreaterThan(0);
  expect(change.if_accepted.late_sec).toBe(0);
  await page.goto(`/inbox?employee=${employee.id}&kind=schedule`);
  const card = page.getByRole("listitem").filter({ has: page.getByRole("button", { name: "Одобрить новый план", exact: true }) }).first();
  const comparison = card.getByRole("region", { name: "Изменения расписания", exact: true });
  await expect(comparison).toContainText("В табеле сейчас");
  await expect(comparison).toContainText("После одобрения");
  await expect(comparison).toContainText("Опоздание:");
  await card.getByRole("button", { name: "Одобрить новый план", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Одобрить новое расписание?", exact: true })).toBeVisible();
  await expect(dialog).toContainText("Опоздания и итоги пересчитаются");
  const response = page.waitForResponse((response) => response.url().endsWith(`/admin/inbox/${item.parse.id}/resolve`) && response.request().method() === "POST");
  await dialog.getByRole("button", { name: "Одобрить и пересчитать", exact: true }).click();
  expect((await response).ok()).toBeTruthy();
  await expect(dialog).toHaveCount(0);
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

test("профиль: админ сохраняет телефон, описание и фотографию", async ({ page }) => {
  await login(page);
  const employees = await (await page.request.get("/api/v1/employees")).json();
  const employee = employees[0];
  try {
    await page.goto(`/people/${employee.id}`);
    await page.getByRole("link", { name: "Редактировать профиль" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("Телефон", { exact: true }).fill("+0 (000) 000-00-00");
    await dialog.getByLabel("О сотруднике", { exact: true }).fill("Вымышленный профиль для браузерной проверки");
    await dialog.getByLabel("Фотография", { exact: true }).setInputFiles({
      name: "test-avatar.png", mimeType: "image/png",
      buffer: await page.screenshot({ clip: { x: 0, y: 0, width: 32, height: 32 } }),
    });
    await expect(dialog.getByAltText("Фотография сотрудника")).toBeVisible();
    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await page.goto(`/people/${employee.id}`);
    await expect(page.getByRole("link", { name: "+0 (000) 000-00-00", exact: true })).toBeVisible();
    await expect(page.getByText("Вымышленный профиль для браузерной проверки", { exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: "Профиль сотрудника" }).locator("img")).toBeVisible();
  } finally {
    const restored = await page.request.put(`/api/v1/admin/employees/${employee.id}`, {
      data: employee, headers: { "X-Requested-With": "teamtime" },
    });
    expect(restored.ok()).toBeTruthy();
  }
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
  for (const route of ["/", "/people/2", "/day"]) {
    await page.goto(route);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")).toBeTruthy();
  }
  await ctx.close();
});
