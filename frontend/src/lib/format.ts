/**
 * Форматирование для русской локали. Длительности приходят из API целыми секундами,
 * уже усечёнными на сервере; здесь мы только показываем их, усекая до минут, как исходная таблица.
 */

const MONTHS_GEN = [
  "января", "февраля", "марта", "апреля", "мая", "июня",
  "июля", "августа", "сентября", "октября", "ноября", "декабря",
];
const MONTHS_SHORT = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
export const MONTHS = [
  "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
];
export const WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
export const WEEKDAYS_LONG = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"];

/** «Ч:ММ» с усечением к нулю. null → прочерк: «нет данных» не равно «0:00». */
export function hm(seconds: number | null | undefined, empty = "—"): string {
  if (seconds === null || seconds === undefined) return empty;
  const sign = seconds < 0 ? "−" : "";
  const total = Math.trunc(Math.abs(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  return `${sign}${h}:${String(m).padStart(2, "0")}`;
}

/** Время суток из секунд от полуночи. 24:00 остаётся 24:00. */
export const clock = (seconds: number | null | undefined, empty = "—") => hm(seconds, empty);

export function span(start: number | null | undefined, end: number | null | undefined): string {
  return `${clock(start)}–${clock(end)}`;
}

/** Плюрализация: plural(5, ["день", "дня", "дней"]) → «дней». */
export function plural(n: number, forms: [string, string, string]): string {
  const abs = Math.abs(n) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return forms[2];
  if (last > 1 && last < 5) return forms[1];
  if (last === 1) return forms[0];
  return forms[2];
}

export function count(n: number, forms: [string, string, string]): string {
  return `${n} ${plural(n, forms)}`;
}

/** Длительность словами для подписей и aria: «7 часов 45 минут». */
export function durationWords(seconds: number): string {
  const total = Math.trunc(Math.abs(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const parts = [];
  if (h) parts.push(count(h, ["час", "часа", "часов"]));
  if (m || !h) parts.push(count(m, ["минута", "минуты", "минут"]));
  return parts.join(" ");
}

/** Дата из «ГГГГ-ММ-ДД» без сдвига часового пояса браузера. */
export function parseDate(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y!, m! - 1, d!);
}

export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function weekday(iso: string): number {
  return (parseDate(iso).getDay() + 6) % 7;
}

/** «26 октября» */
export function dayMonth(iso: string): string {
  const d = parseDate(iso);
  return `${d.getDate()} ${MONTHS_GEN[d.getMonth()]}`;
}

/** «26 окт» */
export function dayMonthShort(iso: string): string {
  const d = parseDate(iso);
  return `${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}`;
}

/** «пн, 26 октября» */
export function humanDay(iso: string): string {
  return `${WEEKDAYS_SHORT[weekday(iso)]!.toLowerCase()}, ${dayMonth(iso)}`;
}

/** «26 окт – 1 ноя» */
export function rangeShort(a: string, b: string): string {
  return `${dayMonthShort(a)} – ${dayMonthShort(b)}`;
}

export function ddmm(iso: string): string {
  const d = parseDate(iso);
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}`;
}

const timeFmt = new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" });
const dateTimeFmt = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric", month: "long", hour: "2-digit", minute: "2-digit",
});

export function timeOf(isoDateTime: string, timeZone?: string): string {
  return timeZone
    ? new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit", timeZone }).format(new Date(isoDateTime))
    : timeFmt.format(new Date(isoDateTime));
}

/** Название часового пояса и его смещение на указанную дату, включая летнее время. */
export function timezoneLabel(timeZone: string, at: string): string {
  const cities: Record<string, string> = {
    "Asia/Yekaterinburg": "Екатеринбург", "Europe/Moscow": "Москва", "Europe/Samara": "Самара",
    "Asia/Omsk": "Омск", "Asia/Novosibirsk": "Новосибирск", "Asia/Krasnoyarsk": "Красноярск",
    "Asia/Irkutsk": "Иркутск", "Asia/Vladivostok": "Владивосток", "Europe/Kaliningrad": "Калининград",
  };
  const offset = new Intl.DateTimeFormat("en", { timeZone, timeZoneName: "shortOffset" })
    .formatToParts(new Date(at)).find((part) => part.type === "timeZoneName")?.value.replace("GMT", "UTC");
  return `${cities[timeZone] ?? timeZone} (${offset ?? timeZone})`;
}

export function dateTime(isoDateTime: string): string {
  return dateTimeFmt.format(new Date(isoDateTime));
}

/** «5 минут назад», «вчера в 18:40». */
export function relative(isoDateTime: string, now = new Date()): string {
  const then = new Date(isoDateTime);
  const diff = Math.round((now.getTime() - then.getTime()) / 1000);
  if (diff < 45) return "только что";
  if (diff < 3600) {
    const m = Math.round(diff / 60);
    return `${count(m, ["минуту", "минуты", "минут"])} назад`;
  }
  if (diff < 6 * 3600) {
    const h = Math.round(diff / 3600);
    return `${count(h, ["час", "часа", "часов"])} назад`;
  }
  const sameDay = then.toDateString() === now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (sameDay) return `сегодня в ${timeFmt.format(then)}`;
  if (then.toDateString() === yesterday.toDateString()) return `вчера в ${timeFmt.format(then)}`;
  return dateTime(isoDateTime);
}

const rub = new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", minimumFractionDigits: 2 });

export function money(value: string | number): string {
  return rub.format(Number(value));
}

export function percent(fraction: number, digits = 0): string {
  return `${(fraction * 100).toFixed(digits)}%`;
}

/** ISO-неделя для даты. */
export function isoWeek(d: Date): { year: number; week: number } {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((t.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return { year: t.getUTCFullYear(), week };
}

/** Соседняя ISO-неделя. */
export function shiftWeek(year: number, week: number, delta: number): { year: number; week: number } {
  const jan4 = new Date(year, 0, 4);
  const monday = new Date(jan4);
  monday.setDate(jan4.getDate() - ((jan4.getDay() + 6) % 7) + (week - 1 + delta) * 7);
  return isoWeek(monday);
}

export function shiftMonth(year: number, month: number, delta: number): { year: number; month: number } {
  const d = new Date(year, month - 1 + delta, 1);
  return { year: d.getFullYear(), month: d.getMonth() + 1 };
}
