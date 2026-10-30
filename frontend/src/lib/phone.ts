/** Единое представление российского номера; неизвестный формат сохраняем как ввели. */
export function formatPhone(value: string): string {
  let digits = value.replace(/\D/g, "");
  if (digits.length === 10 && !value.trim().startsWith("+")) digits = `7${digits}`;
  if (digits.length === 11 && /^[78]/.test(digits)) {
    return `+7 (${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7, 9)}-${digits.slice(9)}`;
  }
  return value.trim();
}

export function phoneHref(value: string): string {
  return `tel:${formatPhone(value).replace(/[^+\d]/g, "")}`;
}

/** Запасной способ нужен для HTTP в локальной сети, где Clipboard API может быть недоступен. */
export async function copyText(value: string): Promise<void> {
  try {
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(value);
      return;
    }
  } catch {
    // После отказа браузера пробуем копирование в рамках того же нажатия пользователя.
  }
  const previous = document.activeElement;
  const input = document.createElement("textarea");
  input.value = value;
  input.setAttribute("readonly", "");
  input.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0";
  document.body.append(input);
  try {
    input.select();
    if (!document.execCommand("copy")) throw new Error("Не удалось скопировать номер");
  } finally {
    input.remove();
    if (previous instanceof HTMLElement) previous.focus({ preventScroll: true });
  }
}
