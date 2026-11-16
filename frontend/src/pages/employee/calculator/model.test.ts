import { calculateDay, calculateMonth, calculateTarget, parseDuration, serializeDayIntervals, type Calculation, type MonthTerms } from "./model";

const HOUR = 3600;
const terms: MonthTerms = {
  contractNormSec: 160 * HOUR, normSec: 160 * HOUR,
  hourlyRate: "500", projectBonuses: "0", penaltySec: 0,
};

function value<T>(result: Calculation<T>): T {
  if (!result.ok) throw new Error(result.error);
  return result.value;
}

describe("эффективность дейлика по времени", () => {
  it("вычитает обед из суммы интервалов, не вычитая промежуток между ними ещё раз", () => {
    const result = value(calculateDay([
      { start: "10:20", end: "18:00" }, { start: "19:50", end: "23:40" },
    ], 60));
    expect(result.factMinutes).toBe(690);
    expect(result.effectiveMinutes).toBe(630);
    expect(result.efficiencyPercent).toBeCloseTo(91.304347826);
    expect(result.dailyEfficiency).toBe(91);
    expect(result.creditedMinutes).toBeCloseTo(627.9);
    expect(result.roundingDeltaMinutes).toBeCloseTo(-2.1);
  });

  it("показывает 100% без перерывов и 0%, когда весь интервал занят перерывом", () => {
    expect(value(calculateDay([{ start: "10:00", end: "11:00" }], 0)).dailyEfficiency).toBe(100);
    expect(value(calculateDay([{ start: "10:00", end: "11:00" }], 60)).dailyEfficiency).toBe(0);
  });

  it.each([[11, 94], [9, 96]])("при перерыве %i минут округляет половину к чётному проценту как Python", (breakMinutes, expected) => {
    const result = value(calculateDay([{ start: "10:00", end: "13:20" }], breakMinutes));
    expect(result.dailyEfficiency).toBe(expected);
  });

  it("учитывает ночное продолжение и сохраняет исходные интервалы", () => {
    const drafts = [{ start: "22:00", end: "02:00" }, { start: "03:00", end: "05:00" }];
    const result = value(calculateDay(drafts, 30));
    expect(result.factMinutes).toBe(360);
    expect(result.effectiveMinutes).toBe(330);
    expect(result.intervals.map((interval) => [interval.startMinute, interval.endMinute]))
      .toEqual([[1320, 1560], [1620, 1740]]);
    expect(drafts[1]).toEqual({ start: "03:00", end: "05:00" });
  });

  it.each([
    [[{ start: "10:00", end: "14:00" }, { start: "13:00", end: "18:00" }], 0],
    [[{ start: "22:00", end: "02:00" }, { start: "01:00", end: "03:00" }], 0],
    [[{ start: "10:00", end: "10:00" }], 0],
    [[{ start: "25:00", end: "10:00" }], 0],
    [[{ start: "10:65", end: "11:00" }], 0],
    [[{ start: "10:00", end: "11:00" }], 61],
    [[{ start: "10:00", end: "11:00" }], -1],
    [[{ start: "10:00", end: "11:00" }], Number.NaN],
    [[], 0],
  ])("не выдаёт результат при некорректных интервалах или перерывах %#", (intervals, breaks) => {
    expect(calculateDay(intervals, breaks).ok).toBe(false);
  });

  it("разрешает соседние интервалы и ровно сутки только при явном переходе даты", () => {
    expect(value(calculateDay([{ start: "10:00", end: "12:00" }, { start: "12:00", end: "14:00" }], 0)).factMinutes).toBe(240);
    expect(value(calculateDay([{ start: "00:00", end: "00:00", nextDay: true }], 0)).factMinutes).toBe(1440);
    expect(calculateDay([{ start: "10:00", end: "11:00", nextDay: true }], 0).ok).toBe(false);
  });
});

