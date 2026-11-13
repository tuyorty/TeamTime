import type { DayCell, DisplayDayCell } from "@/api/types";
import { describeCell } from "@/components/domain/states";
import { axisFor } from "./axis";
import { scheduleCell } from "./schedule";

/** Реальный контракт /display/today: поля расчёта дня сюда не входят. */
function displayCell(): DisplayDayCell {
  return {
    date: "2026-11-13", status: null, status_note: "",
    plan: {
      kind: "work", start: 36000, end: 64800, intervals: [[36000, 64800]],
      planned_sec: 28800, note: null, note_has_time: false, raw_line: "",
    },
  };
}

describe("ячейка расписания", () => {
  it("строит шкалу и описание по ограниченному ответу телевизора без flags", () => {
    const source = displayCell();
    const cell = scheduleCell({ presence: "on_site", cell: source });

    expect(source).not.toHaveProperty("flags");
    expect(axisFor([cell])).toEqual({ start: 36000, end: 64800 });
    expect(describeCell(cell)).toContain("план 10:00–18:00");
    expect(describeCell(cell)).not.toContain("подтверждён невыход");
    expect(cell.fact).toBeNull();
  });

  it("сохраняет отсутствие без плана из ограниченного ответа", () => {
    const cell = scheduleCell({
      presence: "absent", cell: { ...displayCell(), status: "vacation", plan: null },
    });

    expect(axisFor([cell], { start: 28800, end: 79200 })).toEqual({ start: 28800, end: 79200 });
    expect(cell.state).toBe("absence");
    expect(describeCell(cell)).toBe("Отпуск");
  });

  it("сохраняет подтверждение невыхода и его интервалы в полном ответе Сегодня", () => {
    const confirmation = {
      id: 31, plan_id: 17, seconds: 28800, intervals: [[36000, 64800]],
      reason: "Отсутствие подтверждено", created_by: "admin", created_at: "2026-11-14T09:00:00Z",
    };
    const source: DayCell = {
      ...displayCell(), state: "absence", status_label: null,
      plan: {
        kind: "off", start: null, end: null, intervals: [], planned_sec: 0,
        note: null, note_has_time: false, raw_line: "",
      },
      fact: null, late_sec: 28800, early_leave_sec: null, undertime_sec: null,
      flags: ["no_show_confirmed"], source: { plan_id: 17 }, no_plan: false,
      no_show: confirmation, can_confirm_no_show: false,
    };
    const cell = scheduleCell({ presence: "absent", cell: source });

    expect(cell.no_show).toEqual(confirmation);
    expect(cell.source).toEqual({ plan_id: 17 });
    expect(axisFor([cell])).toEqual({ start: 36000, end: 64800 });
    expect(describeCell(cell)).toContain("подтверждён невыход");
    expect(cell.late_sec).toBeNull();
    expect(source.late_sec).toBe(28800);
  });
});
