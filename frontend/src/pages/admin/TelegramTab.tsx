import { Check, Link2, Plus, ShieldOff, Trash2 } from "lucide-react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { DEPARTMENTS, type Department } from "@/lib/departments";

import { api } from "@/api/client";
import { keys, useAdminMutation, useChats, useEmployees, useIdentities, useMeta, useTopics } from "@/api/queries";
import type { Chat, Identity } from "@/api/types";
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
        <Chats />
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
            <li>Разрешите группу выше, в разделе «Чаты». Из неразрешённых чатов бот сообщения не принимает.</li>
          </ol>
          {bot ? <p className="mt-3 text-[12px] text-ink-3">Бот: @{bot}</p> : null}
        </Panel>
      </div>
    </div>
  );
}

function IdentityRow({ identity }: { identity: Identity }) {
  const [confirmRemove, setConfirmRemove] = useState(false);
  const remove = useAdminMutation(() => api.delete<{ detail: string }>(`/admin/identities/${identity.id}`), { success: (r) => r.detail });
  const restore = useAdminMutation(() => api.post<{ detail: string }>(`/admin/identities/${identity.id}/restore`), { success: (r) => r.detail });
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
        {identity.removed_at ? <Button size="sm" onClick={() => restore.mutate(undefined)} disabled={restore.isPending}>Восстановить аккаунт</Button> : <div className="flex items-center gap-2">
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
          {!identity.employee ? <Button size="icon-sm" variant="ghost" aria-label={`Удалить аккаунт ${identity.display_name}`} onClick={() => setConfirmRemove(true)}><Trash2 /></Button> : null}
        </div>}
        <Dialog open={confirmRemove} onOpenChange={setConfirmRemove}>
          <DialogContent title={`Удалить аккаунт ${identity.display_name}?`}>
            <p className="text-[13px] text-ink-2">Аккаунт исчезнет из списка, его новые сообщения будут игнорироваться. Повторный импорт не вернёт его обратно. Исходные сообщения сохранятся; восстановить аккаунт можно в списке удалённых.</p>
            <div className="mt-4 flex justify-end gap-2">
              <Button onClick={() => setConfirmRemove(false)}>Отмена</Button>
              <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(undefined, { onSuccess: () => setConfirmRemove(false) })}>Удалить аккаунт</Button>
            </div>
          </DialogContent>
        </Dialog>
        {!identity.employee && identity.suggested_employee ? (
          <p className="mt-1 text-[12px] text-deviation-ink">Бот предлагает: {identity.suggested_employee.short_name}</p>
        ) : null}
      </td>
    </tr>
  );
}

function Identities() {
  const [showRemoved, setShowRemoved] = useState(false);
  const active = useIdentities();
  const removed = useQuery({ queryKey: ["identities", "removed"], queryFn: () => api.get<Identity[]>("/admin/identities/removed"), enabled: showRemoved });
  const data = showRemoved ? removed.data : active.data;
  const unlinked = data?.filter((i) => !i.employee).length ?? 0;
  return (
    <Panel
      title="Аккаунты Telegram"
      description="Дейлик определяется по отправителю, поэтому аккаунт нужно привязать к сотруднику. После привязки бот переразберёт его сообщения."
      actions={unlinked ? <Badge tone="deviation">не привязано: {unlinked}</Badge> : null}
      bodyClassName="px-0 pb-0"
    >
      <div className="px-4 pb-3"><Button size="sm" onClick={() => setShowRemoved(!showRemoved)}>{showRemoved ? "Действующие аккаунты" : "Удалённые аккаунты"}</Button></div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] border-collapse text-[13px]">
          <tbody>{data?.map((i) => <IdentityRow key={i.id} identity={i} />)}</tbody>
        </table>
      </div>
      {data && !data.length ? (
        <p className="px-4 pb-4 text-[13px] text-ink-2">{showRemoved ? "Удалённых аккаунтов нет." : "Аккаунты появятся, когда кто-то напишет в привязанную тему."}</p>
      ) : null}
    </Panel>
  );
}

