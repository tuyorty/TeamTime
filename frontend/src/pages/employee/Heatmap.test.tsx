import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DayCell, EmployeeDetail } from "@/api/types";
import { TooltipProvider } from "@/components/ui/tooltip";
import { MonthHeatmap } from "./Heatmap";

const cell: DayCell = {
  date: "2026-11-10", state: "absence", status: "remote", status_label: "Удалёнка", status_note: null,
  plan: null, fact: null, late_sec: 28800, early_leave_sec: null, undertime_sec: null,
  no_plan: false, flags: ["no_show_confirmed"], source: {}, can_confirm_no_show: false,
};

function show(day: DayCell) {
  const data = { start: day.date, end: day.date, days: [day] } as EmployeeDetail;
  render(<TooltipProvider><MonthHeatmap data={data} today={day.date} /></TooltipProvider>);
}

describe("невыход в календаре сотрудника", () => {
  it("показывает подтверждённый невыход вместо пустого дня или удалёнки", () => {
    show(cell);
    expect(screen.getByRole("gridcell", { name: "10 ноября: невыход подтверждён, 8:00 в опоздания" })).toBeVisible();
    expect(screen.queryByRole("gridcell", { name: "10 ноября: удалёнка" })).not.toBeInTheDocument();
  });

  it("при конфликте сохраняет реальные часы нового дейлика", () => {
    show({ ...cell, state: "worked", flags: ["no_show_conflict"], late_sec: null, fact: {
      start: 36000, end: 64800, intervals: [[36000, 64800]], worked_sec: 28800, efficiency: 80,
      result_sec: 23040, tasks: [], edited: false, source: "telegram", sent_at: null,
    } });
    expect(screen.getByRole("gridcell", { name: "10 ноября: 8:00" })).toBeVisible();
    expect(screen.queryByText("невыход")).not.toBeInTheDocument();
  });
});
