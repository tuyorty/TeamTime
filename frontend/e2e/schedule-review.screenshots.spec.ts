import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { manualApprovalNote, mockScheduleReview, reviewEmployee } from "./schedule-review-fixtures";

const output = path.resolve(import.meta.dirname, "../../docs/screenshots");

for (const theme of ["light", "dark"] as const) {
  test(`расписания: история и подтверждение невыхода, ${theme}`, async ({ browser }) => {
    mkdirSync(output, { recursive: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, colorScheme: theme, locale: "ru-RU", reducedMotion: "reduce" });
    const page = await context.newPage();
    await mockScheduleReview(page);
    await page.goto(`/plans/2026/46?employee=${reviewEmployee.id}`);
    const history = page.getByRole("dialog", { name: `${reviewEmployee.short_name}: версии плана` });
    await expect(history.getByRole("region", { name: "Сообщение этой версии", exact: true })).toHaveCount(2);
    await page.evaluate("document.fonts.ready");
    await page.screenshot({ path: path.join(output, `schedule-history-${theme}.png`), animations: "disabled" });

    await page.goto("/inbox");
    await page.getByRole("button", { name: "Подтвердить невыход…", exact: true }).click();
    await page.getByLabel("Причина подтверждения", { exact: true }).fill("Проверено с сотрудником: в этот день он не работал.");
    await page.getByRole("button", { name: "Подтвердить невыход", exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, `schedule-no-show-${theme}.png`), animations: "disabled", fullPage: true });
    await context.close();
  });

  test(`расписания: приоритет ручной правки, ${theme}`, async ({ browser }) => {
    mkdirSync(output, { recursive: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, colorScheme: theme, locale: "ru-RU", reducedMotion: "reduce" });
    const page = await context.newPage();
    await mockScheduleReview(page, { manualPlan: true });
    await page.goto("/inbox");
    await expect(page.getByText(manualApprovalNote, { exact: true })).toBeVisible();
    await page.evaluate("document.fonts.ready");
    await page.screenshot({ path: path.join(output, `schedule-manual-plan-${theme}.png`), animations: "disabled", fullPage: true });
    await context.close();
  });
}
