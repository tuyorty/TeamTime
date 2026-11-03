import { useState } from "react";

export type Department = "software" | "laboratory";
export type DepartmentFilter = Department | "all";

export const DEPARTMENTS: Record<Department, string> = {
  software: "Программисты",
  laboratory: "Лаборатория",
};

export function departmentOf(employee: { department?: Department }): Department {
  return employee.department ?? "software";
}

export function inDepartment(employee: { department?: Department }, filter: string): boolean {
  return filter === "all" || departmentOf(employee) === filter;
}

export function employeeGroups<T extends { employee: { department?: Department } }>(rows: readonly T[]) {
  return (Object.keys(DEPARTMENTS) as Department[])
    .map((department) => ({ department, label: DEPARTMENTS[department], rows: rows.filter((r) => departmentOf(r.employee) === department) }))
    .filter((group) => group.rows.length);
}

export function useDepartmentFilter() {
  const [department, setDepartment] = useState<DepartmentFilter>("all");
  return { department, setDepartment, matches: (employee: { department?: Department }) => inDepartment(employee, department) };
}
