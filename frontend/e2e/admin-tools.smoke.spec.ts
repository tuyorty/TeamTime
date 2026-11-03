import { expect, test, type APIRequestContext } from "@playwright/test";

const headers = { "X-Requested-With": "teamtime" };

test.beforeEach(async ({ page }) => {
  const request = page.request;
  expect((await (await request.get("/api/v1/meta")).json()).demo).toBe(true);
  expect((await request.post("/api/v1/auth/login", { data: { password: "demo" } })).ok()).toBe(true);
});

async function importMessages(request: APIRequestContext, author: number, name: string, texts: string[]) {
  const exportId = 1900000000 + Math.floor(Math.random() * 100000000);
  const payload = { name: "Проверка старых дейликов", id: exportId, type: "private_supergroup", messages: texts.map((text, index) => ({
    id: index + 1, type: "message", from: name, from_id: `user${author}`,
    date_unixtime: String(Date.parse("2026-06-23T12:00:00Z") / 1000), text,
  })) };
  const send = () => request.post("/api/v1/admin/import/telegram", { headers, multipart: { file: { name: "result.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(payload)) } } });
  const response = await send();
  expect(response.ok()).toBeTruthy();
  return { send, chatId: (await response.json()).chat_id };
}

test("аккаунты: удаление, повторный импорт и восстановление", async ({ page }) => {
  const request = page.request;
  const userId = 9000000000 + Math.floor(Math.random() * 100000000);
  const name = `Проверка удаления ${userId}`;
  const imported = await importMessages(request, userId, name, ["#дейлик\n22.06.2026\n10:00-18:00"]);
  await page.goto("/admin/telegram");
  const row = page.getByRole("row").filter({ hasText: name });
  await row.getByRole("button", { name: `Удалить аккаунт ${name}`, exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Повторный импорт не вернёт");
  await dialog.getByRole("button", { name: "Удалить аккаунт", exact: true }).click();
  await expect(row).toHaveCount(0);
  expect((await imported.send()).ok()).toBeTruthy();
  await page.reload();
  await expect(row).toHaveCount(0);
  await page.getByRole("button", { name: "Удалённые аккаунты", exact: true }).click();
  await row.getByRole("button", { name: "Восстановить аккаунт", exact: true }).click();
  await expect(row).toHaveCount(0);
  await page.getByRole("button", { name: "Действующие аккаунты", exact: true }).click();
  await expect(row).toBeVisible();
});

test("старые дейлики: предпросмотр и массовое закрытие без изменения эффективности", async ({ page }) => {
  const request = page.request;
  const identities = await (await request.get("/api/v1/identities")).json();
  const identity = identities.find((item: { employee: unknown }) => item.employee);
  const imported = await importMessages(request, identity.telegram_user_id, identity.display_name, [
    "#дейлик\n22.06.2026\n10:00-18:00\n- проверка без эффективности",
    "#дейлик\n22.06.2026\nБез науки",
  ]);
  await page.goto("/inbox");
  await page.getByRole("button", { name: "Массовая обработка дейликов", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Старые дейлики", exact: true });
  await dialog.getByLabel("Беседа", { exact: true }).selectOption(String(imported.chatId));
  await dialog.getByRole("button", { name: "Предпросмотр выборки", exact: true }).click();
  await expect(dialog).toContainText("Подходит записей: 1");
  await expect(dialog).toContainText("проверка без эффективности");
  await dialog.getByRole("button", { name: "Закрыть 1 запись без изменения часов", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  const preview = await (await request.post("/api/v1/admin/inbox/bulk/preview", { headers, data: { target: "missing_efficiency", chat_id: imported.chatId } })).json();
  expect(preview.count).toBe(0);
  await page.getByRole("button", { name: "Массовая обработка дейликов", exact: true }).click();
  await dialog.getByLabel("Что обработать", { exact: true }).selectOption("no_time");
  await dialog.getByRole("button", { name: "Предпросмотр выборки", exact: true }).click();
  await expect(dialog).toContainText("Подходит записей: 1");
  await expect(dialog).toContainText("Без науки");
  await dialog.getByRole("button", { name: "Закрыть 1 запись без изменения часов", exact: true }).click();
  await expect(dialog).toHaveCount(0);
});

test("профиль: прошлые месяцы, выбор месяца и возврат к текущему", async ({ page }) => {
  const request = page.request;
  const people = await (await request.get("/api/v1/employees")).json();
  const meta = await (await request.get("/api/v1/meta")).json();
  const current = meta.today.slice(0, 7);
  const [year, month] = current.split("-").map(Number);
  const previousDate = new Date(year, month - 2, 1);
  const previous = `${previousDate.getFullYear()}-${String(previousDate.getMonth() + 1).padStart(2, "0")}`;
  await page.goto(`/people/${people[0].id}`);
  await expect(page.getByLabel("Месяц статистики")).toHaveValue(current);
  await page.getByRole("button", { name: "Предыдущий месяц", exact: true }).click();
  await expect(page.getByLabel("Месяц статистики")).toHaveValue(previous);
  await expect(page).toHaveURL(new RegExp(`month=${previous}`));
  await expect(page.getByRole("region", { name: "Итоги месяца", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Месяц статистики")).toHaveValue(previous);
  await page.getByLabel("Месяц статистики").fill("2026-06");
  await expect(page).toHaveURL(/month=2026-06/);
  await page.getByRole("button", { name: "Текущий", exact: true }).click();
  await expect(page.getByLabel("Месяц статистики")).toHaveValue(current);
  await page.getByLabel("Период статистики").selectOption("custom");
  await expect(page.getByLabel("Начало периода")).toBeVisible();
});

test("отделы: фильтр недели, месяца и финансов", async ({ page }) => {
  const request = page.request;
  const people = await (await request.get("/api/v1/employees")).json();
  const person = people[0];
  const path = `/api/v1/admin/employees/${person.id}`;
  expect((await request.put(path, { headers, data: { ...person, department: "laboratory" } })).ok()).toBeTruthy();
  try {
    for (const url of ["/week", "/month", "/finances", "/plans", "/people", "/calendar"]) {
      await page.goto(url);
      await page.getByLabel("Отдел", { exact: true }).selectOption("laboratory");
      const scope = await page.getByRole("table").count() ? page.getByRole("table").first() : page.locator("main");
      const nameKey = url === "/people" ? "full_name" : "short_name";
      await expect(scope.getByText(person[nameKey], { exact: true }).first()).toBeVisible();
      for (const other of people.filter((employee: { id: number }) => employee.id !== person.id)) {
        await expect(scope.getByText(other[nameKey], { exact: true })).toHaveCount(0);
      }
    }
  } finally {
    expect((await request.put(path, { headers, data: person })).ok()).toBeTruthy();
  }
});
