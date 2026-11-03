import { compareEmployees } from "./employees";

it("русский алфавит учитывает Ё и не зависит от регистра", () => {
  const employees = ["Яковлев Я.Я.", "Жуков Ж.Ж.", "ёлкин Е.Е.", "Егоров Е.Е.", "Баранов К.А."]
    .map((short_name, id) => ({ id, short_name, full_name: short_name }));
  expect(employees.sort(compareEmployees).map((e) => e.short_name))
    .toEqual(["Баранов К.А.", "Егоров Е.Е.", "ёлкин Е.Е.", "Жуков Ж.Ж.", "Яковлев Я.Я."]);
});
