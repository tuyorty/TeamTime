import {
  AlarmClock, CircleDashed, Coffee, Hourglass, House, LogOut, MoonStar, Palmtree, Sparkles,
  Thermometer, UserX, type LucideIcon,
} from "lucide-react";

import type { DayCell, StatusKind } from "@/api/types";
import { clock } from "@/lib/format";

export const STATUS: Record<StatusKind, { label: string; icon: LucideIcon; tone: "absence" | "neutral" }> = {
  vacation: { label: "Отпуск", icon: Palmtree, tone: "absence" },
  sick: { label: "Больничный", icon: Thermometer, tone: "absence" },
  dayoff: { label: "Отгул", icon: Coffee, tone: "absence" },
  absent: { label: "Не придёт", icon: UserX, tone: "absence" },
  off: { label: "Выходной", icon: MoonStar, tone: "neutral" },
  remote: { label: "Удалёнка", icon: House, tone: "neutral" },
};

export const DEVIATION = {
  late: { label: "Опоздание", icon: AlarmClock, tone: "late" as const },
  early_leave: { label: "Ранний уход", icon: LogOut, tone: "deviation" as const },
  undertime: { label: "Недоработка", icon: Hourglass, tone: "deviation" as const },
  missing: { label: "Нет дейлика", icon: CircleDashed, tone: "neutral" as const },
  no_plan: { label: "Без плана", icon: Sparkles, tone: "neutral" as const },
};

/** Короткое описание дня для aria-label и подсказок. */
export function describeCell(c: DayCell): string {
  const parts: string[] = [];
  if (c.status) parts.push(STATUS[c.status].label);
  if (c.plan?.kind === "work") parts.push(`план ${clock(c.plan.start)}–${clock(c.plan.end)}`);
  else if (c.plan?.kind === "off") parts.push("выходной по плану");
  else if (c.plan?.kind === "note") parts.push(`план: «${c.plan.note ?? ""}»`);
  if (c.fact) {
    parts.push(`факт ${c.fact.intervals.map(([a, b]) => `${clock(a)}–${clock(b)}`).join(", ")}`);
    parts.push(`часов ${clock(c.fact.worked_sec)}`);
    if (c.fact.efficiency !== null && c.fact.efficiency !== undefined) parts.push(`эффективность ${c.fact.efficiency}%`);
  } else if (c.state === "missing") parts.push("нет дейлика");
  else if (c.state === "pending") parts.push("дейлик ещё не пришёл");
  if (c.late_sec) parts.push(`опоздание ${clock(c.late_sec)}`);
  if (c.early_leave_sec) parts.push(`ранний уход ${clock(c.early_leave_sec)}`);
  if (c.undertime_sec) parts.push(`недоработка ${clock(c.undertime_sec)}`);
  return parts.join(", ");
}

