import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import path from "node:path";

import { expect, test, type Browser, type Page } from "@playwright/test";
import { avatarFixture, lateScheduleExample } from "./fixtures";

/**
 * Скриншоты и GIF для README на демо-данных:
 *   DEMO=1 DEMO_NOW=2026-10-23T14:30:00+05:00 docker compose up -d
 *   E2E_BASE_URL=http://localhost:8080 npm run screenshots
 */
const OUT = path.resolve(import.meta.dirname, "../../docs/screenshots");
mkdirSync(OUT, { recursive: true });

type Theme = "light" | "dark";

async function shot(
  browser: Browser,
  url: string,
  name: string,
  theme: Theme,
  mobile = false,
  prepare?: (p: Page) => Promise<void>,
) {
  const ctx = await browser.newContext({
    viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    deviceScaleFactor: mobile ? 2 : 1,
    colorScheme: theme,
    locale: "ru-RU",
    reducedMotion: "reduce",
  });
  const page = await ctx.newPage();
  await page.goto(url, { waitUntil: "load" });
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(700);
  await page.evaluate("window.scrollTo(0, 0)");
  if (prepare) await prepare(page);
  await page.screenshot({ path: path.join(OUT, `${name}-${theme}.png`) });
  await ctx.close();
}

test.describe.configure({ mode: "serial" });

for (const theme of ["light", "dark"] as const) {
  test(`десктоп, ${theme}`, async ({ browser }) => {
    test.setTimeout(150_000);
    await shot(browser, "/week/2026/43", "week", theme);
    await shot(browser, "/week/2026/43", "week-facts", theme, false, async (p) => {
      await p.getByRole("button", { name: "Факты недели", exact: true }).click();
    });
    await shot(browser, "/month/2026/9", "month-facts", theme, false, async (p) => {
      await p.getByRole("button", { name: "Факты месяца", exact: true }).click();
    });
    await shot(browser, "/", "today", theme);
    await shot(browser, "/?day=tomorrow", "tomorrow", theme);
    await shot(browser, "/plans/2026/43", "plans", theme);

    await shot(browser, "/admin/system", "system", theme, false, async (p) => {
      await p.request.post("/api/v1/auth/login", { data: { password: "demo" } });
      await p.reload();
      await p.getByRole("heading", { name: "Готовность личных напоминаний", exact: true }).waitFor();
      await p.evaluate("window.scrollTo({top: 0, left: 0, behavior: 'instant'})");
    });
    await shot(browser, "/inbox?view=requests", "status-requests", theme, false, async (p) => {
      await p.request.post("/api/v1/auth/login", { data: { password: "demo" } });
      await p.reload();
      await p.getByRole("button", { name: "Согласовать", exact: true }).first().waitFor();
      await p.evaluate("window.scrollTo({top: 0, left: 0, behavior: 'instant'})");
    });
    await shot(browser, "/?view=summary&date=2026-10-22", "day-summary", theme);
    await shot(browser, "/month/2026/9?tab=late", "month-late", theme, false, async (p) => {
      await p.getByRole("heading", { name: "Шкала штрафа" }).scrollIntoViewIfNeeded();
      await p.mouse.wheel(0, 380);
      await p.waitForTimeout(300);
    });
    await shot(browser, "/month/2026/9", "month", theme);
    await shot(browser, "/finances/2026/10", "finances", theme);
    await shot(browser, "/finances/2026/10?employee=1", "finance-detail", theme);
    await shot(browser, "/people/2", "employee", theme);
    await shot(browser, "/people/2?period=3m", "employee-period", theme, false, async (p) => {
      await p.evaluate(
        "Array.from(document.querySelectorAll('h2')).find(element => element.textContent === 'Рабочая статистика').scrollIntoView({block: 'start', behavior: 'instant'})",
      );
    });
    await shot(browser, "/admin/employees?edit=2", "avatar-editor", theme, false, prepareAvatarEditor);
    await shot(browser, "/calendar", "calendar", theme);
    await shot(browser, "/week/2026/43?day=2026-10-21&e=1", "day-detail", theme);
  });

  test(`телефон, ${theme}`, async ({ browser }) => {
    test.setTimeout(60_000);
    await shot(browser, "/week/2026/43", "mobile-week", theme, true);
    await shot(browser, "/", "mobile-today", theme, true);
    await shot(browser, "/finances/2026/10", "mobile-finances", theme, true);
    await shot(browser, "/people/2", "mobile-employee", theme, true);
    await shot(browser, "/admin/employees?edit=2", "mobile-avatar-editor", theme, true, prepareAvatarEditor);
    await shot(browser, "/?view=summary&date=2026-10-22", "mobile-day-summary", theme, true);
    await shot(browser, "/week/2026/43", "mobile-week-facts", theme, true, async (p) => {
      await p.getByRole("button", { name: "Факты недели", exact: true }).click();
    });
  });
}

