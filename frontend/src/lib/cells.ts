import type { DayCell } from "@/api/types";

/** День с опозданием, ранним уходом, недоработкой или без дейлика. */
export function hasDeviation(c: DayCell): boolean {
  return !!(c.late_sec || c.early_leave_sec || c.undertime_sec || c.state === "missing");
}
