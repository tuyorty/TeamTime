import type { TodayRow } from "@/api/types";
import { groupCounts, groupFor, nextDate, tomorrowSummary, tvClock, upcomingEvents } from "./model";

function row(presence: TodayRow["presence"], id = 1): TodayRow {
  return {
    employee: { id, short_name: `Сотрудник ${id}`, full_name: `Сотрудник ${id}`, position: "", color: "", is_active: true, avatar_url: "" },
    presence, daily_overdue: false, tasks: [],
    cell: {
      date: "2026-10-23", state: "pending", status: null, status_label: null, status_note: null,
      plan: { kind: "work", start: 36000, end: 64800, intervals: [[36000, 64800]], planned_sec: 28800, note: null, note_has_time: false, raw_line: "" },
      fact: null, late_sec: null, early_leave_sec: null, undertime_sec: null, no_plan: false, flags: [], source: {},
    },
  };
}

it("вся команда учитывается ровно один раз, включая выходные и отсутствие времени", () => {
  const rows = (["on_site", "remote", "expected_later", "left", "off", "absent", "no_plan"] as const).map((presence, i) => row(presence, i));
  rows[6]!.cell.plan = null;
  const counts = groupCounts(rows);
  expect(Object.values(counts).reduce((a, b) => a + b, 0)).toBe(7);
  expect(counts).toEqual({ office: 1, remote: 1, later: 1, finished: 1, off: 1, absent: 1, unknown: 1 });
});

it("отметка об удалёнке без часов не означает, что человек сейчас работает", () => {
  const remote = row("remote");
  remote.cell.status = "remote";
  remote.cell.plan = null;
  expect(groupFor(remote)).toBe("unknown");
  expect(upcomingEvents([remote], 0)).toEqual([]);
});

it("ближайшие события не используют факты и отменённые отсутствием планы", () => {
  const office = row("on_site", 1);
  const absent = row("absent", 2);
  const off = row("off", 3);
  const later = row("expected_later", 4);
  later.cell.plan!.start = 54000;
  expect(upcomingEvents([office, absent, off, later], 40000).map((event) => [event.row.employee.id, event.kind, event.time]))
    .toEqual([[4, "start", 54000], [1, "end", 64800], [4, "end", 64800]]);
});

it("завтрашнее расписание различает удалёнку, отсутствие и неизвестное время", () => {
  const remote = row("expected_later", 1);
  remote.cell.status = "remote";
  const unknown = row("no_plan", 4);
  unknown.cell.plan = null;
  expect(tomorrowSummary([remote, row("expected_later", 2), row("absent", 3), unknown]))
    .toEqual({ office: 1, remote: 1, away: 1, unknown: 1, firstStart: 36000 });
});

it("дата завтра и время после полуночи не зависят от длины месяца", () => {
  expect(nextDate("2026-10-31")).toBe("2026-11-01");
  expect(nextDate("2026-12-31")).toBe("2027-01-01");
  expect(tvClock(25 * 3600)).toBe("1:00 +1");
  expect(tvClock(null)).toBe("—");
});
