import { expect, test } from "@playwright/test";

import { manualApprovalNote, mockScheduleReview, reviewEmployee, reviewNewText, reviewOldText } from "./schedule-review-fixtures";

test("инбокс: доступны исходные версии, которые не удалось превратить в план", async ({ page }) => {
  const fixture = await mockScheduleReview(page);
  fixture.plans.rows[0]!.versions = fixture.plans.rows[0]!.versions.slice(1);
  fixture.message.parses[0]!.status = "failed";
  fixture.message.parses[0]!.issues = [{ code: "example_parse_error", severity: "error", message: "Не удалось разобрать исходное расписание", line_no: null, line: null }];
  await page.goto("/inbox");
  await page.getByText("Все версии сообщения · 2", { exact: true }).click();
  const source = page.getByRole("region", { name: "История текста сообщения", exact: true });
  await source.getByRole("button", { name: "исходное", exact: true }).click();
  await expect(source.locator("pre > span")).toHaveText(reviewOldText.split("\n"));
  await expect(source.getByText("Не удалось разобрать исходное расписание", { exact: true })).toBeVisible();
});

test("расписания: история доступна без действующего плана, каждый источник соответствует своей версии", async ({ page }) => {
  const fixture = await mockScheduleReview(page);
  await page.goto("/plans/2026/46");
  await expect(page.getByText("Расписаний на эту неделю нет")).toHaveCount(0);
  await page.getByRole("button", { name: `Что менялось: ${reviewEmployee.short_name}` }).click();
  const history = page.getByRole("dialog", { name: `${reviewEmployee.short_name}: версии плана` });
  const sources = history.getByRole("region", { name: "Сообщение этой версии", exact: true });
  await expect(sources).toHaveCount(2);
  await expect(sources.nth(0).locator("pre > span")).toHaveText(reviewNewText.split("\n"));
  await expect(sources.nth(1).locator("pre > span")).toHaveText(reviewOldText.split("\n"));
  await expect(sources.nth(0).getByText("ждёт решения", { exact: true })).toBeVisible();
  await expect(sources.nth(1).getByText("принято администратором", { exact: true })).toBeVisible();
  await expect(sources.nth(1).getByText(/Отправлено:/)).toContainText("8 ноября");
  await expect(sources.nth(1).getByText(/Разобрано:/)).toContainText("12 ноября");
  await expect(history.getByText("Добавлены задачи · 1", { exact: true })).toBeVisible();
  await expect(history.getByText("Убраны задачи · 1", { exact: true })).toBeVisible();
  expect(fixture.unexpected).toEqual([]);
});

test("инбокс: ссылка сразу открывает историю нужного сотрудника", async ({ page }) => {
  await mockScheduleReview(page);
  await page.goto("/inbox");
  await page.getByRole("link", { name: "История расписания и исходные сообщения" }).click();
  await expect(page).toHaveURL(new RegExp(`/plans/2026/46\\?employee=${reviewEmployee.id}$`));
  await expect(page.getByRole("dialog", { name: `${reviewEmployee.short_name}: версии плана` })).toBeVisible();
});

test("инбокс: невыход требует причины и отправляет подтверждённые план и часы", async ({ page }) => {
  const fixture = await mockScheduleReview(page);
  await page.goto("/inbox");
  await page.getByRole("button", { name: "Подтвердить невыход…", exact: true }).click();
  const submit = page.getByRole("button", { name: "Подтвердить невыход", exact: true });
  await expect(submit).toBeDisabled();
  const reason = page.getByLabel("Причина подтверждения", { exact: true });
  await reason.fill("  ");
  await expect(submit).toBeDisabled();
  expect(fixture.saved).toEqual([]);
  await reason.fill("  Проверено: сотрудник не работал в этот день  ");
  await expect(page.getByText(/В опоздания добавится/)).toContainText("8:00");
  await submit.click();
  await expect(page.getByRole("heading", { name: "Невыход подтверждён", exact: true })).toBeVisible();
  expect(fixture.saved).toEqual([{ reason: "Проверено: сотрудник не работал в этот день", expected_plan_id: 301, expected_seconds: 28800 }]);
  expect(fixture.unexpected).toEqual([]);
});

test("инбокс: просмотр без режима администратора не предлагает подтверждать невыход", async ({ page }) => {
  await mockScheduleReview(page, { admin: false });
  await page.goto("/inbox");
  await expect(page.getByRole("region", { name: "Изменения расписания", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Подтвердить невыход/ })).toHaveCount(0);
});

test("инбокс: новая ручная правка объясняет, почему старое одобрение не заменит план", async ({ page }) => {
  const fixture = await mockScheduleReview(page, { manualPlan: true });
  await page.goto("/inbox");
  const comparison = page.getByRole("region", { name: "Изменения расписания", exact: true });
  await expect(comparison.getByText("Версия плана 2", { exact: true })).toBeVisible();
  await expect(comparison.getByText("Выходной", { exact: true })).toBeVisible();
  await expect(comparison.getByText(manualApprovalNote, { exact: true })).toBeVisible();
  expect(fixture.unexpected).toEqual([]);
});
