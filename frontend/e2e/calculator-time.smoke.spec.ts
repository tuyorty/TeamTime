import { expect, test } from "@playwright/test";

import { calculatorExample, installCalculatorExample, openCalculator } from "./calculator-fixtures";

for (const mobile of [false, true]) {
  test.describe(`калькулятор: время без AM/PM · ${mobile ? "телефон" : "компьютер"}`, () => {
    // Английская локаль воспроизводит окружение с нативным 12-часовым выбором времени.
    test.use({
      locale: "en-US",
      viewport: mobile ? { width: 390, height: 844 } : { width: 1280, height: 900 },
      isMobile: mobile,
      hasTouch: mobile,
    });

    test("24-часовой ввод, короткая запись и проверка неверного времени", async ({ page }) => {
      const example = await calculatorExample(page.request);
      await installCalculatorExample(page, example);
      await page.goto(example.url);
      const dialog = await openCalculator(page);
      const start = dialog.getByLabel("Начало интервала 1", { exact: true });
      const end = dialog.getByLabel("Конец интервала 1", { exact: true });
      const result = dialog.getByLabel("Текст для дейлика", { exact: true });
      await expect(dialog.locator('input[type="time"]')).toHaveCount(0);
      for (const field of [start, end]) {
        await expect(field).toHaveAttribute("type", "text");
        await expect(field).toHaveAttribute("inputmode", "numeric");
        await expect(field).toHaveAttribute("placeholder", "ЧЧ:ММ");
      }

      await start.pressSequentially("19:50");
      await end.pressSequentially("23:40");
      await end.blur();
      await expect(start).toHaveValue("19:50");
      await expect(end).toHaveValue("23:40");
      await expect(dialog.getByText("3:50", { exact: true }).first()).toBeVisible();
      await expect(result).toHaveText("19:50 - 23:40\nЭффективность: 100%");

      // Цифровая клавиатура телефона не обязана иметь двоеточие.
      await start.fill("930");
      await end.fill("1820");
      await end.blur();
      await expect(start).toHaveValue("09:30");
      await expect(end).toHaveValue("18:20");
      await expect(dialog.getByText("8:50", { exact: true }).first()).toBeVisible();
      await expect(result).toHaveText("09:30 - 18:20\nЭффективность: 100%");

      await start.fill("9");
      await start.blur();
      await expect(start).toHaveValue("09:00");
      await expect(result).toHaveText("09:00 - 18:20\nЭффективность: 100%");

      for (const invalid of ["25:00", "12:70", "11:30 PM"]) {
        await end.fill(invalid);
        await end.blur();
        await expect(end).toHaveValue(invalid);
        await expect(dialog.getByRole("alert")).toContainText(/время|интервал/i);
        await expect(dialog.getByRole("button", { name: "Скопировать для дейлика", exact: true })).toHaveCount(0);
      }
      expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
    });
  });
}
