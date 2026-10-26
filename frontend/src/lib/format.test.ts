import { count, durationWords, hm, isoWeek, plural, rangeShort, shiftWeek, span } from "./format";

describe("hm", () => {
  it.each([
    [0, "0:00"],
    [27360, "7:36"],
    [14508, "4:01"], // 4:01:48 усекается вниз, как в таблице
    [59, "0:00"],
    [171300, "47:35"],
    [-70200, "−19:30"],
  ])("%i → %s", (s, expected) => expect(hm(s)).toBe(expected));

  it("отличает «нет данных» от нуля", () => {
    expect(hm(null)).toBe("—");
    expect(hm(undefined)).toBe("—");
  });
});

describe("plural", () => {
  it.each([
    [1, "день"], [2, "дня"], [5, "дней"], [11, "дней"], [12, "дней"], [14, "дней"],
    [21, "день"], [22, "дня"], [101, "день"], [111, "дней"],
  ])("%i %s", (n, word) => expect(plural(n, ["день", "дня", "дней"])).toBe(word));

  it("count склеивает число и слово", () => {
    expect(count(3, ["час", "часа", "часов"])).toBe("3 часа");
  });
});

describe("durationWords", () => {
  it("для aria-label", () => {
    expect(durationWords(27900)).toBe("7 часов 45 минут");
    expect(durationWords(3600)).toBe("1 час");
    expect(durationWords(0)).toBe("0 минут");
  });
});

describe("даты", () => {
  it("ISO-неделя", () => {
    expect(isoWeek(new Date(2026, 9, 26))).toEqual({ year: 2026, week: 44 });
    expect(isoWeek(new Date(2027, 0, 1))).toEqual({ year: 2026, week: 53 });
  });
  it("переход через год", () => {
    expect(shiftWeek(2026, 53, 1)).toEqual({ year: 2027, week: 1 });
    expect(shiftWeek(2027, 1, -1)).toEqual({ year: 2026, week: 53 });
  });
  it("диапазоны", () => {
    expect(rangeShort("2026-10-26", "2026-11-01")).toBe("26 окт – 1 ноя");
    expect(span(36000, 64800)).toBe("10:00–18:00");
  });
});