async function prepareAvatarEditor(page: Page) {
  await page.request.post("/api/v1/auth/login", { data: { password: "demo" } });
  await page.reload();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Фотография", { exact: true }).setInputFiles(await avatarFixture(page));
  const zoom = dialog.getByRole("slider", { name: "Масштаб фото", exact: true });
  await zoom.focus();
  for (let step = 0; step < 10; step++) await zoom.press("ArrowRight");
  await dialog.getByRole("region", { name: "Настройка фотографии", exact: true }).scrollIntoViewIfNeeded();
}

test("демо: пример заявки на статус", async ({ browser }) => {
  for (const theme of ["light", "dark"] as const) {
    await shot(browser, "/demo", "status-request-example", theme, false, async (p) => {
      await p.request.post("/api/v1/auth/login", { data: { password: "demo" } });
      await p.reload();
      await expect(p.getByRole("button", { name: "Создать пример заявки", exact: true })).toBeEnabled();
      await p.evaluate("window.scrollTo({top: 0, left: 0, behavior: 'instant'})");
    });
  }
});

test("инбокс: сравнение изменённого плана и подтверждение", async ({ browser, request }) => {
  test.setTimeout(60_000);
  const { employee } = await lateScheduleExample(request);
  for (const theme of ["light", "dark"] as const) {
    await shot(
      browser,
      `/inbox?employee=${employee.id}&kind=schedule`,
      "inbox-changes",
      theme,
      false,
      async (page) => {
        await page.request.post("/api/v1/auth/login", { data: { password: "demo" } });
        await page.reload();
        await page.getByRole("button", { name: "Одобрить новый план", exact: true }).first().click();
      },
    );
  }
});

test("телефон: большой список задач с внутренней прокруткой", async ({ browser }) => {
  await shot(browser, "/", "mobile-tasks", "light", true, async (page) => {
    const today = await (await page.request.get("/api/v1/today")).json();
    const row = today.rows[0];
    row.tasks = [
      "Разобрать новые обращения поддержки",
      "Проверить исправление фильтров расписания на телефоне и большом экране",
      "Подготовить инструкцию для новых сотрудников",
      "Обновить тестовые данные для демонстрации",
      "Обсудить макет личного кабинета с командой",
      "Проверить отчёт за прошлую неделю",
      "Описать порядок ручного исправления дейликов",
      "Провести ревью изменений экспорта",
      "Подготовить задачи следующего спринта",
      "Обновить документацию проекта",
    ];
    await page.route("**/api/v1/today", (route) => route.fulfill({ json: today }));
    await page.reload();
    await page.getByRole("button", { name: `Задачи: ${row.employee.short_name}`, exact: true }).click();
    await page.getByRole("button", { name: "Показать все задачи (10)", exact: true }).click();
    await page
      .getByRole("region", { name: "Задачи выбранного сотрудника", exact: true })
      .scrollIntoViewIfNeeded();
  });
});

test("GIF: дейлик из эмулятора появляется без перезагрузки", async ({ browser }) => {
  const videoDir = path.join(OUT, ".video");
  rmSync(videoDir, { recursive: true, force: true });
  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 760 },
    colorScheme: "light",
    locale: "ru-RU",
    recordVideo: { dir: videoDir, size: { width: 1280, height: 760 } },
  });
  const page = await ctx.newPage();
  const today = await (await page.request.get("/api/v1/today")).json();
  await page.goto(`/?view=summary&date=${today.date}`);
  await page.getByText("Сайт подключён", { exact: true }).waitFor();
  await page.waitForTimeout(1200);
  const identities = await (await page.request.get("/api/v1/identities")).json();
  const waiting = today.rows.find(
    (r: { cell: { fact: unknown; plan: { kind: string } | null } }) =>
      !r.cell.fact && r.cell.plan?.kind === "work",
  );
  const author =
    identities.find((i: { employee: { id: number } | null }) => i.employee?.id === waiting?.employee.id) ??
    identities.find((i: { employee: unknown }) => i.employee);
  const [y, m, d] = today.date.split("-");
  await page.request.post("/api/v1/demo/messages", {
    data: {
      telegram_user_id: author.telegram_user_id,
      topic: "daily",
      text: `${d}.${m}.${y}\n11:10 - 14:00; 15:00 - 19:20\nЭффективность: 85%\n\n- разбор инбокса\n\n#дейли`,
    },
  });
  await page.waitForTimeout(3500);
  const video = page.video();
  await ctx.close();
  const webm = await video!.path();
  const gif = path.join(OUT, "realtime.gif");
  execFileSync("ffmpeg", [
    "-y",
    "-loglevel",
    "error",
    "-i",
    webm,
    "-vf",
    "fps=12,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=4",
    gif,
  ]);
  rmSync(videoDir, { recursive: true, force: true });
});
