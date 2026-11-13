import type { DayCell, DisplayDayCell, TodayRow } from "@/api/types";

type ScheduleRow = Pick<TodayRow, "presence"> & { cell: DisplayDayCell & Partial<DayCell> };

/** На рабочем экране показываем расписание, не подменяя его вечерним отчётом. */
export function scheduleCell(row: ScheduleRow): DayCell {
  return {
    ...row.cell,
    // Телевизор получает ограниченный ответ API; полосе и шкале нужна полная ячейка.
    flags: row.cell.flags ?? [],
    source: row.cell.source ?? {},
    status_label: row.cell.status_label ?? null,
    no_plan: row.cell.no_plan ?? row.cell.plan === null,
    no_show: row.cell.no_show ?? null,
    can_confirm_no_show: row.cell.can_confirm_no_show ?? false,
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
