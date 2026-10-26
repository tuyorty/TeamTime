import type { PenaltyScale } from "@/api/types";

/**
 * Шкала штрафа для графика. Это только рисование кривой: цифры в таблицах приходят с сервера
 * (точная арифметика, backend/src/teamtime/calc/penalty.py), а калькулятор спрашивает /penalty.
 */
export function penaltyHours(x: number, s: PenaltyScale): number {
  if (x <= 0) return 0;
  if (x <= s.soft_limit_h) return x;
  if (x <= s.hard_limit_h) {
    const d = x - s.soft_limit_h;
    return s.soft_limit_h + d + s.quad_coef * d * d;
  }
  return s.hard_value_h + s.tail_slope * (x - s.hard_limit_h);
}

export function curve(s: PenaltyScale, maxX: number, step = 0.25): { x: number; y: number }[] {
  const out = [];
  for (let x = 0; x <= maxX + 1e-9; x += step) out.push({ x: Number(x.toFixed(2)), y: penaltyHours(x, s) });
  return out;
}
