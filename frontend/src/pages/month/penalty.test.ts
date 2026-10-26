import { penaltyHours } from "./penalty";

const scale = { soft_limit_h: 5, hard_limit_h: 12, quad_coef: 3 / 14, hard_value_h: 22.5, tail_slope: 4, problems: [] };

describe("кривая штрафа совпадает с золотыми значениями сервера", () => {
  it.each([
    [2 + 17 / 60, "2:17"],
    [5 + 20 / 60, "5:21"],
    [5 + 40 / 60, "5:45"],
    [6 + 10 / 60, "6:27"],
    [6 + 45 / 60, "7:24"],
    [12, "22:30"],
    [13, "26:30"],
  ])("%f ч → %s", (x, expected) => {
    const s = Math.round(penaltyHours(x, scale) * 3600 * 1000) / 1000;
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    expect(`${h}:${String(m).padStart(2, "0")}`).toBe(expected);
  });
});
