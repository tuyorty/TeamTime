import { parseDuration } from "./model";

/** В полях длительностей вводятся часы, а не время суток. */
export const readHours = (text: string): number => parseDuration(text) ?? NaN;

export function readNumber(text: string): number {
  const value = text.trim().replace(",", ".");
  return /^\d+(?:\.\d+)?$/.test(value) ? Number(value) : NaN;
}
