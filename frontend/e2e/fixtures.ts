import { expect, type APIRequestContext, type Page } from "@playwright/test";

import type { Identity, InboxItem, Message, Meta, Plans, Today } from "../src/api/types";
import { isoWeek, parseDate } from "../src/lib/format";

/** Три цветные области помогают проверить, какой участок сохранился после кадрирования. */
export async function avatarFixture(page: Page) {
  const image: string = await page.evaluate(`(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 900;
    canvas.height = 600;
    const context = canvas.getContext('2d');
    ['#dc3242', '#149462', '#2864dc'].forEach((color, index) => {
      context.fillStyle = color;
      context.fillRect(index * 300, 0, 300, 600);
    });
    return canvas.toDataURL('image/png');
  })()`);
  return { name: "demo-avatar.png", mimeType: "image/png", buffer: Buffer.from(image.split(",")[1]!, "base64") };
}

/** Только вымышленные данные отдельного демо-стенда; никаких обращений в Telegram. */
export async function lateScheduleExample(request: APIRequestContext) {
  const meta: Meta = await (await request.get("/api/v1/meta")).json();
  expect(meta.demo, "Пример поздней правки разрешён только на демо-стенде").toBe(true);
  const login = await request.post("/api/v1/auth/login", { data: { password: "demo" } });
  expect(login.ok()).toBeTruthy();
  const today: Today = await (await request.get("/api/v1/today")).json();
  const identities: Identity[] = await (await request.get("/api/v1/identities")).json();
  const week = isoWeek(parseDate(today.date));
  const plans: Plans = await (await request.get(`/api/v1/plans/${week.year}/${week.week}`)).json();
  const target = plans.rows.flatMap((row) => {
    const source = row.versions.find((version) =>
      (version.source === "demo" || version.source === "telegram") && version.raw_message_id &&
      version.days.some(([day, plan]) => day === today.date && plan.kind === "work"),
    );
    return source ? [{ row, source }] : [];
  }).find(
    ({ row }) =>
      identities.some((identity) => identity.employee?.id === row.employee.id) &&
      today.rows.some(
        (item) =>
          item.employee.id === row.employee.id &&
          !item.cell.no_show &&
          (!item.cell.status || item.cell.status === "remote"),
      ),
  );
  expect(target, "Нужен сотрудник с исходным демо-расписанием и без отсутствия в выбранный день").toBeDefined();
  const { row, source } = target!;
  const identity = identities.find((item) => item.employee?.id === row.employee.id)!;
  const raw: Message = await (await request.get(`/api/v1/messages/${source.raw_message_id}`)).json();
  const version = raw.versions.find((item) => item.id === source.message_version_id)!;
  expect(version, "Нужен текст выбранной исходной версии расписания").toBeDefined();
  const weekday = new Date(`${today.date}T12:00:00Z`).getUTCDay();
  const names = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];
  const dayLine = new RegExp(`^${names[weekday]}:.*$`, "im");
  expect(version.text).toMatch(dayLine);
  const baseText = version.text.replace(dayLine, `${names[weekday]}: 10:00 - 18:00`);
  // Каждый запуск начинает с тех же часов. Новый пример не зависит от правок админа
  // и результатов прошлых прогонов; одобрение явно делает 10–18 действующим планом.
  const baseline = await request.post("/api/v1/demo/messages", {
    data: { telegram_user_id: identity.telegram_user_id, topic: "schedule", text: baseText },
  });
  expect(baseline.ok()).toBeTruthy();
  const { raw_message_id: messageId } = await baseline.json() as { raw_message_id: number };
  expect(messageId).toBeTruthy();
  const baselineMessage: Message = await (await request.get(`/api/v1/messages/${messageId}`)).json();
  const baselineParse = baselineMessage.parses.find((parse) => parse.is_latest)!;
  expect(baselineParse.kind).toBe("schedule");
  expect(baselineParse.employee?.id).toBe(row.employee.id);
  const accepted = await request.post(`/api/v1/admin/inbox/${baselineParse.id}/resolve`, {
    data: { resolution: "accepted", reason: "Исходный план вымышленного e2e-примера" },
    headers: { "X-Requested-With": "teamtime" },
  });
  expect(accepted.ok()).toBeTruthy();
  const text = baseText.replace(dayLine, `${names[weekday]}: 11:00 - 19:00`);
  const [year, month, day] = today.date.split("-");
  const daily = await request.post("/api/v1/demo/messages", {
    data: {
      telegram_user_id: identity.telegram_user_id,
      topic: "daily",
      text: `${day}.${month}.${year}\n10:30 - 18:00\nЭффективность: 80%\n\n- проверка вымышленного примера\n\n#дейли`,
    },
  });
  expect(daily.ok()).toBeTruthy();
  const edited = await request.post("/api/v1/demo/messages", {
    data: {
      telegram_user_id: identity.telegram_user_id,
      topic: "schedule",
      text,
      edit_raw_message_id: messageId,
    },
  });
  expect(edited.ok()).toBeTruthy();
  const inbox: { items: InboxItem[] } = await (
    await request.get(`/api/v1/inbox?employee=${row.employee.id}&kind=schedule`)
  ).json();
  const item = inbox.items.find(
    (item) => item.message.id === messageId && item.plan_change?.late_change,
  )!;
  expect(item?.plan_change).toBeTruthy();
  const change = item.plan_change!.days.find((day) => day.date === today.date)!;
  expect(change.current.late_sec).toBe(1800);
  expect(change.if_accepted.late_sec).toBe(0);
  return { item, employee: row.employee, date: today.date };
}
