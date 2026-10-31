import { expect, test, type Page } from "@playwright/test";
import { tvFixture, tvMeta } from "./tv-fixtures";

async function fixtures(page: Page, total?: number) {
  const data = tvFixture();
  if (total) data.rows = Array.from({ length: total }, (_, i) => ({
    ...data.rows[i % data.rows.length]!,
    employee: { ...data.rows[i % data.rows.length]!.employee, id: i + 1, short_name: `Сотрудник ${i + 1}` },
  }));
  await page.route("**/api/v1/meta", (route) => route.fulfill({ json: tvMeta }));
  await page.route("**/api/v1/today**", (route) => route.fulfill({ json: {
    ...data, date: new URL(route.request().url()).searchParams.get("day") ?? data.date,
  } }));
  return data;
}

test("ТВ: вся команда и все состояния помещаются в Full HD без элементов управления", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  const data = await fixtures(page);
  await page.goto("/tv");
  await expect(page.getByRole("heading", { name: /Сегодня/ })).toBeVisible();
  await expect(page.getByRole("article")).toHaveCount(9);
  await expect(page.getByRole("navigation")).toHaveCount(0);
  await expect(page.getByRole("button")).toHaveCount(0);
  await expect(page.getByRole("link")).toHaveCount(0);
  await expect(page.getByText("Отпуск", { exact: true })).toBeVisible();
  await expect(page.getByRole("article").getByText("Выходной", { exact: true })).toBeVisible();
  await expect(page.getByText("Время не указано", { exact: true })).toBeVisible();
  await expect(page.getByText("15:00", { exact: true }).last()).toBeVisible();
  const numbers = await page.locator(".tv-stat-value").allTextContents();
  expect(numbers.reduce((sum, value) => sum + Number(value), 0)).toBe(data.rows.length);
  expect(await page.evaluate("document.documentElement.scrollHeight <= innerHeight && document.documentElement.scrollWidth <= innerWidth")).toBe(true);
  expect(await page.locator(".tv-person, .tv-upcoming").evaluateAll((elements) => elements.every((element) => element.scrollHeight <= element.clientHeight + 2))).toBe(true);
  await expect(page).toHaveTitle("xTime · Команда сегодня");
});

test("ТВ: большая команда автоматически меняет страницы, никого не теряя", async ({ page }) => {
  await page.clock.install();
  await page.setViewportSize({ width: 1280, height: 720 });
  await fixtures(page, 14);
  await page.goto("/tv");
  await expect(page.getByRole("article")).toHaveCount(6);
  const seen = new Set(await page.locator(".tv-person h3").allTextContents());
  for (let step = 0; step < 2; step++) {
    await page.clock.fastForward(15_100);
    for (const name of await page.locator(".tv-person h3").allTextContents()) seen.add(name);
  }
  expect(seen.size).toBe(14);
  expect(await page.evaluate("document.documentElement.scrollHeight <= innerHeight")).toBe(true);
});

test("ТВ: при потере API остаются последние данные с явной отметкой, затем связь восстанавливается", async ({ page }) => {
  await page.clock.install();
  await fixtures(page);
  await page.goto("/tv");
  await expect(page.getByRole("article").first()).toBeVisible();
  await page.route("**/api/v1/today", (route) => route.fulfill({ status: 503, json: { detail: "Недоступно" } }));
  await page.clock.fastForward(95_000);
  await expect(page.getByText("Нет свежих данных · обновлено в 14:30 · Демо", { exact: true })).toBeVisible();
  await expect(page.getByRole("article").first()).toBeVisible();
  await page.unroute("**/api/v1/today");
  await page.clock.fastForward(35_000);
  await expect(page.getByText(/Нет свежих данных/)).toHaveCount(0);
});

