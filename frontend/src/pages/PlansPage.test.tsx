import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import { useMeta, usePlans } from "@/api/queries";
import type { Plans, PlanVersion } from "@/api/types";
import { dateTime } from "@/lib/format";
import PlansPage from "./PlansPage";

vi.mock("@/api/queries", () => ({ useMeta: vi.fn(), usePlans: vi.fn() }));

const days = ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13", "2026-11-14", "2026-11-15"];
const base: PlanVersion = {
  id: 11, version: 1, created_at: "2026-11-12T15:00:00+05:00", source: "telegram",
  created_by: "bot", edited: false, retracted: true, days: [], tasks: ["Подготовить пример"],
  message_version_id: null, raw_message_id: null,
  stated_at: "2026-11-08T10:00:00+05:00", source_message_version: 1,
};

function fixture(current: PlanVersion | null = null, versions = [base]): Plans {
  return {
    iso_year: 2026, iso_week: 46, label: "46 неделя", week_start: days[0]!, days, required_days: days,
    rows: [{ employee: { id: 7, full_name: "Соколов Степан Сергеевич", short_name: "Соколов С.С.", position: "Инженер", color: "", avatar_url: "", department: "software", is_active: true }, current, versions, done_tasks: [], days_with_daily: 0, days_planned: 0 }],
  };
}

function show(url = "/plans/2026/46") {
  return render(<MemoryRouter initialEntries={[url]}><Routes><Route path="/plans/:year/:week" element={<PlansPage />} /></Routes></MemoryRouter>);
}

beforeEach(() => {
  localStorage.setItem("tt-theme", "light");
  vi.mocked(useMeta).mockReturnValue({ data: { today: days[0] } } as ReturnType<typeof useMeta>);
  vi.mocked(usePlans).mockReturnValue({ data: fixture(), error: null, refetch: vi.fn() } as unknown as ReturnType<typeof usePlans>);
});

describe("история расписания", () => {
  it("доступна при отсутствии действующего плана, даже если версия всего одна", () => {
    show();
    const button = screen.getByRole("button", { name: "Что менялось: Соколов С.С." });
    expect(button).toBeVisible();
    expect(screen.queryByText("Расписаний на эту неделю нет")).not.toBeInTheDocument();
    fireEvent.click(button);
    expect(screen.getByRole("dialog", { name: "Соколов С.С.: версии плана" })).toBeVisible();
    expect(screen.getByText("Версия 1")).toBeVisible();
  });

  it("ссылка из инбокса сразу открывает нужного сотрудника и показывает изменения задач", () => {
    const latest = { ...base, id: 12, version: 2, tasks: ["Проверить новый сценарий"], edited: true, source_message_version: 2 };
    vi.mocked(usePlans).mockReturnValue({ data: fixture(null, [base, latest]), error: null, refetch: vi.fn() } as unknown as ReturnType<typeof usePlans>);
    show("/plans/2026/46?employee=7");
    const panel = screen.getByRole("dialog", { name: "Соколов С.С.: версии плана" });
    expect(within(panel).getByText("Добавлены задачи · 1")).toBeVisible();
    expect(within(panel).getByText("Убраны задачи · 1")).toBeVisible();
    expect(within(panel).getByText("Проверить новый сценарий")).toBeVisible();
  });

  it("ручную правку датирует действием администратора, а не старым сообщением", () => {
    const manual = { ...base, source: "manual" as const, edited: true, retracted: false };
    vi.mocked(usePlans).mockReturnValue({ data: fixture(manual, [manual]), error: null, refetch: vi.fn() } as unknown as ReturnType<typeof usePlans>);
    show("/plans/2026/46?employee=7");
    expect(screen.getByText(`Правка администратора: ${dateTime(manual.created_at)}`)).toBeVisible();
    expect(screen.queryByText(new RegExp(`Изменено: ${dateTime(base.stated_at!)}`))).not.toBeInTheDocument();
  });
});