describe("интервалы для копирования в дейлик", () => {
  it("выводит дневные интервалы в хронологическом порядке с ведущими нулями", () => {
    const day = value(calculateDay([{ start: "19:50", end: "23:40" }, { start: "9:00", end: "18:00" }], 60));
    expect(serializeDayIntervals(day)).toBe("09:00 - 18:00 + 19:50 - 23:40");
  });

  it("сохраняет порядок ночной смены и её продолжения после полуночи", () => {
    const day = value(calculateDay([{ start: "22:00", end: "02:00" }, { start: "03:00", end: "05:00" }], 30));
    expect(serializeDayIntervals(day)).toBe("22:00 - 02:00 + 03:00 - 05:00");
  });

  it.each([
    ["00:00", "00:00", true, "00:00 - 24:00"],
    ["20:00", "00:00", false, "20:00 - 24:00"],
    ["10:00", "10:00", true, "10:00 - 22:00 + 22:00 - 10:00"],
    ["12:00", "12:00", true, "12:00 - 01:00 + 01:00 - 12:00"],
  ])("сохраняет длительность и переход даты для %s–%s", (start, end, nextDay, expected) => {
    expect(serializeDayIntervals(value(calculateDay([{ start, end, nextDay }], 0)))).toBe(expected);
  });
});

describe("месяц по правилам обычных финансов", () => {
  it("сохраняет полный оклад при недоработке", () => {
    const result = value(calculateMonth({ ...terms, workedSec: 140 * HOUR, efficiencyPercent: 100 }));
    expect(result.effectiveSec).toBe(140 * HOUR);
    expect(result.overtimePay).toBe(0);
    expect(result.salary).toBe(80_000);
    expect(result.totalPay).toBe(80_000);
  });

  it("считает переработку после эффективности и штрафа, а оклад — по полной норме", () => {
    const result = value(calculateMonth({
      ...terms, normSec: 128 * HOUR, workedSec: 200 * HOUR,
      efficiencyPercent: 90, penaltySec: 10 * HOUR, projectBonuses: "5000",
    }));
    expect(result.effectiveSec).toBe(180 * HOUR);
    expect(result.creditedSec).toBe(170 * HOUR);
    expect(result.overtimeSec).toBe(42 * HOUR);
    expect(result.salary).toBe(80_000);
    expect(result.overtimePay).toBe(21_000);
    expect(result.totalPay).toBe(106_000);
  });

  it("не обнуляет отрицательный итог времени и отдельно округляет оклад и переработку", () => {
    const negative = value(calculateMonth({ ...terms, workedSec: HOUR, efficiencyPercent: 50, penaltySec: 2 * HOUR }));
    expect(negative.creditedSec).toBe(-1.5 * HOUR);
    expect(negative.overtimePay).toBe(0);
    expect(negative.totalPay).toBe(80_000);
    const cents = value(calculateMonth({ ...terms, contractNormSec: HOUR, normSec: HOUR, hourlyRate: ".005",
      workedSec: 2 * HOUR, efficiencyPercent: 100 }));
    expect(cents.salary).toBe(0.01);
    expect(cents.overtimePay).toBe(0.01);
    expect(cents.totalPay).toBe(0.02);
  });

  it("принимает явные эффективные часы без повторного умножения на процент", () => {
    const result = value(calculateMonth({ ...terms, workedSec: 200 * HOUR, efficiencyPercent: 50, effectiveSec: 180 * HOUR }));
    expect(result.effectiveSec).toBe(180 * HOUR);
    expect(result.efficiencyPercent).toBe(90);
    expect(result.totalPay).toBe(90_000);
    expect(calculateMonth({ ...terms, workedSec: HOUR, effectiveSec: 2 * HOUR, efficiencyPercent: 100 }).ok).toBe(false);
  });
});

