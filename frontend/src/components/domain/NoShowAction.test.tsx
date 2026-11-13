import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { NoShowAction } from "./NoShowAction";
import { describeCell } from "./states";

vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: vi.fn() }));

type Cell = Parameters<typeof NoShowAction>[0]["cell"];

function day(overrides: Partial<Cell> = {}): Cell {
  return {
    date: "2026-11-10", state: "missing", status: null, status_label: null, status_note: null,
    plan: { kind: "work", start: 36000, end: 64800, intervals: [[36000, 64800]], planned_sec: 28800, note: null, note_has_time: false, raw_line: "" },
    fact: null, late_sec: null, early_leave_sec: null, undertime_sec: null, no_plan: false, flags: ["missing_daily"],
    source: { plan_id: 17 }, can_confirm_no_show: true, no_show: null, ...overrides,
  };
}

const confirmation = {
  id: 31, plan_id: 17, seconds: 28800, intervals: [[36000, 64800]], reason: "Сотрудник подтвердил отсутствие",
  created_by: "admin", created_at: "2026-11-11T09:00:00+05:00",
};

function show(cell = day()) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><NoShowAction employeeId={7} cell={cell} /></QueryClientProvider>);
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.mocked(useIsAdmin).mockReturnValue(true);
  vi.spyOn(api, "post").mockResolvedValue({});
});

describe("явное подтверждение невыхода", () => {
  it("отсутствие дейлика не вызывает запрос, для подтверждения нужны проверка и причина", async () => {
    show();
    expect(api.post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить невыход…" }));
    const submit = screen.getByRole("button", { name: "Подтвердить невыход" });
    expect(submit).toBeDisabled();
    expect(screen.getByText("8:00")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Причина подтверждения"), { target: { value: "  " } });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Причина подтверждения"), { target: { value: "  Проверено с сотрудником  " } });
    fireEvent.click(submit);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/admin/days/7/2026-11-10/no-show", {
      expected_plan_id: 17, expected_seconds: 28800, reason: "Проверено с сотрудником",
    }));
  });

  it("не предлагает действие без разрешения сервера, даже если дейлика нет", () => {
    show(day({ can_confirm_no_show: false }));
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("читатель видит подтверждение, но не может его отменить", () => {
    vi.mocked(useIsAdmin).mockReturnValue(false);
    show(day({ no_show: confirmation, flags: ["no_show_confirmed"], state: "absence", late_sec: 28800 }));
    expect(screen.getByText("Невыход подтверждён")).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("конфликт с новыми данными можно отменить отдельным решением с причиной", async () => {
    show(day({ no_show: confirmation, flags: ["no_show_conflict"], can_confirm_no_show: false }));
    expect(screen.getByText("Невыход требует пересмотра")).toBeVisible();
    expect(screen.getByText(/время невыхода не добавляется к опозданию/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Отменить подтверждение…" }));
    expect(screen.getByRole("button", { name: "Отменить подтверждение" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Причина отмены"), { target: { value: "Получен подтверждающий дейлик" } });
    fireEvent.click(screen.getByRole("button", { name: "Отменить подтверждение" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/admin/days/7/2026-11-10/no-show/cancel", {
      expected_id: 31, reason: "Получен подтверждающий дейлик",
    }));
  });

  it("описание дня отличает подтверждённый невыход от пропущенного дейлика", () => {
    const description = describeCell(day({ flags: ["no_show_confirmed"], state: "absence", late_sec: 28800 }));
    expect(description).toContain("подтверждён невыход, в опозданиях 8:00");
    expect(description).not.toContain("нет дейлика");
  });
});
