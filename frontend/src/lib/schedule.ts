import type { DayCell, TodayRow } from "@/api/types";

/** На рабочем экране показываем расписание, не подменяя его вечерним отчётом. */
export function scheduleCell(row: TodayRow): DayCell {
  return {
    ...row.cell,
    fact: null,
    late_sec: null,
    early_leave_sec: null,
    undertime_sec: null,
    state:
      row.presence === "off"
        ? "off"
        : row.presence === "absent"
          ? "absence"
          : row.cell.plan?.kind === "work"
            ? "pending"
            : "unplanned",
  };
}
