import type { Page } from "@playwright/test";

import type { DayCell, EmployeeBrief, Inbox, Message, Meta, PlanDay, Plans, PlanVersion } from "../src/api/types";

export const reviewEmployee: EmployeeBrief = {
  id: 701, full_name: "Соколов Степан Сергеевич", short_name: "Соколов С.С.",
  position: "Инженер", department: "software", color: "", avatar_url: "", is_active: true,
};
export const reviewDay = "2026-11-10";
export const reviewOldText = "#расписание\nСпринт 09.11 — 15.11\nСоколов С.С.\nВт: 10:00 — 18:00\n- Проверить учебный стенд";
export const reviewNewText = "#расписание\nСпринт 09.11 — 15.11\nСоколов С.С.\nВт: выходной\n- Подготовить демонстрационный отчёт";
export const manualApprovalNote = "После этой версии расписание исправлено вручную. Одобрение сообщения не заменит ручной план; при необходимости измените день в таблице.";

/** Полностью вымышленные сообщения. Ответы и изменения живут только в памяти браузерного теста. */
export function scheduleReviewData() {
  const days = ["2026-11-09", reviewDay, "2026-11-11", "2026-11-12", "2026-11-13", "2026-11-14", "2026-11-15"];
  const work: PlanDay = {
    kind: "work", start: 36000, end: 64800, planned_sec: 28800, intervals: [[36000, 64800]],
    note: null, note_has_time: false, raw_line: "Вт: 10:00 — 18:00",
  };
  const off: PlanDay = { kind: "off", start: null, end: null, planned_sec: 0, intervals: [], note: null, note_has_time: false, raw_line: "Вт: выходной" };
  const cell: DayCell = {
    date: reviewDay, state: "missing", status: null, status_label: null, status_note: null,
    plan: work, fact: null, late_sec: null, early_leave_sec: null, undertime_sec: null, no_plan: false,
    flags: [], source: { plan_id: 301, plan_version: 1, plan_message_version_id: 101, plan_raw_message_id: 10 },
    no_show: null, can_confirm_no_show: true,
  };
  const message: Message = {
    id: 10, chat_id: -12345, message_id: 77, thread_id: 1, author_name: reviewEmployee.full_name,
    author_tg_id: 7001, sent_at: "2026-11-08T10:00:00+05:00", source: "telegram", telegram_link: null,
    versions: [
      { id: 101, version: 1, text: reviewOldText, edited_at: null, received_at: "2026-11-08T10:00:01+05:00" },
      { id: 102, version: 2, text: reviewNewText, edited_at: "2026-11-11T09:00:00+05:00", received_at: "2026-11-11T09:00:01+05:00" },
    ],
    parses: [
      { id: 201, message_version_id: 101, version: 1, parser_version: 1, kind: "schedule", status: "ok", resolution: "accepted", issues: [], data: null, employee: reviewEmployee, employee_unresolved: false, created_at: "2026-11-12T15:00:00+05:00", is_latest: false },
      {
        id: 202, message_version_id: 102, version: 2, parser_version: 1, kind: "schedule", status: "partial", resolution: "pending",
        issues: [{ code: "late_change", severity: "warning", message: "Расписание на Вт 10.11 изменено после начала дня. До решения администратора действует прежний план." }],
        data: { iso_year: 2026, iso_week: 46, sprint_start: days[0], sprint_end: days[6], person: { raw: reviewEmployee.short_name }, days: [[reviewDay, off]], tasks: ["Подготовить демонстрационный отчёт"] },
        employee: reviewEmployee, employee_unresolved: false, created_at: "2026-11-12T15:01:00+05:00", is_latest: true,
      },
    ],
  };
  const first: PlanVersion = {
    id: 301, version: 1, created_at: "2026-11-12T15:00:00+05:00", source: "telegram", created_by: "bot",
    edited: false, retracted: true, days: [[reviewDay, work]], tasks: ["Проверить учебный стенд"],
    message_version_id: 101, raw_message_id: 10, stated_at: message.sent_at, source_message_version: 1,
  };
  const second: PlanVersion = {
    ...first, id: 302, version: 2, created_at: "2026-11-12T15:01:00+05:00", edited: true,
    days: [[reviewDay, off]], tasks: ["Подготовить демонстрационный отчёт"], message_version_id: 102,
    stated_at: message.versions[1]!.edited_at, source_message_version: 2,
  };
  const plans: Plans = {
    iso_year: 2026, iso_week: 46, label: "46 неделя", week_start: days[0]!, days, required_days: days.slice(0, 6),
    rows: [{ employee: reviewEmployee, current: null, versions: [first, second], done_tasks: [], days_with_daily: 0, days_planned: 0 }],
  };
  const inbox: Inbox = {
    counts: { pending: 1, resolved: 0, auto: 0 }, total: 1,
    items: [{
      parse: message.parses[1]!, message, candidates: [],
      plan_change: {
        plan_id: 302, version: 2, previous_version: 1, late_change: true,
        tasks_added: second.tasks, tasks_removed: first.tasks,
        days: [{ date: reviewDay, previous: work, submitted: off, current: cell, if_accepted: { ...cell, state: "off", plan: off, can_confirm_no_show: false }, affects_calculation: true }],
      },
    }],
  };
  return { message, plans, inbox, cell };
}

