import { expect, type APIRequestContext } from "@playwright/test";

import type { Identity, InboxItem, Plans, Today } from "../src/api/types";
import { hm, isoWeek, parseDate } from "../src/lib/format";

/** Только вымышленные данные отдельного демо-стенда; никаких обращений в Telegram. */
export async function lateScheduleExample(request: APIRequestContext) {
  const today: Today = await (await request.get("/api/v1/today")).json();
  const identities: Identity[] = await (await request.get("/api/v1/identities")).json();
  const week = isoWeek(parseDate(today.date));
  const plans: Plans = await (await request.get(`/api/v1/plans/${week.year}/${week.week}`)).json();
  const target = plans.rows.find(
    (row) =>
      row.current?.days.some(
        ([day, plan]) => day === today.date && plan.kind === "work" && plan.start !== null && plan.start <= 12 * 3600,
      ) &&
      identities.some((identity) => identity.employee?.id === row.employee.id) &&
      today.rows.some(
        (item) =>
          item.employee.id === row.employee.id &&
          item.cell.plan?.kind === "work" &&
          (!item.cell.status || item.cell.status === "remote"),
      ),
  );
  expect(target?.current?.raw_message_id).toBeTruthy();
  const identity = identities.find((item) => item.employee?.id === target!.employee.id)!;
  const raw = await (await request.get(`/api/v1/messages/${target!.current!.raw_message_id}`)).json();
  const version = raw.versions.at(-1);
  const weekday = new Date(`${today.date}T12:00:00Z`).getUTCDay();
  const names = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];
  const oldDay = target!.current!.days.find(([day]) => day === today.date)![1];
  const start = (oldDay.start ?? 10 * 3600) + 3600;
  const text: string = version.text.replace(
    new RegExp(`^${names[weekday]}:.*$`, "im"),
    `${names[weekday]}: ${hm(start)} - ${hm(start + 8 * 3600)}`,
  );
  expect(text).not.toBe(version.text);
  const [year, month, day] = today.date.split("-");
  const daily = await request.post("/api/v1/demo/messages", {
    data: {
      telegram_user_id: identity.telegram_user_id,
      topic: "daily",
      text: `${day}.${month}.${year}\n${hm(start - 1800)} - ${hm(start + 7 * 3600)}\nЭффективность: 80%\n\n- проверка вымышленного примера\n\n#дейли`,
    },
  });
  expect(daily.ok()).toBeTruthy();
  const edited = await request.post("/api/v1/demo/messages", {
    data: {
      telegram_user_id: identity.telegram_user_id,
      topic: "schedule",
      text,
      edit_raw_message_id: target!.current!.raw_message_id,
    },
  });
  expect(edited.ok()).toBeTruthy();
  const inbox: { items: InboxItem[] } = await (
    await request.get(`/api/v1/inbox?employee=${target!.employee.id}&kind=schedule`)
  ).json();
  const item = inbox.items.find(
    (item) => item.message.id === target!.current!.raw_message_id && item.plan_change?.late_change,
  )!;
  expect(item?.plan_change).toBeTruthy();
  return { item, employee: target!.employee, date: today.date };
}