test("ТВ: после полуночи показывает новый день и запрашивает следующие сутки", async ({ page }) => {
  await page.clock.install();
  let requests = 0;
  const tomorrowDates: string[] = [];
  await page.route("**/api/v1/meta", (route) => route.fulfill({ json: {
    ...tvMeta, demo: false, now: "2026-10-31T23:59:45+05:00", today: "2026-10-31",
  } }));
  await page.route("**/api/v1/today**", (route) => {
    const day = new URL(route.request().url()).searchParams.get("day");
    if (day) tomorrowDates.push(day);
    return route.fulfill({ json: tvFixture(day ?? (requests++ === 0 ? "2026-10-31" : "2026-11-01")) });
  });
  await page.goto("/tv");
  await expect(page.getByRole("heading", { name: "Сегодня · 31 октября", exact: true })).toBeVisible();
  await page.clock.fastForward(35_000);
  await expect(page.getByRole("heading", { name: "Сегодня · 1 ноября", exact: true })).toBeVisible();
  await expect(page.getByLabel("Текущее время команды")).toHaveText(/^00:00:\d{2}$/);
  await expect.poll(() => tomorrowDates).toContain("2026-11-02");
});

test("ТВ: несколько интервалов и длинные подписи не обрезают строки", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.route("**/api/v1/meta", (route) => route.fulfill({ json: tvMeta }));
  const data = tvFixture();
  data.rows[0]!.cell.plan!.intervals = [[32400, 43200], [46800, 64800]];
  data.rows[0]!.employee.position = "Очень длинное название направления работы сотрудника";
  await page.route("**/api/v1/today**", (route) => route.fulfill({ json: data }));
  await page.goto("/tv");
  await expect(page.getByText("2 интервала", { exact: true })).toBeVisible();
  expect(await page.locator(".tv-person").evaluateAll((elements) => elements.every((element) => element.scrollHeight <= element.clientHeight + 2))).toBe(true);
});

test("ТВ: выходной имеет приоритет над отметкой об удалёнке", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  const data = tvFixture();
  data.rows[6]!.cell.status = "remote";
  await page.route("**/api/v1/meta", (route) => route.fulfill({ json: tvMeta }));
  await page.route("**/api/v1/today**", (route) => route.fulfill({ json: data }));
  await page.goto("/tv");
  const employee = page.getByRole("article", { name: "Белов К.Н.: Выходной" });
  await expect(employee).toBeVisible();
  await expect(employee.getByText("Не работает сегодня", { exact: true })).toBeVisible();
  await expect(employee.getByText(/Удалённо/)).toHaveCount(0);
});

test("ТВ: секунды идут без перезагрузки и не сбрасываются после обновления демо-данных", async ({ page }) => {
  const start = new Date("2026-10-23T09:30:00Z");
  await page.clock.install({ time: start });
  await fixtures(page);
  let metaRequests = 0;
  await page.route("**/api/v1/meta", (route) => {
    metaRequests++;
    return route.fulfill({ json: tvMeta });
  });
  await page.goto("/tv");
  const time = page.getByLabel("Текущее время команды");
  await expect(time).toHaveText(/^14:30:\d{2}$/);
  await page.clock.pauseAt(new Date(start.getTime() + 10_000));
  const initial = Date.parse((await time.getAttribute("datetime"))!);
  const before = await time.boundingBox();
  await page.clock.runFor(1000);
  await expect.poll(async () => Date.parse((await time.getAttribute("datetime"))!)).toBe(initial + 1000);
  await page.clock.fastForward(60_000);
  await expect.poll(() => metaRequests).toBeGreaterThan(1);
  await expect(time).toHaveText(/^14:31:\d{2}$/);
  await expect.poll(async () => Date.parse((await time.getAttribute("datetime"))!)).toBe(initial + 61_000);
  const after = await time.boundingBox();
  expect(after!.width).toBeCloseTo(before!.width, 0);
  expect(after!.x).toBeCloseTo(before!.x, 0);
});

for (const theme of ["light", "dark"] as const) {
  test(`ТВ: использует выбранную тему приложения — ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme === "light" ? "dark" : "light" });
    await page.addInitScript(`localStorage.setItem("tt-theme", "${theme}")`);
    await fixtures(page);
    await page.goto("/tv");
    await expect(page.getByRole("article").first()).toBeVisible();
    await expect(page.locator("html")).toHaveClass(theme === "dark" ? "dark" : "");
    const background = await page.evaluate<string>("getComputedStyle(document.body).backgroundColor");
    await expect(page.getByRole("main")).toHaveCSS("background-color", background);
    await expect(page.getByRole("main")).toHaveCSS("background-image", "none");
  });
}
