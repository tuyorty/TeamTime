/**
 * Цвета сотрудников: проверенная категориальная палитра (dataviz, фиксированный порядок).
 * Цвет следует за человеком, а не за его местом в списке.
 */
const SLOTS: Record<string, { light: string; dark: string }> = {
  blue: { light: "#2a78d6", dark: "#3987e5" },
  orange: { light: "#eb6834", dark: "#d95926" },
  aqua: { light: "#1baf7a", dark: "#199e70" },
  yellow: { light: "#eda100", dark: "#c98500" },
  magenta: { light: "#e87ba4", dark: "#d55181" },
  green: { light: "#008300", dark: "#008300" },
  violet: { light: "#6250d6", dark: "#9085e9" },
  red: { light: "#e34948", dark: "#e66767" },
};
const ORDER = Object.keys(SLOTS);

export function employeeColor(color: string, id: number, dark: boolean): string {
  const slot = SLOTS[color] ?? SLOTS[ORDER[(id - 1) % ORDER.length]!]!;
  return dark ? slot.dark : slot.light;
}

export function initials(shortName: string): string {
  const [surname = "", rest = ""] = shortName.split(" ");
  return (surname[0] ?? "") + (rest.replace(/\./g, "")[0] ?? "");
}