function ChatRow({ chat }: { chat: Chat }) {
  const [confirm, setConfirm] = useState(false);
  const [department, setDepartment] = useState<Department | "">(chat.department ?? "");
  const [confirmDepartment, setConfirmDepartment] = useState(false);
  const setChatDepartment = useAdminMutation(() => api.put<{ detail: string }>(`/admin/chats/${chat.chat_id}/department`, { department: department || null }), { success: (r) => r.detail });
  const invalidate = [[...keys.chats], [...keys.topics]];
  const approve = useAdminMutation((approved: boolean) => api.put<{ detail: string }>(`/admin/chats/${chat.chat_id}`, { approved }), {
    success: (r) => r.detail,
    invalidate,
  });
  const remove = useAdminMutation(() => api.delete<{ detail: string }>(`/admin/chats/${chat.chat_id}`), {
    success: (r) => r.detail,
    invalidate,
  });
  return (
    <li className="grid gap-2 rounded-md border border-line p-2.5 text-[13px]">
      <div className="flex flex-wrap items-center gap-2">
        <Select aria-label={`Отдел чата ${chat.title}`} value={department} onChange={(event) => setDepartment(event.target.value as Department | "")}>
          <option value="">Отдел не задан</option>
          {Object.entries(DEPARTMENTS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </Select>
        <Button size="sm" disabled={setChatDepartment.isPending} onClick={() => setConfirmDepartment(true)}>Применить отдел</Button>
      </div>
      <Dialog open={confirmDepartment} onOpenChange={setConfirmDepartment}>
        <DialogContent title="Отдел сотрудников чата">
          <p className="text-[13px] text-ink-2">{department ? `Назначить отдел «${DEPARTMENTS[department]}» сотрудникам, определённым по сообщениям беседы «${chat.title}»? Он также будет назначаться при первом распознавании новых сотрудников из этой беседы.` : "Убрать назначение отдела по этому чату? Отделы существующих сотрудников сохранятся."}</p>
          <div className="mt-4 flex justify-end gap-2"><Button onClick={() => setConfirmDepartment(false)}>Отмена</Button><Button variant="primary" onClick={() => setChatDepartment.mutate(undefined, { onSuccess: () => setConfirmDepartment(false) })}>Применить</Button></div>
        </DialogContent>
      </Dialog>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={chat.approved ? "accent" : "deviation"}>{chat.approved ? "разрешён" : "ждёт разрешения"}</Badge>
        <span className="min-w-0 truncate font-medium">{chat.title || "Без названия"}</span>
        <span className="text-[12px] text-ink-3 tnum">
          {chat.chat_id}, тем: {chat.topics}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {chat.approved ? (
          <Button size="sm" variant="ghost" disabled={approve.isPending} onClick={() => approve.mutate(false)}>
            <ShieldOff /> Запретить
          </Button>
        ) : (
          <Button size="sm" variant="primary" disabled={approve.isPending} onClick={() => approve.mutate(true)}>
            <Check /> Разрешить
          </Button>
        )}
        {confirm ? (
          <>
            <span className="text-[12px] text-ink-2">Удалить чат и его темы?</span>
            <Button size="sm" variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(undefined)}>
              Удалить
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirm(false)}>
              Нет
            </Button>
          </>
        ) : (
          <Button size="icon-sm" variant="ghost" className="ml-auto" aria-label="Удалить чат" onClick={() => setConfirm(true)}>
            <Trash2 />
          </Button>
        )}
      </div>
    </li>
  );
}

/** Бот публичный: добавить его в группу может кто угодно, поэтому чаты разрешает админ. */
function Chats() {
  const { data } = useChats();
  const pending = data?.filter((c) => !c.approved).length ?? 0;
  return (
    <Panel
      title="Чаты"
      description="Бот принимает сообщения только из разрешённых групп. Разрешайте рабочие беседы компании."
      actions={pending ? <Badge tone="deviation">{pending} ждут</Badge> : undefined}
    >
      <ul className="grid gap-2">
        {data?.map((c) => <ChatRow key={c.chat_id} chat={c} />)}
        {data && !data.length ? (
          <li className="text-[13px] text-ink-2">Бот ещё не добавлен ни в одну группу. Добавьте его и отправьте /bind в теме.</li>
        ) : null}
      </ul>
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
    { success: "Тема привязана, чат разрешён", invalidate: [[...keys.topics], [...keys.chats]] },
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
