import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import path from "node:path";

import { test, type Browser, type Page } from "@playwright/test";

/**
 * Скриншоты и GIF для README на демо-данных:
 *   DEMO=1 DEMO_NOW=2026-10-23T19:40:00+05:00 docker compose up -d
 *   E2E_BASE_URL=http://localhost:8080 npm run screenshots
 */
const OUT = path.resolve(import.meta.dirname, "../../docs/screenshots");
mkdirSync(OUT, { recursive: true });

type Theme = "light" | "dark";

async function shot(browser: Browser, url: string, name: string, theme: Theme, mobile = false, prepare?: (p: Page) => Promise<void>) {
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
  if (prepare) await prepare(page);
  await page.screenshot({ path: path.join(OUT, `${name}-${theme}.png`) });
  await ctx.close();
}

test.describe.configure({ mode: "serial" });

for (const theme of ["light", "dark"] as const) {
  test(`десктоп, ${theme}`, async ({ browser }) => {
    await shot(browser, "/week/2026/43", "week", theme);
    await shot(browser, "/", "today", theme);
    await shot(browser, "/month/2026/9?tab=late", "month-late", theme, false, async (p) => {
      await p.getByRole("heading", { name: "Шкала штрафа" }).scrollIntoViewIfNeeded();
      await p.mouse.wheel(0, 380);
      await p.waitForTimeout(300);
    });
    await shot(browser, "/month/2026/9", "month", theme);
    await shot(browser, "/people/2", "employee", theme);
    await shot(browser, "/calendar", "calendar", theme);
    await shot(browser, "/week/2026/43?day=2026-10-21&e=1", "day-detail", theme);
  });

  test(`телефон, ${theme}`, async ({ browser }) => {
    await shot(browser, "/week/2026/43", "mobile-week", theme, true);
    await shot(browser, "/", "mobile-today", theme, true);
  });
}

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
  await page.goto("/");
  await page.getByText("Онлайн").waitFor();
  await page.waitForTimeout(1200);
  const identities = await (await page.request.get("/api/v1/identities")).json();
  const today = await (await page.request.get("/api/v1/today")).json();
  const waiting = today.rows.find((r: { cell: { fact: unknown; plan: { kind: string } | null } }) => !r.cell.fact && r.cell.plan?.kind === "work");
  const author = identities.find((i: { employee: { id: number } | null }) => i.employee?.id === waiting?.employee.id) ?? identities.find((i: { employee: unknown }) => i.employee);
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
    "-y", "-loglevel", "error", "-i", webm,
    "-vf", "fps=12,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=4",
    gif,
  ]);
  rmSync(videoDir, { recursive: true, force: true });
});
