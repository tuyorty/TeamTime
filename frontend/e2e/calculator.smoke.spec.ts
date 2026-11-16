import { expect, test } from "@playwright/test";

import type { Today } from "../src/api/types";
import { calculatorExample, installCalculatorExample, openCalculator } from "./calculator-fixtures";

test("калькулятор: перерывы, округление для дейлика и сохранение ввода между вкладками", async ({ page, context }) => {
  const example = await calculatorExample(page.request);
  await installCalculatorExample(page, example);
  const mutations: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/") && !["GET", "HEAD", "OPTIONS"].includes(request.method())) {
      mutations.push(`${request.method()} ${new URL(request.url()).pathname}`);
    }
  });
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto(example.url);
  const dialog = await openCalculator(page);
  await expect(dialog.getByLabel("Начало интервала 1", { exact: true })).toHaveValue("");
  await dialog.getByRole("button", { name: "Пример", exact: true }).click();
  await expect(dialog.getByTestId("daily-efficiency")).toHaveText("91%");
  await expect(dialog.getByText("11:30", { exact: true }).first()).toBeVisible();
  await expect(dialog.getByText("10:30", { exact: true }).first()).toBeVisible();
  await dialog.getByRole("button", { name: "Скопировать для дейлика", exact: true }).click();
  const copied: string = await page.evaluate("navigator.clipboard.readText()");
  expect(copied).toMatch(/10:20\s*[-–]\s*18:00/);
  expect(copied).toMatch(/19:50\s*[-–]\s*23:40/);
  expect(copied).toMatch(/Эффективность:\s*91%/);
  // В офисной сети страница открывается по HTTP: проверяем запасное копирование внутри диалога.
  await page.evaluate(`(() => {
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined });
    document.execCommand = (command) => {
      const input = document.activeElement;
      if (command !== "copy" || !(input instanceof HTMLTextAreaElement)) return false;
      document.documentElement.dataset.calculatorCopy = input.value.slice(input.selectionStart, input.selectionEnd);
      return true;
    };
  })()`);
  await dialog.getByRole("button", { name: "Скопировать для дейлика", exact: true }).click();
  await expect.poll(() => page.evaluate("document.documentElement.dataset.calculatorCopy")).toBe(copied.replace(/\r\n/g, "\n"));
  await dialog.getByRole("tab", { name: "Доход за месяц", exact: true }).click();
  await dialog.getByRole("tab", { name: "Эффективность дня", exact: true }).click();
  await expect(dialog.getByLabel("Начало интервала 1", { exact: true })).toHaveValue("10:20");
  await expect(dialog.getByLabel("Конец интервала 2", { exact: true })).toHaveValue("23:40");
  await expect(dialog.getByLabel("Перерывы внутри интервалов, мин", { exact: true })).toHaveValue("60");
  expect(mutations).toEqual([]);
});

