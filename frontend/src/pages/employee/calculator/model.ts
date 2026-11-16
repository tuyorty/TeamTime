/** Локальные прикидки по правилам обычных финансов; серверные данные не изменяются. */
export type Calculation<T> = { ok: true; value: T } | { ok: false; error: string };

export interface IntervalDraft { start: string; end: string; nextDay?: boolean }
export interface CalculatedInterval {
  index: number;
  startMinute: number;
  endMinute: number;
  durationMinutes: number;
  nextDay: boolean;
}
export interface DayCalculation {
  intervals: CalculatedInterval[];
  factMinutes: number;
  breakMinutes: number;
  effectiveMinutes: number;
  efficiencyPercent: number;
  dailyEfficiency: number;
  creditedMinutes: number;
  roundingDeltaMinutes: number;
}
export interface MonthTerms {
  contractNormSec: number;
  normSec: number;
  hourlyRate: number | string;
  projectBonuses: number | string;
  penaltySec: number;
}
export interface MonthInput extends MonthTerms {
  workedSec: number;
  efficiencyPercent: number;
  effectiveSec?: number;
}
export interface MoneyBreakdown {
  effectiveSec: number;
  creditedSec: number;
  overtimeSec: number;
  salary: number;
  overtimePay: number;
  projectBonuses: number;
  totalPay: number;
}
export interface MonthCalculation extends MoneyBreakdown {
  workedSec: number;
  efficiencyPercent: number;
}
export interface TargetInput extends MonthTerms {
  targetAmount: number | string;
  currentEffectiveSec: number;
  efficiencyPercent: number;
}
export interface TargetCalculation {
  targetAmount: number;
  targetReached: boolean;
  unreachable: null | "zero_rate" | "zero_efficiency";
  current: MoneyBreakdown;
  projected: MoneyBreakdown | null;
  requiredTotalEffectiveSec: number | null;
  additionalEffectiveSec: number | null;
  additionalWorkedSec: number | null;
  additionalOvertimeSec: number | null;
}

const DAY_MINUTES = 24 * 60;
const failure = (error: string): { ok: false; error: string } => ({ ok: false, error });
const valid = (value: number) => Number.isFinite(value) && value >= 0 && value <= 1e12;

function clockMinutes(text: string): number | null {
  const match = /^(\d{1,2}):(\d{2})$/.exec(text.trim());
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  return hour < 24 && minute < 60 ? hour * 60 + minute : null;
}

/** Длительность в секундах: часы:минуты либо десятичные часы, в том числе с запятой. */
export function parseDuration(text: string): number | null {
  const value = text.trim().replace(",", ".");
  const match = /^(\d+):(\d{2})$/.exec(value);
  if (match) {
    const seconds = Number(match[1]) * 3600 + Number(match[2]) * 60;
    return Number(match[2]) < 60 && valid(seconds) ? seconds : null;
  }
  if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(value)) return null;
  const seconds = Number(value) * 3600;
  return valid(seconds) ? seconds : null;
}

/** Дробный e% парсер округляет к ближайшему целому; половины — к чётному. */
function dailyPercent(effective: number, fact: number): number {
  const numerator = effective * 100;
  const whole = Math.floor(numerator / fact);
  const twiceRemainder = (numerator % fact) * 2;
  return whole + Number(twiceRemainder > fact || (twiceRemainder === fact && whole % 2 === 1));
}

