import { formatIntervals, parseIntervals, totalSeconds } from "./intervals";

describe("parseIntervals", () => {
  it("разбирает несколько интервалов и разные тире", () => {
    const r = parseIntervals("13:30 - 15:30; 17:30 – 18:40");
    expect(r.error).toBeNull();
    expect(r.intervals).toEqual([[48600, 55800], [63000, 67200]]);
    expect(totalSeconds(r.intervals)).toBe(3 * 3600 + 10 * 60);
  });
  it("00:00 в конце — полночь", () => {
    expect(parseIntervals("18:00-00:00").intervals).toEqual([[64800, 86400]]);
  });
  it("ночной интервал считается через полночь", () => {
    expect(totalSeconds(parseIntervals("22:00 - 2:00").intervals)).toBe(4 * 3600);
  });
  it.each(["", "10:00", "25:00-26:00", "10:00-10:00", "утром"])("ошибка для «%s»", (t) => {
    expect(parseIntervals(t).error).not.toBeNull();
  });
  it("форматирует обратно", () => {
    expect(formatIntervals([[36000, 64800]])).toBe("10:00 - 18:00");
  });
});
