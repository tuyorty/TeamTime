import { describe, expect, it, vi } from "vitest";
import { copyText, formatPhone, phoneHref } from "./phone";

describe("номер сотрудника", () => {
  it.each([
    ["79991234567", "+7 (999) 123-45-67"],
    ["8 999 123 45 67", "+7 (999) 123-45-67"],
    ["9991234567", "+7 (999) 123-45-67"],
    ["+7 (999) 123-45-67", "+7 (999) 123-45-67"],
    ["+44 20 0000 0000", "+44 20 0000 0000"],
    ["+47 12345678", "+47 12345678"],
  ])("форматирует %s", (input, expected) => expect(formatPhone(input)).toBe(expected));
  it("даёт ссылку для звонка", () => expect(phoneHref("89991234567")).toBe("tel:+79991234567"));
  it("копирует номер через Clipboard API", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    try {
      await copyText("+7 (999) 123-45-67");
      expect(writeText).toHaveBeenCalledWith("+7 (999) 123-45-67");
    } finally {
      vi.unstubAllGlobals();
    }
  });
  it("копирует в HTTP без Clipboard API и убирает временное поле", async () => {
    const original = Object.getOwnPropertyDescriptor(document, "execCommand");
    const execCommand = vi.fn(() => true);
    Object.defineProperty(document, "execCommand", { configurable: true, value: execCommand });
    vi.stubGlobal("navigator", {});
    try {
      await copyText("пример номера");
      expect(execCommand).toHaveBeenCalledWith("copy");
      expect(document.querySelector("textarea")).toBeNull();
    } finally {
      if (original) Object.defineProperty(document, "execCommand", original);
      else Reflect.deleteProperty(document, "execCommand");
      vi.unstubAllGlobals();
    }
  });
});
