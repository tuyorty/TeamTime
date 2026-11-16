import { parseDuration } from "./model";

/** В полях длительностей вводятся часы, а не время суток. */
export const readHours = (text: string): number => parseDuration(text) ?? NaN;

export function readNumber(text: string): number {
  const value = text.trim().replace(",", ".");
  return /^\d+(?:\.\d+)?$/.test(value) ? Number(value) : NaN;
}

/** Единый 24-часовой ввод, в том числе цифрами с клавиатуры телефона. */
export function normalizeClock(text: string): string {
  const value = text.trim();
  const separated = /^(\d{1,2}):(\d{1,2})$/.exec(value);
  let hours: number;
  let minutes: number;
  if (separated) {
    hours = Number(separated[1]);
    minutes = Number(separated[2]);
  } else if (/^\d{1,4}$/.test(value)) {
    hours = Number(value.length <= 2 ? value : value.slice(0, -2));
    minutes = value.length <= 2 ? 0 : Number(value.slice(-2));
  } else {
    return text;
  }
  // Не исправляем неверные часы и не превращаем AM/PM в другое время молча.
  if (hours > 23 || minutes > 59) return text;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}
