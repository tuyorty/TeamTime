import { departmentOf, employeeGroups, inDepartment } from "./departments";
import { compareEmployees } from "./employees";

it("программисты выше лаборатории, внутри отдела — алфавит", () => {
  const people = [
    { id: 1, short_name: "Андреев А.А.", full_name: "Андреев", department: "laboratory" as const },
    { id: 2, short_name: "Яковлев Я.Я.", full_name: "Яковлев", department: "software" as const },
    { id: 3, short_name: "Баранов К.А.", full_name: "Баранов", department: "laboratory" as const },
  ];
  expect(people.sort(compareEmployees).map((p) => p.id)).toEqual([2, 1, 3]);
  const groups = employeeGroups(people.map((employee) => ({ employee })));
  expect(groups.map((group) => [group.label, group.rows.length])).toEqual([["Программисты", 1], ["Лаборатория", 2]]);
  expect(inDepartment(people[0]!, "laboratory")).toBe(false);
  expect(inDepartment(people[1]!, "all")).toBe(true);
  expect(departmentOf({})).toBe("software");
});
