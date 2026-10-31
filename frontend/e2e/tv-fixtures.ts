import type { Meta, Today, TodayRow } from "../src/api/types";

/** Полностью вымышленные данные: все состояния команды на одном ТВ-экране. */
export function tvFixture(date = "2026-10-23"): Today {
  const people: [string, string, TodayRow["presence"], number | null, number | null, TodayRow["cell"]["status"]][] = [
    ["Соколов А.М.", "Разработчик", "on_site", 9, 18, null],
    ["Морозова Е.В.", "Дизайнер", "on_site", 10, 19, null],
    ["Орлов Д.С.", "Инженер", "remote", 10, 18, "remote"],
    ["Волкова М.А.", "Разработчик", "expected_later", 15, 21, null],
    ["Лебедев И.П.", "Тестировщик", "expected_later", 16, 22, "remote"],
    ["Новикова А.Р.", "Аналитик", "left", 7, 14, null],
    ["Белов К.Н.", "Инженер", "off", null, null, null],
    ["Крылова О.Д.", "Дизайнер", "absent", null, null, "vacation"],
    ["Тихонов Р.Е.", "Разработчик", "no_plan", null, null, null],
  ];
  return {
    date, now_sec: 14.5 * 3600, counts: { total: people.length }, worked_sec: 0, feed: [], week_pulse: [],
    rows: people.map(([name, position, presence, start, end, status], i) => ({
      employee: { id: i + 1, short_name: name, full_name: name, position, color: "", is_active: true, avatar_url: "" },
      presence, daily_overdue: false, tasks: [],
      cell: {
        date, state: presence === "off" ? "off" : presence === "absent" ? "absence" : "pending",
        status, status_label: null, status_note: null,
        plan: start !== null && end !== null ? {
          kind: "work", start: start * 3600, end: end * 3600, planned_sec: (end - start) * 3600,
          intervals: [[start * 3600, end * 3600]], note: null, note_has_time: false, raw_line: "",
        } : null,
        fact: null, late_sec: null, early_leave_sec: null, undertime_sec: null, no_plan: start === null, flags: [], source: {},
      },
    })),
  };
}

export const tvMeta: Meta = {
  version: "demo", demo: true, admin_enabled: true, is_admin: false, timezone: "Asia/Yekaterinburg",
  today: "2026-10-23", now: "2026-10-23T14:30:00+05:00", bot_username: null, late_tolerance_min: 15, weekly_off: [6],
};