export async function mockScheduleReview(page: Page, options: { admin?: boolean; manualPlan?: boolean } = {}) {
  const data = scheduleReviewData();
  if (options.manualPlan) {
    const previous = data.plans.rows[0]!.versions[1]!;
    const manual: PlanVersion = {
      ...previous, id: 303, version: 3, source: "manual", created_by: "Администратор демо",
      retracted: false, days: [[reviewDay, data.cell.plan!]],
      created_at: "2026-11-12T16:00:00+05:00", stated_at: "2026-11-12T16:00:00+05:00",
    };
    data.plans.rows[0]!.current = manual;
    data.plans.rows[0]!.versions.push(manual);
    data.cell.source = { ...data.cell.source, plan_id: manual.id, plan_version: manual.version };
    const comparison = data.inbox.items[0]!.plan_change!.days[0]!;
    comparison.if_accepted = { ...data.cell };
    comparison.affects_calculation = false;
    comparison.approval_note = manualApprovalNote;
  }
  const saved: { reason: string; expected_plan_id: number; expected_seconds: number }[] = [];
  const unexpected: string[] = [];
  const meta: Meta = {
    version: "demo", demo: true, admin_enabled: true, is_admin: options.admin ?? true,
    timezone: "Asia/Yekaterinburg", today: "2026-11-13", now: "2026-11-13T12:00:00+05:00",
    bot_username: null, late_tolerance_min: 15, weekly_off: [6],
  };
  await page.clock.setFixedTime(new Date(meta.now));
  // Ни один API-запрос этого сценария не попадает в настоящую базу, в том числе POST.
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname.replace("/api/v1", "");
    if (request.method() === "POST" && pathname === `/admin/days/${reviewEmployee.id}/${reviewDay}/no-show`) {
      const payload = request.postDataJSON() as (typeof saved)[number];
      saved.push(payload);
      data.cell.no_show = { id: 501, plan_id: 301, seconds: 28800, intervals: [[36000, 64800]], reason: payload.reason, created_by: "Администратор демо", created_at: meta.now };
      data.cell.late_sec = 28800;
      data.cell.flags = ["no_show_confirmed"];
      data.cell.state = "absence";
      data.cell.can_confirm_no_show = false;
      const accepted = data.inbox.items[0]!.plan_change!.days[0]!.if_accepted;
      accepted.no_show = data.cell.no_show;
      accepted.late_sec = data.cell.late_sec;
      accepted.flags = ["no_show_confirmed"];
      accepted.state = "absence";
      return route.fulfill({ json: { ...data.cell.no_show, employee_id: reviewEmployee.id, date: reviewDay, retracted_at: null } });
    }
    if (request.method() !== "GET") {
      unexpected.push(`${request.method()} ${pathname}`);
      return route.fulfill({ status: 400, json: { detail: "Непредусмотренное действие теста" } });
    }
    if (pathname === "/meta") return route.fulfill({ json: meta });
    if (pathname === "/team/session") return route.fulfill({ json: { enabled: false, module_enabled: false, module_available: false, demo: true, actor: null } });
    if (pathname === "/inbox") return route.fulfill({ json: data.inbox });
    if (pathname === "/employees") return route.fulfill({ json: [reviewEmployee] });
    if (pathname === "/identities" || pathname === "/admin/chats") return route.fulfill({ json: [] });
    if (pathname === "/admin/status-requests") return route.fulfill({ json: { items: [], total: 0, pending: 0 } });
    if (pathname === "/plans/2026/46") return route.fulfill({ json: data.plans });
    if (pathname === "/messages/10") return route.fulfill({ json: data.message });
    if (pathname === "/events") return route.fulfill({ status: 204 });
    unexpected.push(`${request.method()} ${pathname}`);
    return route.fulfill({ status: 404, json: { detail: "Нет ответа в тестовой фикстуре" } });
  });
  return { ...data, saved, unexpected };
}
