/** Ввод интервалов в формах правки — тот же синтаксис, что в дейликах: «10:00 - 13:00; 14:00 - 18:30». */

export type Interval = [number, number];

const TIME = /^(\d{1,2})(?:[:.](\d{2}))?$/;

function toSeconds(token: string, allow24: boolean): number | null {
  const m = TIME.exec(token.trim());
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2] ?? 0);
  if (min > 59 || h > 24 || (h === 24 && (min > 0 || !allow24))) return null;
  return h * 3600 + min * 60;
}

export function parseIntervals(text: string): { intervals: Interval[]; error: string | null } {
  const parts = text.split(/[;,]/).map((p) => p.trim()).filter(Boolean);
  if (!parts.length) return { intervals: [], error: "Укажите хотя бы один интервал" };
  const intervals: Interval[] = [];
  for (const part of parts) {
    const [a, b, ...rest] = part.split(/\s*[-–—]\s*/);
    if (!a || !b || rest.length) return { intervals: [], error: `Не понял «${part}»: нужно «10:00 - 18:00»` };
    const start = toSeconds(a, false);
    let end = toSeconds(b, true);
    if (start === null || end === null) return { intervals: [], error: `Нет такого времени в «${part}»` };
    if (end === 0 && start > 0) end = 86400;
    if (start === end) return { intervals: [], error: `Интервал «${part}» нулевой длины` };
    intervals.push([start, end]);
  }
  return { intervals, error: null };
}

export function formatIntervals(intervals: readonly (readonly [number, number])[]): string {
  const f = (s: number) => `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}`;
  return intervals.map(([a, b]) => `${f(a)} - ${f(b)}`).join("; ");
}

export function totalSeconds(intervals: readonly (readonly [number, number])[]): number {
  return intervals.reduce((sum, [a, b]) => sum + (b >= a ? b - a : 86400 - a + b), 0);
}
