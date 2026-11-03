import type { Employee } from "@/api/types";
import { departmentOf, type Department } from "./departments";

type EmployeeName = Pick<Employee, "short_name" | "full_name" | "id"> & { department?: Department };

const names = new Intl.Collator("ru", { sensitivity: "base", numeric: true });

/** Постоянный порядок по фамилии, независимо от присутствия и начала смены. */
export function compareEmployees(a: EmployeeName, b: EmployeeName): number {
  return Number(departmentOf(a) === "laboratory") - Number(departmentOf(b) === "laboratory") || names.compare(a.short_name.trim(), b.short_name.trim()) ||
    names.compare(a.full_name.trim(), b.full_name.trim()) || a.id - b.id;
}

export function compareEmployeeRows(a: { employee: EmployeeName }, b: { employee: EmployeeName }): number {
  return compareEmployees(a.employee, b.employee);
}
