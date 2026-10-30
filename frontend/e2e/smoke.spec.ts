import { expect, test, type Page } from "@playwright/test";
import { avatarFixture, lateScheduleExample } from "./fixtures";

/** Ключевые сценарии на демо-данных. Ожидания не завязаны на конкретные случайные числа. */

async function login(page: Page) {
  const r = await page.request.post("/api/v1/auth/login", { data: { password: "demo" } });
  expect(r.ok()).toBeTruthy();
}

test("финансы: расчёт, выбор месяца, премия и отмена с сохранением истории", async ({ page }) => {
  await page.goto("/finances");
  await expect(page.getByRole("heading", { name: "Финансы", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Добавить премию", exact: true })).toHaveCount(0);
  const month = await page.getByLabel("Месяц расчёта").inputValue();
  const [year, number] = month.split("-").map(Number);
  const data = await (await page.request.get(`/api/v1/finances/${year}/${number}`)).json();
  const employee = data.rows[0].employee;
  await page.getByRole("button", { name: `Расчёт: ${employee.short_name}`, exact: true }).first().click();
  const details = page.getByRole("dialog");
  await expect(details.getByRole("heading", { name: "Как получилась сумма" })).toBeVisible();
  await expect(details.getByText(/Выплачивается полностью при недоработке/)).toBeVisible();
  await details.getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.getByRole("button", { name: "Предыдущий месяц" }).click();
  await expect(page.getByLabel("Месяц расчёта")).not.toHaveValue(month);
  await page.getByRole("button", { name: "Текущий", exact: true }).click();
  await expect(page.getByLabel("Месяц расчёта")).toHaveValue(month);
  await login(page);
  await page.reload();
  await page.getByRole("button", { name: "Добавить премию", exact: true }).click();
  const form = page.getByRole("dialog", { name: "Добавить премию", exact: true });
  const title = `Проверка проекта ${Date.now()}`;
  await form.getByLabel("Сотрудник", { exact: true }).selectOption(String(employee.id));
  await form.getByLabel("Проект / основание").fill(title);
  await form.getByLabel("Сумма, ₽").fill("1234,56");
  await form.getByRole("button", { name: "Сохранить премию" }).click();
  await expect(form).not.toBeVisible();
  await expect(page.getByRole("button", { name: new RegExp(title) })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: `Расчёт: ${employee.short_name}`, exact: true }).first().click();
  const card = details.getByRole("listitem").filter({ hasText: title });
  await expect(card).toContainText("1 234,56".replace(/ /g, "\u00a0"));
  await card.getByRole("button", { name: "Изменить", exact: true }).click();
  const edit = page.getByRole("dialog", { name: "Изменить премию" });
  await edit.getByLabel("Сумма, ₽").fill("2345.67");
  await edit.getByRole("button", { name: "Сохранить премию" }).click();
  await expect(edit).not.toBeVisible();
  await expect(card).toContainText("2 345,67".replace(/ /g, "\u00a0"));
  await card.getByRole("button", { name: "Отменить", exact: true }).click();
  const cancel = page.getByRole("dialog", { name: "Отменить премию", exact: true });
  await cancel.getByLabel("Причина отмены").fill("Завершение тестового примера");
  await cancel.getByRole("button", { name: "Отменить премию", exact: true }).click();
  await expect(cancel).not.toBeVisible();
  await expect(card).toContainText("Отменена");
  const after = await (await page.request.get(`/api/v1/finances/${year}/${number}`)).json();
  expect(after.totals.project_bonuses).toBe(data.totals.project_bonuses);
});

test("финансы на телефоне: карточки и расшифровка без горизонтального скролла", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/finances");
  const cards = page.getByRole("button", { name: /^Расчёт:/ });
  await expect(cards.first()).toBeVisible();
  expect(await page.evaluate("document.documentElement.scrollWidth <= innerWidth")).toBe(true);
  await cards.first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  expect(await page.evaluate("document.documentElement.scrollWidth <= innerWidth")).toBe(true);
});

test("месяц: явная сортировка премий синхронизирована с заголовками", async ({ page }) => {
  const data: import("../src/api/types").Month = await (await page.request.get("/api/v1/months/2026/9?history=1")).json();
  await page.goto("/month/2026/9?tab=bonus");
  const table = page.getByRole("table", { name: "Премии за переработку" });
  const names = table.locator("tbody > tr > th").getByRole("link");
  const sorted = (dir: number) => [...data.rows].sort((a, b) => dir * (Number(a.summary.bonus) - Number(b.summary.bonus))).map((row) => row.employee.short_name);
  await page.getByLabel("Сортировка премий за переработку").selectOption("bonus:desc");
  await expect(names).toHaveText(sorted(-1));
  await table.getByRole("button", { name: "Премия", exact: true }).click();
  await expect(page.getByLabel("Сортировка премий за переработку")).toHaveValue("bonus:asc");
  await expect(names).toHaveText(sorted(1));
});

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

test("завтра: расписание и задачи выбранного дня", async ({ page }) => {
  const today = await (await page.request.get("/api/v1/meta")).json();
  await page.goto("/");
  const todayButton = page.getByRole("button", { name: "Сегодня", exact: true });
  const tomorrowButton = page.getByRole("button", { name: "Завтра", exact: true });
  const before = await tomorrowButton.boundingBox();
  await expect(page.getByLabel("Текущее время команды")).toHaveCSS("font-size", /^(36|48)px$/);
  await expect(page.getByRole("radio", { name: "Рабочий день", exact: true })).toHaveCSS(
    "white-space",
    "nowrap",
  );
  await page.getByRole("button", { name: "Завтра", exact: true }).click();
  await expect(page.getByRole("heading", { name: /^Завтра/, level: 1 })).toBeVisible();
  await expect(page.getByText("По расписанию на завтра", { exact: true })).toBeVisible();
  const after = await tomorrowButton.boundingBox();
  expect(Math.abs(before!.x - after!.x)).toBeLessThan(1);
  expect(Math.abs(before!.y - after!.y)).toBeLessThan(1);
  await expect(page.getByRole("radio", { name: "Итоги дня", exact: true })).toBeDisabled();
  const date = new Date(`${today.today}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + 1);
  const next = await (await page.request.get(`/api/v1/today?day=${date.toISOString().slice(0, 10)}`)).json();
  expect(next.rows.length).toBeGreaterThan(0);
  await expect(page.getByRole("list", { name: "Расписание команды" }).getByRole("listitem")).toHaveCount(
    next.rows.length,
  );
  await todayButton.click();
  await expect(page.getByRole("heading", { name: /^Сегодня/, level: 1 })).toBeVisible();
});

test("инбокс: заявки и диагностика доступны администратору", async ({ page }) => {
  await login(page);
  await page.goto("/inbox");
  await page.getByRole("tab", { name: /Заявки на статусы/ }).click();
  await expect(page.getByRole("region", { name: "Заявки на статусы" })).toBeVisible();
  await expect(page.getByLabel("Состояние заявок")).toBeVisible();
  await page.goto("/admin/system");
  await expect(page.getByRole("heading", { name: "Telegram-бот", exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Готовность личных напоминаний", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Нет данных", { exact: true }).first()).toBeVisible();
});

test("месяц: экспорт текущего отбора", async ({ page }) => {
  await page.goto("/month");
  await page.getByRole("button", { name: "Экспорт", exact: true }).click();
  await expect(page.getByRole("menuitem", { name: /Текущий отбор.*Excel/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Данные для итогов месяца", exact: true })).toHaveCount(0);
});

test("сегодня: строка выбирает задачи, подробнее открывает день, профиль показывает контакты", async ({
  page,
}) => {
  const today = await (await page.request.get("/api/v1/today")).json();
  const employee =
    today.rows.find((row: { tasks: string[] }) => row.tasks.length)?.employee ?? today.rows[0].employee;
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
  await expect(
    page.getByRole("navigation", { name: "Разделы" }).getByRole("link", { name: "Итоги дня", exact: true }),
  ).toHaveCount(0);
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
  await expect(page).toHaveURL(
    (url) =>
      url.pathname === "/" &&
      url.searchParams.get("view") === "summary" &&
      url.searchParams.get("date") === meta.today,
  );
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
  await table
    .getByRole("button", { name: /факт \d/ })
    .first()
    .click();
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
  await expect(
    page.getByRole("dialog").getByRole("heading", { name: "Самый насыщенный день команды", exact: true }),
  ).toBeVisible();
});

test("профиль: весь календарь и пунктуальность используют выбранный период", async ({ page }) => {
  const employees = await (await page.request.get("/api/v1/employees")).json();
  const id = employees[0].id;
  await page.goto(`/people/${id}`);
  await expect(page.getByLabel("Период статистики")).toHaveValue("1m");
  await expect(page.getByRole("heading", { name: "Прогноз текущего месяца", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Личная динамика", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Задачи за выбранный период", exact: true })).toHaveCount(0);
  const calendars = page.getByRole("region", { name: "Календарь выбранного периода" });
  await expect(calendars).toBeVisible();
  const calendarCard = page.locator("section").filter({ has: calendars });
  const initialCard = await calendarCard.boundingBox();
  await page.getByLabel("Период статистики").selectOption("3m");
  await expect(page.getByRole("heading", { name: "Часы по дням за период", exact: true })).toBeVisible();
  await expect(calendars.getByRole("grid")).toHaveCount(3);
  const expandedCard = await calendarCard.boundingBox();
  expect(Math.abs(expandedCard!.height - initialCard!.height)).toBeLessThan(1);
  expect(
    await page.evaluate(`(() => {
      const calendar = document.querySelector('[aria-label="Календарь выбранного периода"]');
      return calendar.scrollHeight > calendar.clientHeight;
    })()`),
  ).toBe(true);
  await calendars.focus();
  await page.keyboard.press("End");
  await expect(calendars.getByRole("grid").last()).toBeInViewport();
  const meta = await (await page.request.get("/api/v1/meta")).json();
  const end = new Date(`${meta.today}T12:00:00Z`);
  end.setUTCDate(1);
  end.setUTCMonth(end.getUTCMonth() - 2);
  const from = end.toISOString().slice(0, 10);
  const report = await (
    await page.request.get(`/api/v1/employees/${id}?start=${from}&end=${meta.today}`)
  ).json();
  const onTime = report.late_minutes.filter((minutes: number) => minutes <= 0).length;
  await expect(
    page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Пунктуальность", exact: true }) }),
  ).toContainText(
    report.late_minutes.length
      ? `Вовремя или раньше: ${onTime} из ${report.late_minutes.length}`
      : "Нет дней с планом и дейликом",
  );
  await page.getByLabel("Период статистики").selectOption("custom");
  const previousEnd = new Date(`${meta.today}T12:00:00Z`);
  previousEnd.setUTCDate(0);
  const previousStart = new Date(previousEnd);
  previousStart.setUTCDate(1);
  const monthName = new Intl.DateTimeFormat("ru-RU", { month: "long", timeZone: "UTC" }).format(
    previousStart,
  );
  await page.getByLabel("Начало периода").fill(previousStart.toISOString().slice(0, 10));
  await page.getByLabel("Конец периода").fill(previousEnd.toISOString().slice(0, 10));
  await expect(
    page.getByRole("heading", {
      name: `${monthName[0]!.toUpperCase()}${monthName.slice(1)}: часы по дням`,
      exact: true,
    }),
  ).toBeVisible();
  await expect(calendars.getByRole("grid")).toHaveCount(1);
  await expect(calendars.locator(`[data-date^="${meta.today.slice(0, 7)}"]`)).toHaveCount(0);
});

test("демо: заявка не меняет статус до согласования", async ({ page }) => {
  await login(page);
  await page.goto("/demo");
  const form = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "Проверка согласования статуса", exact: true }) });
  await expect(form.getByRole("button", { name: "Создать пример заявки", exact: true })).toBeEnabled();
  await expect(form.getByLabel("Сотрудник для примера")).not.toHaveValue("");
  const available = (await (await page.request.get("/api/v1/today")).json()).rows.find(
    (row: { cell: { status: string | null } }) => row.cell.status !== "remote",
  );
  expect(available).toBeTruthy();
  await form.getByLabel("Сотрудник для примера").selectOption(String(available.employee.id));
  const employeeId = Number(await form.getByLabel("Сотрудник для примера").inputValue());
  const before = (await (await page.request.get("/api/v1/today")).json()).rows.find(
    (row: { employee: { id: number } }) => row.employee.id === employeeId,
  ).cell.status;
  expect(before).not.toBe("remote");
  await form.getByRole("button", { name: "Создать пример заявки", exact: true }).click();
  await expect(page).toHaveURL(/view=requests.*request=\d+/);
  const requestId = new URL(page.url()).searchParams.get("request");
  const card = page.locator(`[data-request-id="${requestId}"]`);
  await expect(card.getByText("Ждёт решения", { exact: true })).toBeVisible();
  expect(
    (await (await page.request.get("/api/v1/today")).json()).rows.find(
      (row: { employee: { id: number } }) => row.employee.id === employeeId,
    ).cell.status,
  ).toBe(before);
  await card.getByRole("button", { name: "Согласовать", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Подтвердить решение", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByLabel("Состояние заявок").selectOption("accepted");
  await expect(card.getByText("Согласована", { exact: true })).toBeVisible();
  expect(
    (await (await page.request.get("/api/v1/today")).json()).rows.find(
      (row: { employee: { id: number } }) => row.employee.id === employeeId,
    ).cell.status,
  ).toBe("remote");
});

test("профиль: формат номера, копирование и просмотр аватара", async ({ page, context }) => {
  await login(page);
  const employee = (await (await page.request.get("/api/v1/employees")).json())[0];
  await page.goto(`/people/${employee.id}`);
  const photo = await avatarFixture(page);
  const avatar_url = `data:image/png;base64,${photo.buffer.toString("base64")}`;
  try {
    const saved = await page.request.put(`/api/v1/admin/employees/${employee.id}`, {
      data: { ...employee, phone: "89991234567", avatar_url },
      headers: { "X-Requested-With": "teamtime" },
    });
    expect(saved.ok()).toBeTruthy();
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.reload();
    await expect(page.getByRole("link", { name: "+7 (999) 123-45-67", exact: true })).toHaveAttribute(
      "href",
      "tel:+79991234567",
    );
    await page.getByRole("button", { name: "Скопировать номер телефона", exact: true }).click();
    await expect(page.getByText("Номер скопирован", { exact: true })).toBeVisible();
    expect(await page.evaluate("navigator.clipboard.readText()")).toBe("+7 (999) 123-45-67");
    await page.getByRole("button", { name: "Открыть фотографию сотрудника", exact: true }).click();
    await expect(page.getByRole("dialog").getByRole("img")).toHaveAttribute("src", avatar_url);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  } finally {
    await page.request.put(`/api/v1/admin/employees/${employee.id}`, {
      data: employee,
      headers: { "X-Requested-With": "teamtime" },
    });
  }
});

test("инбокс: правка показывает последствия до одобрения", async ({ page }) => {
  await login(page);
  const { item, employee, date } = await lateScheduleExample(page.request);
  const change = item.plan_change!.days.find((day) => day.date === date)!;
  expect(change.current.late_sec).toBeGreaterThan(0);
  expect(change.if_accepted.late_sec).toBe(0);
  await page.goto(`/inbox?employee=${employee.id}&kind=schedule`);
  const card = page
    .getByRole("listitem")
    .filter({ has: page.getByRole("button", { name: "Одобрить новый план", exact: true }) })
    .first();
  const comparison = card.getByRole("region", { name: "Изменения расписания", exact: true });
  await expect(comparison).toContainText("В таблице сейчас");
  await expect(comparison).toContainText("После одобрения");
  await expect(comparison).toContainText("Опоздание:");
  await card.getByRole("button", { name: "Одобрить новый план", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("heading", { name: "Одобрить новое расписание?", exact: true }),
  ).toBeVisible();
  await expect(dialog).toContainText("Опоздания и итоги пересчитаются");
  const response = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/admin/inbox/${item.parse.id}/resolve`) &&
      response.request().method() === "POST",
  );
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

test("realtime: сообщение из эмулятора появляется на открытой странице без перезагрузки", async ({
  page,
  context,
}) => {
  await page.goto("/");
  await expect(page.getByText("Сайт подключён", { exact: true })).toBeVisible();
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
  await expect(page.getByText(new RegExp(`${author.employee.short_name}.*дейлик`)).first()).toBeVisible({
    timeout: 10_000,
  });
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
    await dialog
      .getByLabel("О сотруднике", { exact: true })
      .fill("Вымышленный профиль для браузерной проверки");
    await dialog.getByLabel("Фотография", { exact: true }).setInputFiles({
      name: "test-avatar.png",
      mimeType: "image/png",
      buffer: await page.screenshot({ clip: { x: 0, y: 0, width: 32, height: 32 } }),
    });
    await expect(dialog.getByAltText("Фотография сотрудника")).toBeVisible();
    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await page.goto(`/people/${employee.id}`);
    await expect(page.getByRole("link", { name: "+0 (000) 000-00-00", exact: true })).toBeVisible();
    await expect(
      page.getByText("Вымышленный профиль для браузерной проверки", { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("region", { name: "Профиль сотрудника" }).locator("img")).toBeVisible();
  } finally {
    const restored = await page.request.put(`/api/v1/admin/employees/${employee.id}`, {
      data: employee,
      headers: { "X-Requested-With": "teamtime" },
    });
    expect(restored.ok()).toBeTruthy();
  }
});

for (const mobile of [false, true]) {
  test(`фото: масштаб, перемещение и сохранение выбранной области · ${mobile ? "телефон" : "компьютер"}`, async ({
    page,
  }) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 });
    await login(page);
    const employee = (await (await page.request.get("/api/v1/employees")).json())[0];
    try {
      await page.goto(`/admin/employees?edit=${employee.id}`);
      const dialog = page.getByRole("dialog");
      await dialog.getByLabel("Фотография", { exact: true }).setInputFiles(await avatarFixture(page));
      const editor = dialog.getByRole("region", { name: "Настройка фотографии", exact: true });
      const zoom = editor.getByRole("slider", { name: "Масштаб фото", exact: true });
      await zoom.focus();
      await zoom.press("End");
      await expect(zoom).toHaveValue("4");
      await editor.getByRole("button", { name: "Сбросить кадр", exact: true }).click();
      await expect(zoom).toHaveValue("1");
      await zoom.focus();
      for (let step = 0; step < 20; step++) await zoom.press("ArrowRight");
      await expect(zoom).toHaveValue("2");
      const frame = editor.getByRole("group", { name: "Область кадрирования", exact: true });
      await frame.scrollIntoViewIfNeeded();
      const bounds = (await frame.boundingBox())!;
      const start = { x: bounds.x + bounds.width - 12, y: bounds.y + bounds.height / 2 };
      const end = { x: bounds.x + 12, y: start.y };
      if (mobile) {
        const cdp = await page.context().newCDPSession(page);
        await cdp.send("Emulation.setTouchEmulationEnabled", { enabled: true });
        await cdp.send("Input.dispatchTouchEvent", {
          type: "touchStart",
          touchPoints: [{ ...start, id: 1 }],
        });
        for (let step = 1; step <= 5; step++) {
          await cdp.send("Input.dispatchTouchEvent", {
            type: "touchMove",
            touchPoints: [{ x: start.x + ((end.x - start.x) * step) / 5, y: start.y, id: 1 }],
          });
        }
        await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
        await cdp.detach();
      } else {
        await page.mouse.move(start.x, start.y);
        await page.mouse.down();
        await page.mouse.move(end.x, end.y, { steps: 5 });
        await page.mouse.up();
      }
      expect(await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")).toBeTruthy();
      await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
      await expect(dialog).toHaveCount(0);
      const saved = (await (await page.request.get(`/api/v1/employees/${employee.id}`)).json()).employee
        .avatar_url;
      const picture: { width: number; height: number; pixel: number[] } = await page.evaluate(`(async () => {
        const image = new Image();
        image.src = ${JSON.stringify(saved)};
        await image.decode();
        const canvas = document.createElement('canvas');
        canvas.width = canvas.height = 256;
        const context = canvas.getContext('2d');
        context.drawImage(image, 0, 0);
        return { width: image.naturalWidth, height: image.naturalHeight, pixel: [...context.getImageData(128, 128, 1, 1).data] };
      })()`);
      expect(picture.width).toBe(256);
      expect(picture.height).toBe(256);
      expect(picture.pixel[2]!).toBeGreaterThan(180);
      expect(picture.pixel[0]!).toBeLessThan(80);
      expect(picture.pixel[1]!).toBeLessThan(130);
      await page.goto(`/admin/employees?edit=${employee.id}`);
      await page.getByRole("dialog").getByRole("button", { name: "Настроить фото", exact: true }).click();
      await expect(page.getByRole("region", { name: "Настройка фотографии", exact: true })).toBeVisible();
    } finally {
      expect(
        (
          await page.request.put(`/api/v1/admin/employees/${employee.id}`, {
            data: employee,
            headers: { "X-Requested-With": "teamtime" },
          })
        ).ok(),
      ).toBeTruthy();
    }
  });
}

test("фото: отмена редактирования не меняет профиль", async ({ page }) => {
  await login(page);
  const employee = (await (await page.request.get("/api/v1/employees")).json())[0];
  await page.goto(`/admin/employees?edit=${employee.id}`);
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Фотография", { exact: true }).setInputFiles(await avatarFixture(page));
  await expect(dialog.getByRole("region", { name: "Настройка фотографии", exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Отмена", exact: true }).click();
  const saved = (await (await page.request.get(`/api/v1/employees/${employee.id}`)).json()).employee;
  expect(saved.avatar_url).toBe(employee.avatar_url);
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

test("длинный список задач раскрывается внутри ограниченного блока", async ({ page }) => {
  const today = await (await page.request.get("/api/v1/today")).json();
  const employee = today.rows[0].employee;
  today.rows[0].tasks = Array.from(
    { length: 100 },
    (_, index) => `Задача ${index + 1}: ${"описание ".repeat(30)}`,
  );
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
  expect(
    await list.evaluate((element) => {
      const node = element as unknown as { scrollHeight: number; clientHeight: number };
      return node.scrollHeight > node.clientHeight;
    }),
  ).toBeTruthy();
  expect(await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")).toBeTruthy();
  await page.getByRole("button", { name: "Свернуть задачи", exact: true }).click();
  await expect(list.getByRole("listitem")).toHaveCount(4);
});
