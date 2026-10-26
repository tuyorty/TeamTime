import { Link2, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { api } from "@/api/client";
import { keys, useAdminMutation, useEmployees, useIdentities, useMeta, useTopics } from "@/api/queries";
import type { Identity } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import { relative } from "@/lib/format";

export function TelegramTab() {
  const bot = useMeta().data?.bot_username;
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <Identities />
      <div className="grid content-start gap-5">
        <Topics />
        <Panel title="Как подключить бота">
          <ol className="grid list-decimal gap-1.5 pl-5 text-[13px] text-ink-2">
            <li>Создайте бота у @BotFather и запишите токен в BOT_TOKEN.</li>
            <li>Отключите у бота Privacy Mode (/setprivacy → Disable), чтобы он видел сообщения в темах.</li>
            <li>Добавьте бота в группу-форум администратором с правом ставить реакции.</li>
            <li>
              В теме расписаний отправьте <code className="rounded bg-surface-2 px-1">/bind расписание</code>, в теме
              дейликов — <code className="rounded bg-surface-2 px-1">/bind дейлики</code>.
            </li>
          </ol>
          {bot ? <p className="mt-3 text-[12px] text-ink-3">Бот: @{bot}</p> : null}
        </Panel>
      </div>
    </div>
  );
}

function IdentityRow({ identity }: { identity: Identity }) {
  const employees = useEmployees().data ?? [];
  const [value, setValue] = useState(
    String(identity.employee?.id ?? identity.suggested_employee?.id ?? ""),
  );
  const link = useAdminMutation(
    (employeeId: number | null) => api.put<{ detail: string }>(`/admin/identities/${identity.id}`, { employee_id: employeeId }),
    {
      success: (r) => (r.detail ? `Сохранено. ${r.detail}` : "Сохранено"),
      invalidate: [[...keys.identities], ["inbox"], ["week"], ["month"], ["today"]],
    },
  );
  const changed = String(identity.employee?.id ?? "") !== value;
  return (
    <tr className="border-b border-line last:border-b-0">
      <td className="px-3 py-2">
        <div className="font-medium">{identity.display_name || "без имени"}</div>
        <div className="text-[12px] text-ink-3">
          {identity.username ? `@${identity.username}, ` : ""}id {identity.telegram_user_id}, {relative(identity.last_seen_at)}
        </div>
      </td>
      <td className="px-3 py-2">
        <div className="flex items-center gap-2">
          <Select className="w-48" value={value} onChange={(e) => setValue(e.target.value)} aria-label="Сотрудник">
            <option value="">не привязан</option>
            {employees.map((e) => (
              <option key={e.id} value={e.id}>
                {e.short_name}
              </option>
            ))}
          </Select>
          {changed ? (
            <Button size="sm" variant="primary" onClick={() => link.mutate(value ? Number(value) : null)} disabled={link.isPending}>
              <Link2 /> Сохранить
            </Button>
          ) : null}
        </div>
        {!identity.employee && identity.suggested_employee ? (
          <p className="mt-1 text-[12px] text-deviation-ink">Бот предлагает: {identity.suggested_employee.short_name}</p>
        ) : null}
      </td>
    </tr>
  );
}

function Identities() {
  const { data } = useIdentities();
  const unlinked = data?.filter((i) => !i.employee).length ?? 0;
  return (
    <Panel
      title="Аккаунты Telegram"
      description="Дейлик определяется по отправителю, поэтому аккаунт нужно привязать к сотруднику. После привязки бот переразберёт его сообщения."
      actions={unlinked ? <Badge tone="deviation">не привязано: {unlinked}</Badge> : null}
      bodyClassName="px-0 pb-0"
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] border-collapse text-[13px]">
          <tbody>{data?.map((i) => <IdentityRow key={i.id} identity={i} />)}</tbody>
        </table>
      </div>
      {data && !data.length ? (
        <p className="px-4 pb-4 text-[13px] text-ink-2">Аккаунты появятся, когда кто-то напишет в привязанную тему.</p>
      ) : null}
    </Panel>
  );
}

function Topics() {
  const { data } = useTopics(true);
  const [form, setForm] = useState({ chat_id: "", thread_id: "", kind: "schedule", title: "" });
  const add = useAdminMutation(
    () =>
      api.post("/admin/topics", {
        chat_id: Number(form.chat_id),
        thread_id: form.thread_id ? Number(form.thread_id) : null,
        kind: form.kind,
        title: form.title,
      }),
    { success: "Тема привязана", invalidate: [[...keys.topics]] },
  );
  const remove = useAdminMutation((id: number) => api.delete(`/admin/topics/${id}`), {
    success: "Тема отвязана",
    invalidate: [[...keys.topics]],
  });
  const valid = /^-?\d+$/.test(form.chat_id) && (!form.thread_id || /^\d+$/.test(form.thread_id));
  return (
    <Panel title="Темы форума" description="Какая тема за что отвечает. Проще всего привязать командой /bind в самой теме.">
      <ul className="mb-3 grid gap-1.5">
        {data?.map((t) => (
          <li key={t.id} className="flex items-center gap-2 text-[13px]">
            <Badge tone={t.kind === "schedule" ? "accent" : "absence"}>{t.kind === "schedule" ? "расписание" : "дейлики"}</Badge>
            <span className="min-w-0 truncate">
              {t.title || "без названия"}
              <span className="text-ink-3">
                , {t.chat_title || t.chat_id}
                {t.thread_id ? `, тема ${t.thread_id}` : ""}
              </span>
            </span>
            <Button size="icon-sm" variant="ghost" className="ml-auto" aria-label="Отвязать тему" onClick={() => remove.mutate(t.id)}>
              <Trash2 />
            </Button>
          </li>
        ))}
        {data && !data.length ? <li className="text-[13px] text-ink-2">Пока ни одной темы.</li> : null}
      </ul>
      <form
        className="grid gap-2 border-t border-line pt-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate(undefined, { onSuccess: () => setForm({ chat_id: "", thread_id: "", kind: "schedule", title: "" }) });
        }}
      >
        <Field label="ID чата" hint="Вида -100…">
          <Input value={form.chat_id} onChange={(e) => setForm({ ...form, chat_id: e.target.value })} />
        </Field>
        <Field label="ID темы" hint="Пусто — весь чат">
          <Input value={form.thread_id} onChange={(e) => setForm({ ...form, thread_id: e.target.value })} />
        </Field>
        <Field label="Тип">
          <Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            <option value="schedule">расписание</option>
            <option value="daily">дейлики</option>
          </Select>
        </Field>
        <Field label="Название">
          <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </Field>
        <div className="flex justify-end sm:col-span-2">
          <Button type="submit" size="sm" disabled={!valid || add.isPending}>
            <Plus /> Привязать
          </Button>
        </div>
      </form>
    </Panel>
  );
}