export function calculateDay(drafts: readonly IntervalDraft[], breakMinutes: number): Calculation<DayCalculation> {
  if (!drafts.length) return failure("Добавьте хотя бы один интервал работы.");
  if (!Number.isInteger(breakMinutes) || !valid(breakMinutes)) return failure("Укажите перерывы целым числом минут от нуля.");
  const intervals: CalculatedInterval[] = [];
  for (const [index, draft] of drafts.entries()) {
    const start = clockMinutes(draft.start);
    const end = clockMinutes(draft.end);
    if (start === null || end === null) return failure(`Проверьте время в интервале ${index + 1}.`);
    const nextDay = !!draft.nextDay || end < start;
    const finish = end + (nextDay ? DAY_MINUTES : 0);
    if (finish === start) return failure(`В интервале ${index + 1} начало совпадает с концом.`);
    if (finish - start > DAY_MINUTES) return failure("Один интервал не может быть длиннее суток.");
    intervals.push({ index, startMinute: start, endMinute: finish, durationMinutes: finish - start, nextDay });
  }
  // Сдвиг на сутки выявляет также пересечения 22:00–02:00 и 01:00–03:00.
  for (let i = 0; i < intervals.length; i++) {
    for (let j = i + 1; j < intervals.length; j++) {
      const a = intervals[i]!;
      const b = intervals[j]!;
      if ([-DAY_MINUTES, 0, DAY_MINUTES].some((offset) =>
        Math.max(a.startMinute, b.startMinute + offset) < Math.min(a.endMinute, b.endMinute + offset))) {
        return failure(`Интервалы ${i + 1} и ${j + 1} пересекаются. Разделите их, чтобы не считать время дважды.`);
      }
    }
  }
  if (intervals.some((interval) => interval.nextDay)) {
    const firstStart = intervals[0]!.startMinute;
    for (const interval of intervals) {
      if (interval.startMinute < firstStart) {
        interval.startMinute += DAY_MINUTES;
        interval.endMinute += DAY_MINUTES;
      }
    }
    if (intervals.some((interval, index) => index > 0 && interval.startMinute < intervals[index - 1]!.endMinute)) {
      return failure("Для ночной смены укажите интервалы по порядку, начиная с первого.");
    }
  }
  intervals.sort((a, b) => a.startMinute - b.startMinute);
  const factMinutes = intervals.reduce((sum, interval) => sum + interval.durationMinutes, 0);
  if (factMinutes > DAY_MINUTES || intervals.at(-1)!.endMinute - intervals[0]!.startMinute > DAY_MINUTES) {
    return failure("Расчёт одного дейлика должен укладываться в 24 часа.");
  }
  if (breakMinutes > factMinutes) return failure("Перерывы не могут быть длиннее всех рабочих интервалов.");
  const effectiveMinutes = factMinutes - breakMinutes;
  const dailyEfficiency = dailyPercent(effectiveMinutes, factMinutes);
  const creditedMinutes = factMinutes * dailyEfficiency / 100;
  return { ok: true, value: {
    intervals, factMinutes, breakMinutes, effectiveMinutes,
    efficiencyPercent: effectiveMinutes * 100 / factMinutes,
    dailyEfficiency, creditedMinutes, roundingDeltaMinutes: creditedMinutes - effectiveMinutes,
  } };
}