test("калькулятор: пересекающиеся интервалы и слишком длинный перерыв нельзя скопировать", async ({ page }) => {
  const example = await calculatorExample(page.request);
  await page.goto(example.url);
  const dialog = await openCalculator(page);
  await dialog.getByLabel("Начало интервала 1", { exact: true }).fill("10:00");
  await dialog.getByLabel("Конец интервала 1", { exact: true }).fill("12:00");
  await dialog.getByLabel("Перерывы внутри интервалов, мин", { exact: true }).fill("180");
  await expect(dialog.getByRole("button", { name: "Скопировать для дейлика", exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("alert")).toContainText(/перерыв/i);
  await dialog.getByLabel("Перерывы внутри интервалов, мин", { exact: true }).fill("0");
  await dialog.getByRole("button", { name: "Добавить интервал", exact: true }).click();
  await dialog.getByLabel("Начало интервала 2", { exact: true }).fill("11:00");
  await dialog.getByLabel("Конец интервала 2", { exact: true }).fill("13:00");
  await expect(dialog.getByRole("alert")).toContainText(/пересека/i);
  await expect(dialog.getByRole("button", { name: "Скопировать для дейлика", exact: true })).toHaveCount(0);
});

test("калькулятор: ночные интервалы из дейлика сохраняют длительность и время следующего дня", async ({ page }) => {
  const example = await calculatorExample(page.request);
  const today: Today = await (await page.request.get("/api/v1/today")).json();
  const row = today.rows.find((item) => item.employee.id === example.employee.id)!;
  expect(row).toBeDefined();
  row.cell.fact = {
    start: 22 * 3600,
    end: 29 * 3600,
    intervals: [[22 * 3600, 26 * 3600], [27 * 3600, 29 * 3600]],
    worked_sec: 6 * 3600,
    efficiency: 100,
    result_sec: 6 * 3600,
    tasks: [],
    edited: false,
    sent_at: null,
    source: "demo",
  };
  await page.route("**/api/v1/today", (route) => route.fulfill({ json: today }));
  await page.goto(example.url);
  const dialog = await openCalculator(page);
  await dialog.getByRole("button", { name: "Интервалы из дейлика", exact: true }).click();
  await expect(dialog.getByLabel("Начало интервала 1", { exact: true })).toHaveValue("22:00");
  await expect(dialog.getByLabel("Конец интервала 1", { exact: true })).toHaveValue("02:00");
  await expect(dialog.getByLabel("Начало интервала 2", { exact: true })).toHaveValue("03:00");
  await expect(dialog.getByLabel("Конец интервала 2", { exact: true })).toHaveValue("05:00");
  await expect(dialog.getByTestId("daily-efficiency")).toHaveText("100%");
  await expect(dialog.getByRole("alert")).toHaveCount(0);
  await expect(dialog.getByText("6:00", { exact: true }).first()).toBeVisible();
  await expect(dialog.getByLabel("Текст для дейлика", { exact: true })).toContainText("22:00 - 02:00 + 03:00 - 05:00");
});

test("калькулятор: месячная цель учитывает оклад, премии, штраф и уже отработанные часы", async ({ page }) => {
  const example = await calculatorExample(page.request);
  await installCalculatorExample(page, example);
  const mutations: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/") && !["GET", "HEAD", "OPTIONS"].includes(request.method())) {
      mutations.push(`${request.method()} ${new URL(request.url()).pathname}`);
    }
  });
  await page.goto(example.url);
  const dialog = await openCalculator(page);
  const financeResponse = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/finances/2026/10");
  await dialog.getByRole("tab", { name: "Доход за месяц", exact: true }).click();
  await financeResponse;
  await dialog.getByLabel("Хочу получить, ₽", { exact: true }).fill("102000");
  await dialog.getByLabel("Эффективность оставшихся часов, %", { exact: true }).fill("80");
  await expect(dialog.getByTestId("monthly-needed-actual")).toHaveText("131:15");
  await expect(dialog.getByTestId("monthly-needed-effective")).toHaveText("105:00");
  await dialog.getByText("Условия расчёта", { exact: true }).click();
  await expect(dialog.getByLabel("Ставка, ₽/ч", { exact: true })).toHaveValue("500");
  await expect(dialog.getByLabel("Норма для оклада, ч:мм", { exact: true })).toHaveValue("160:00");
  await expect(dialog.getByLabel("Проектные премии, ₽", { exact: true })).toHaveValue("2000");
  await expect(dialog.getByLabel("Штрафное время, ч:мм", { exact: true })).toHaveValue("5:00");
  await expect(dialog.getByLabel("Уже учтено эффективных часов, ч:мм", { exact: true })).toHaveValue("100:00");
  await dialog.getByRole("button", { name: "Расчёт по часам", exact: true }).click();
  await dialog.getByLabel("Фактические часы за месяц, ч:мм", { exact: true }).fill("210:00");
  await expect(dialog.getByLabel("Эффективные часы за месяц, ч:мм", { exact: true })).toHaveValue("168:00");
  await expect(dialog.getByTestId("monthly-total")).toContainText(/83\s?500/);
  expect(mutations).toEqual([]);
});

test("калькулятор: ошибка загрузки финансов не подменяется нулевыми начислениями", async ({ page }) => {
  const example = await calculatorExample(page.request);
  await installCalculatorExample(page, example);
  await page.route("**/api/v1/finances/2026/10", (route) => route.fulfill({ status: 503, json: { detail: "Тестовая недоступность" } }));
  await page.goto(example.url);
  const dialog = await openCalculator(page);
  await dialog.getByRole("tab", { name: "Доход за месяц", exact: true }).click();
  await expect(dialog.getByRole("button", { name: /повторить/i })).toBeVisible();
  await expect(dialog.getByTestId("monthly-needed-actual")).toHaveCount(0);
  await dialog.getByRole("tab", { name: "Эффективность дня", exact: true }).click();
  await dialog.getByRole("button", { name: "Пример", exact: true }).click();
  await expect(dialog.getByTestId("daily-efficiency")).toHaveText("91%");
});

