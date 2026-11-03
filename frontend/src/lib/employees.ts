import type { Employee } from "@/api/types";

const names = new Intl.Collator("ru", { sensitivity: "base", numeric: true });

/** Постоянный порядок по фамилии, независимо от присутствия и начала смены. */
export function compareEmployees(a: Pick<Employee, "short_name" | "full_name" | "id">, b: Pick<Employee, "short_name" | "full_name" | "id">): number {
  return names.compare(a.short_name.trim(), b.short_name.trim()) ||
    names.compare(a.full_name.trim(), b.full_name.trim()) || a.id - b.id;
}

export function compareEmployeeRows(a: { employee: Pick<Employee, "short_name" | "full_name" | "id"> }, b: { employee: Pick<Employee, "short_name" | "full_name" | "id"> }): number {
  return compareEmployees(a.employee, b.employee);
}
