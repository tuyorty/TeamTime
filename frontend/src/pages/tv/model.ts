import type { TodayRow } from "@/api/types";
import { clock, isoDate, parseDate } from "@/lib/format";

export type TvGroup = "office" | "remote" | "later" | "finished" | "off" | "absent" | "unknown";

export const GROUPS: { key: TvGroup; label: string }[] = [
  { key: "office", label: "В офисе" },
  { key: "remote", label: "Удалённо" },
  { key: "later", label: "Начнут позже" },
  { key: "finished", label: "Закончили" },
  { key: "off", label: "Выходной" },
  { key: "absent", label: "Отсутствуют" },
  { key: "unknown", label: "Нет расписания" },
];

/** Расписание определяет план, а не подтверждённое присутствие человека. */
export function groupFor(row: TodayRow): TvGroup {
  if (row.presence === "off" || row.presence === "absent") return row.presence;
  if (!timedPlan(row)) return "unknown";
  switch (row.presence) {
    case "on_site": return "office";
    case "remote": return "remote";
    case "expected_later": return "later";
    case "left": return "finished";
    default: return "unknown";
  }
}

export function timedPlan(row: TodayRow) {
  const plan = row.cell.plan;
  return plan?.kind === "work" && plan.start !== null && plan.end !== null ? plan : null;
}

export function groupCounts(rows: TodayRow[]): Record<TvGroup, number> {
  const result = { office: 0, remote: 0, later: 0, finished: 0, off: 0, absent: 0, unknown: 0 };
  for (const row of rows) result[groupFor(row)] += 1;
  return result;
}

export function sortTeam(rows: TodayRow[]): TodayRow[] {
  return [...rows].sort((a, b) =>
    GROUPS.findIndex((g) => g.key === groupFor(a)) - GROUPS.findIndex((g) => g.key === groupFor(b)) ||
    (a.cell.plan?.start ?? 86400) - (b.cell.plan?.start ?? 86400) ||
    a.employee.short_name.localeCompare(b.employee.short_name, "ru"),
  );
}

export interface TvEvent { row: TodayRow; time: number; kind: "start" | "end" }

/** Только начало и конец дня: отдельный учёт перерывов пока не включён. */
export function upcomingEvents(rows: TodayRow[], now: number): TvEvent[] {
  return rows.flatMap((row): TvEvent[] => {
    const plan = timedPlan(row);
    if (!plan || row.presence === "off" || row.presence === "absent") return [];
    return [
      { row, time: plan.start!, kind: "start" as const },
      { row, time: plan.end!, kind: "end" as const },
    ].filter((event) => event.time > now);
  }).sort((a, b) => a.time - b.time || a.row.employee.short_name.localeCompare(b.row.employee.short_name, "ru"));
}

export function nextDate(day: string): string {
  const date = parseDate(day);
  date.setDate(date.getDate() + 1);
  return isoDate(date);
}

/** Время следующего дня не превращаем в «25:00». */
export function tvClock(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  return `${clock(seconds % 86400)}${seconds >= 86400 ? " +1" : ""}`;
}

export function tomorrowSummary(rows: TodayRow[]) {
  const working = rows.filter((row) => timedPlan(row) && row.presence !== "off" && row.presence !== "absent");
  const remote = working.filter((row) => row.cell.status === "remote").length;
  const away = rows.filter((row) => row.presence === "off" || row.presence === "absent").length;
  return {
    office: working.length - remote,
    remote,
    away,
    unknown: rows.length - working.length - away,
    firstStart: working.length ? Math.min(...working.map((row) => row.cell.plan!.start!)) : null,
  };
}