test("калькулятор: процент из дейлика применяется к месяцу при первом и повторном переносе", async ({ page }) => {
  const example = await calculatorExample(page.request);
  await installCalculatorExample(page, example);
  await page.goto(example.url);
  const dialog = await openCalculator(page);
  await dialog.getByRole("button", { name: "Пример", exact: true }).click();
  await dialog.getByRole("button", { name: "К доходу с этой эффективностью", exact: true }).click();
  await expect(dialog.getByLabel("Эффективность оставшихся часов, %", { exact: true })).toHaveValue("91");
  await dialog.getByRole("button", { name: "Расчёт по часам", exact: true }).click();
  await expect(dialog.getByLabel("Фактические часы за месяц, ч:мм", { exact: true })).toHaveValue("125:00");
  await expect(dialog.getByLabel("Эффективные часы за месяц, ч:мм", { exact: true })).toHaveValue("113:45");
  await dialog.getByLabel("Эффективность за месяц, %", { exact: true }).fill("80");
  await expect(dialog.getByLabel("Эффективные часы за месяц, ч:мм", { exact: true })).toHaveValue("100:00");
  await dialog.getByRole("tab", { name: "Эффективность дня", exact: true }).click();
  await dialog.getByRole("button", { name: "К доходу с этой эффективностью", exact: true }).click();
  await expect(dialog.getByLabel("Эффективность за месяц, %", { exact: true })).toHaveValue("91");
  await expect(dialog.getByLabel("Эффективные часы за месяц, ч:мм", { exact: true })).toHaveValue("113:45");
});

test("калькулятор: ошибка фонового обновления не стирает введённый сценарий", async ({ page }) => {
  const example = await calculatorExample(page.request);
  await installCalculatorExample(page, example);
  await page.clock.install();
  await page.goto(example.url);
  const dialog = await openCalculator(page);
  await dialog.getByRole("tab", { name: "Доход за месяц", exact: true }).click();
  await dialog.getByLabel("Хочу получить, ₽", { exact: true }).fill("102000");
  await dialog.getByLabel("Эффективность оставшихся часов, %", { exact: true }).fill("80");
  await dialog.getByText("Условия расчёта", { exact: true }).click();
  await dialog.getByLabel("Ставка, ₽/ч", { exact: true }).fill("650");
  const before = await dialog.getByTestId("monthly-needed-actual").textContent();
  await page.route("**/api/v1/finances/2026/10", (route) => route.fulfill({ status: 503, json: { detail: "Тестовая недоступность" } }));
  // Возвращение к устаревшим данным запускает стандартное фоновое обновление TanStack Query.
  await page.clock.fastForward(16_000);
  const failure = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/finances/2026/10" && response.status() === 503);
  await page.evaluate("document.dispatchEvent(new Event('visibilitychange', { bubbles: true }))");
  await failure;
  await expect(dialog.getByLabel("Хочу получить, ₽", { exact: true })).toHaveValue("102000");
  await expect(dialog.getByLabel("Ставка, ₽/ч", { exact: true })).toHaveValue("650");
  await expect(dialog.getByTestId("monthly-needed-actual")).toHaveText(before!);
});

test("калькулятор: на телефоне оба режима помещаются по ширине и диалог закрывается", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const example = await calculatorExample(page.request);
  await installCalculatorExample(page, example);
  await page.goto(example.url);
  const dialog = await openCalculator(page);
  await dialog.getByRole("button", { name: "Пример", exact: true }).click();
  await expect(dialog.getByTestId("daily-efficiency")).toHaveText("91%");
  for (const tab of ["Эффективность дня", "Доход за месяц"]) {
    await dialog.getByRole("tab", { name: tab, exact: true }).click();
    if (tab === "Доход за месяц") await expect(dialog.getByLabel("Хочу получить, ₽", { exact: true })).toBeVisible();
    expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
    expect(await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")).toBe(true);
  }
  await dialog.getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect(dialog).toBeHidden();
});
