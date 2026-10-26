import type { DayCell } from "@/api/types";

export interface Axis {
  start: number;
  end: number;
}

export const DAY = 86400;

/** Шкала для набора ячеек: от самого раннего начала до самого позднего конца, по целым часам. */
export function axisFor(cells: DayCell[], fallback: Axis = { start: 9 * 3600, end: 19 * 3600 }): Axis {
  let lo = Infinity;
  let hi = -Infinity;
  for (const c of cells) {
    for (const [a, b] of [...(c.plan?.intervals ?? []), ...(c.fact?.intervals ?? [])]) {
      lo = Math.min(lo, a);
      hi = Math.max(hi, b < a ? DAY + b : b);
    }
  }
  if (!Number.isFinite(lo)) return fallback;
  const start = Math.max(0, Math.floor(lo / 3600) * 3600);
  const end = Math.min(DAY + 6 * 3600, Math.ceil(hi / 3600) * 3600);
  return end - start < 6 * 3600 ? { start: Math.max(0, start - 3600), end: start + 7 * 3600 } : { start, end };
}
