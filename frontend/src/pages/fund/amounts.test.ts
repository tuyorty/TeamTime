import { describe, expect, it } from "vitest";
import { sumMoney } from "../finance/amounts";

describe("итоги фонда с корректировками", () => {
  it("сохраняет отрицательные копейки и точную разницу", () => {
    expect(sumMoney(["1000.25", "-1000.50"])).toBe("-0.25");
    expect(sumMoney(["-0.01", "0.01"])).toBe("0.00");
    expect(sumMoney(["-1.99", "-0.02"])).toBe("-2.01");
  });
  it("не теряет копейки при больших командных суммах", () => {
    expect(sumMoney(Array(100).fill("999999999999.99"))).toBe("99999999999999.00");
  });
});