/** Строка для дейлика: порядок смены сохранён, полные сутки не превращаются в пустой интервал. */
export function serializeDayIntervals(day: DayCalculation): string {
  const clock = (minutes: number) => `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
  return [...day.intervals].sort((a, b) => a.startMinute - b.startMinute).flatMap((interval) => {
    const start = interval.startMinute % DAY_MINUTES;
    const end = interval.endMinute % DAY_MINUTES;
    if (interval.durationMinutes === DAY_MINUTES && start !== 0) {
      // Парсер считает одинаковые часы нулём. Два отрезка сохраняют сутки и ночной переход.
      const middle = (start + DAY_MINUTES / 2) % DAY_MINUTES || 60;
      return [`${clock(start)} - ${clock(middle)}`, `${clock(middle)} - ${clock(end)}`];
    }
    return [`${clock(start)} - ${clock(end || DAY_MINUTES)}`];
  }).join(" + ");
}

type Fraction = { n: bigint; d: bigint };
const ZERO: Fraction = { n: 0n, d: 1n };
const add = (a: Fraction, b: Fraction): Fraction => ({ n: a.n * b.d + b.n * a.d, d: a.d * b.d });
const subtract = (a: Fraction, b: Fraction): Fraction => ({ n: a.n * b.d - b.n * a.d, d: a.d * b.d });
const multiply = (a: Fraction, b: Fraction): Fraction => ({ n: a.n * b.n, d: a.d * b.d });
const divide = (a: Fraction, b: Fraction): Fraction => ({ n: a.n * b.d, d: a.d * b.n });
const positive = (value: Fraction): Fraction => value.n > 0n ? value : ZERO;
const numeric = (value: Fraction): number => Number(value.n) / Number(value.d);

/** Десятичные ставки переводим в рациональные числа, чтобы копейки не зависели от float. */
function fraction(value: number | string): Fraction {
  const raw = String(value).trim().replace(",", ".");
  const text = raw.startsWith(".") ? `0${raw}` : raw;
  const match = /^([+-]?)(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/i.exec(text);
  if (!match || !Number.isFinite(Number(text))) throw new Error("Укажите корректные числовые значения.");
  const decimals = match[3] ?? "";
  const exponent = Number(match[4] ?? 0) - decimals.length;
  if (Math.abs(exponent) > 30) throw new Error("Слишком много знаков в числе.");
  const numerator = BigInt(match[2]! + decimals) * (match[1] === "-" ? -1n : 1n);
  return exponent >= 0 ? { n: numerator * 10n ** BigInt(exponent), d: 1n }
    : { n: numerator, d: 10n ** BigInt(-exponent) };
}

/** Как Decimal.quantize(..., ROUND_HALF_UP) в обычных финансах. */
function cents(value: Fraction): bigint {
  return (value.n * 200n + value.d) / (value.d * 2n);
}

function monetary(value: bigint): number {
  if (value < 0n || value > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error("Слишком большая сумма для расчёта.");
  return Number(value) / 100;
}

function roundedMinute(value: Fraction): number {
  if (value.n <= 0n) return 0;
  const denominator = value.d * 60n;
  const seconds = Number((value.n + denominator - 1n) / denominator) * 60;
  if (!Number.isSafeInteger(seconds)) throw new Error("Для этой цели требуется слишком много часов.");
  return seconds;
}

function checkTerms(input: MonthTerms): void {
  if (![input.contractNormSec, input.normSec, input.penaltySec].every(valid)) throw new Error("Норма и штрафное время должны быть неотрицательными.");
  if (input.normSec > input.contractNormSec) throw new Error("Норма с учётом отсутствий не может быть больше полной нормы.");
  const rate = numeric(fraction(input.hourlyRate));
  const bonus = numeric(fraction(input.projectBonuses));
  if (!valid(rate) || rate > 1_000_000) throw new Error("Ставка должна быть от 0 до 1 000 000 ₽ в час.");
  if (!valid(bonus)) throw new Error("Проектные премии должны быть неотрицательными.");
}

function breakdown(input: MonthTerms, effective: Fraction): MoneyBreakdown {
  const credited = subtract(effective, fraction(input.penaltySec));
  const overtime = positive(subtract(credited, fraction(input.normSec)));
  const ratePerSecond = divide(fraction(input.hourlyRate), fraction(3600));
  const salary = cents(multiply(fraction(input.contractNormSec), ratePerSecond));
  const overtimePay = cents(multiply(overtime, ratePerSecond));
  const bonus = cents(fraction(input.projectBonuses));
  return {
    effectiveSec: numeric(effective), creditedSec: numeric(credited), overtimeSec: numeric(overtime),
    salary: monetary(salary), overtimePay: monetary(overtimePay), projectBonuses: monetary(bonus),
    totalPay: monetary(salary + overtimePay + bonus),
  };
}

function checkEfficiency(value: number): void {
  if (!Number.isFinite(value) || value < 0 || value > 100) throw new Error("Эффективность должна быть от 0 до 100%.");
}

export function calculateMonth(input: MonthInput): Calculation<MonthCalculation> {
  try {
    checkTerms(input);
    checkEfficiency(input.efficiencyPercent);
    if (!valid(input.workedSec)) throw new Error("Укажите неотрицательное фактическое время.");
    if (input.effectiveSec !== undefined && (!valid(input.effectiveSec) || input.effectiveSec > input.workedSec)) {
      throw new Error("Эффективное время должно быть от нуля до фактического.");
    }
    const effective = input.effectiveSec === undefined
      ? divide(multiply(fraction(input.workedSec), fraction(input.efficiencyPercent)), fraction(100))
      : fraction(input.effectiveSec);
    return { ok: true, value: { ...breakdown(input, effective), workedSec: input.workedSec,
      efficiencyPercent: input.effectiveSec === undefined ? input.efficiencyPercent
        : input.workedSec ? input.effectiveSec * 100 / input.workedSec : 0,
    } };
  } catch (error) { return failure(error instanceof Error ? error.message : "Не удалось выполнить расчёт."); }
}

export function calculateTarget(input: TargetInput): Calculation<TargetCalculation> {
  try {
    checkTerms(input);
    checkEfficiency(input.efficiencyPercent);
    if (!valid(input.currentEffectiveSec)) throw new Error("Укажите неотрицательное уже учтённое эффективное время.");
    const target = fraction(input.targetAmount);
    if (!valid(numeric(target))) throw new Error("Желаемая сумма должна быть неотрицательной.");
    const targetAmount = monetary(cents(target));
    const currentEffective = fraction(input.currentEffectiveSec);
    const current = breakdown(input, currentEffective);
    const rate = fraction(input.hourlyRate);
    const neededPay = subtract(fraction(targetAmount), add(fraction(current.salary), fraction(current.projectBonuses)));
    if (current.totalPay >= targetAmount) {
      const required = neededPay.n <= 0n ? ZERO : add(add(fraction(input.normSec), fraction(input.penaltySec)),
        divide(multiply(neededPay, fraction(3600)), rate));
      return { ok: true, value: {
        targetAmount, targetReached: true, unreachable: null, current, projected: current,
        requiredTotalEffectiveSec: roundedMinute(required), additionalEffectiveSec: 0,
        additionalWorkedSec: 0, additionalOvertimeSec: 0,
      } };
    }
    if (rate.n === 0n) return { ok: true, value: {
      targetAmount, targetReached: false, unreachable: "zero_rate", current, projected: null,
      requiredTotalEffectiveSec: null, additionalEffectiveSec: null, additionalWorkedSec: null, additionalOvertimeSec: null,
    } };
    const requiredOvertime = divide(multiply(neededPay, fraction(3600)), rate);
    const requiredEffective = add(add(fraction(input.normSec), fraction(input.penaltySec)), requiredOvertime);
    const additionalEffective = positive(subtract(requiredEffective, currentEffective));
    const additionalOvertime = positive(subtract(requiredOvertime, fraction(current.overtimeSec)));
    const common = {
      targetAmount, targetReached: false, current,
      requiredTotalEffectiveSec: roundedMinute(requiredEffective),
      additionalEffectiveSec: roundedMinute(additionalEffective), additionalOvertimeSec: roundedMinute(additionalOvertime),
    };
    if (input.efficiencyPercent === 0) return { ok: true, value: { ...common,
      unreachable: "zero_efficiency", projected: null, additionalWorkedSec: null,
    } };
    const additionalWorkedSec = roundedMinute(divide(multiply(additionalEffective, fraction(100)), fraction(input.efficiencyPercent)));
    const projectedEffective = add(currentEffective,
      divide(multiply(fraction(additionalWorkedSec), fraction(input.efficiencyPercent)), fraction(100)));
    return { ok: true, value: { ...common, unreachable: null, additionalWorkedSec,
      projected: breakdown(input, projectedEffective),
    } };
  } catch (error) { return failure(error instanceof Error ? error.message : "Не удалось выполнить расчёт."); }
}
