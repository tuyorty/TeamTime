import { employeeColor } from "./colors";

it("явно выбранный цвет сохраняется и для временного аватара", () => {
  expect(employeeColor("red", 0, false)).toBe("#e34948");
  expect(employeeColor("red", 0, true)).toBe("#e66767");
});

it("автоматическая палитра обычных сотрудников остаётся прежней", () => {
  expect(employeeColor("", 1, false)).toBe("#2a78d6");
  expect(employeeColor("", 2, false)).toBe("#eb6834");
  expect(employeeColor("", 9, true)).toBe("#3987e5");
});

it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY, 0.5])("аватар с ID %s получает запасной цвет в обеих темах", (id) => {
  expect(employeeColor("", id, false)).toBe("#2a78d6");
  expect(employeeColor("", id, true)).toBe("#3987e5");
});

it.each(["unknown", "constructor", "toString", "__proto__"])("неизвестное имя цвета %s не ломает палитру", (color) => {
  expect(employeeColor(color, 2, false)).toBe("#eb6834");
});