describe("целевая сумма за месяц", () => {
  it("применяет выбранную эффективность только к будущим часам", () => {
    const result = value(calculateTarget({ ...terms, targetAmount: "100000", currentEffectiveSec: 100 * HOUR, efficiencyPercent: 80 }));
    expect(result.targetReached).toBe(false);
    expect(result.requiredTotalEffectiveSec).toBe(200 * HOUR);
    expect(result.additionalEffectiveSec).toBe(100 * HOUR);
    expect(result.additionalWorkedSec).toBe(125 * HOUR);
    expect(result.additionalOvertimeSec).toBe(40 * HOUR);
    expect(result.projected?.totalPay).toBe(100_000);
  });

  it("округляет будущую работу вверх до минуты, чтобы не обещать недостижимую сумму", () => {
    const result = value(calculateTarget({ ...terms, targetAmount: 100_000, currentEffectiveSec: 60 * HOUR, efficiencyPercent: 90 }));
    expect(result.additionalWorkedSec).toBe(9334 * 60);
    expect(result.projected!.totalPay).toBeGreaterThanOrEqual(100_000);
    const previous = value(calculateMonth({ ...terms, workedSec: 60 * HOUR + result.additionalWorkedSec! - 60,
      effectiveSec: 60 * HOUR + (result.additionalWorkedSec! - 60) * 0.9, efficiencyPercent: 90 }));
    expect(previous.totalPay).toBeLessThan(100_000);
  });

  it("учитывает снижённую норму, месячный штраф и проектную премию", () => {
    const result = value(calculateTarget({ ...terms, normSec: 128 * HOUR, penaltySec: 10 * HOUR,
      projectBonuses: "5000", targetAmount: "100000", currentEffectiveSec: 100 * HOUR, efficiencyPercent: 80 }));
    expect(result.requiredTotalEffectiveSec).toBe(168 * HOUR);
    expect(result.additionalEffectiveSec).toBe(68 * HOUR);
    expect(result.additionalWorkedSec).toBe(85 * HOUR);
    expect(result.projected?.totalPay).toBe(100_000);
  });

  it("для суммы в пределах оклада не требует переработку даже при нулевой эффективности", () => {
    const result = value(calculateTarget({ ...terms, targetAmount: 70_000, currentEffectiveSec: 20 * HOUR, efficiencyPercent: 0 }));
    expect(result.targetReached).toBe(true);
    expect(result.requiredTotalEffectiveSec).toBe(0);
    expect(result.additionalWorkedSec).toBe(0);
    expect(result.unreachable).toBeNull();
  });

  it("показывает достижимую цель и нужный общий уровень, когда уже отработано больше", () => {
    const result = value(calculateTarget({ ...terms, targetAmount: 100_000, currentEffectiveSec: 250 * HOUR, efficiencyPercent: 0 }));
    expect(result.targetReached).toBe(true);
    expect(result.requiredTotalEffectiveSec).toBe(200 * HOUR);
    expect(result.additionalWorkedSec).toBe(0);
  });

  it("объясняет невозможность набрать сумму часами при нулевой ставке или эффективности", () => {
    const noRate = value(calculateTarget({ ...terms, hourlyRate: 0, projectBonuses: 1000,
      targetAmount: 2000, currentEffectiveSec: 200 * HOUR, efficiencyPercent: 100 }));
    expect(noRate.unreachable).toBe("zero_rate");
    expect(noRate.additionalWorkedSec).toBeNull();
    const noEfficiency = value(calculateTarget({ ...terms, targetAmount: 100_000, currentEffectiveSec: 100 * HOUR, efficiencyPercent: 0 }));
    expect(noEfficiency.unreachable).toBe("zero_efficiency");
    expect(noEfficiency.additionalEffectiveSec).toBe(100 * HOUR);
    expect(noEfficiency.additionalWorkedSec).toBeNull();
  });

  it("не выдаёт NaN, бесконечность и отрицательные суммы при неверном вводе", () => {
    const input = { ...terms, targetAmount: 100_000, currentEffectiveSec: 0, efficiencyPercent: 100 };
    for (const patch of [
      { targetAmount: -1 }, { targetAmount: "" }, { hourlyRate: "NaN" }, { hourlyRate: -1 },
      { currentEffectiveSec: Number.NaN }, { efficiencyPercent: 101 }, { efficiencyPercent: -1 },
      { penaltySec: -1 }, { normSec: 200 * HOUR }, { projectBonuses: -5 },
    ]) expect(calculateTarget({ ...input, ...patch }).ok).toBe(false);
  });
});

it.each([
  ["10:30", 37800], ["10,5", 37800], ["1.25", 4500], ["0", 0], [".5", 1800],
  ["10:60", null], ["", null], ["-1", null], ["1e3", null], ["abc", null],
])("читает длительность %s без угадывания единиц", (input, expected) => {
  expect(parseDuration(input)).toBe(expected);
});
