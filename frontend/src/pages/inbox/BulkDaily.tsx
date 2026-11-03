import { useState } from "react";

import { api } from "@/api/client";
import { useAdminMutation, useChats, useEmployees } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input, Select, Switch } from "@/components/ui/field";
import { count, dateTime } from "@/lib/format";

type Target = "missing_efficiency" | "no_time";
interface Preview { parse_ids: number[]; count: number; samples: { id: number; author: string; sent_at: string; text: string }[] }

export function BulkDaily() {
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState<Target>("missing_efficiency");
  const [employee, setEmployee] = useState("");
  const [chat, setChat] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [importOnly, setImportOnly] = useState(true);
  const [preview, setPreview] = useState<Preview | null>(null);
  const employees = useEmployees(true).data ?? [];
  const chats = useChats().data ?? [];
  const check = useAdminMutation(() => api.post<Preview>("/admin/inbox/bulk/preview", {
    target, employee_id: employee ? Number(employee) : null, chat_id: chat ? Number(chat) : null,
    start: start || null, end: end || null, import_only: importOnly,
  }));
  const apply = useAdminMutation(() => api.post<{ detail: string }>("/admin/inbox/bulk/apply", { target, parse_ids: preview!.parse_ids }), { success: (r) => r.detail });
  const resetPreview = () => setPreview(null);
  return <>
    <Button size="sm" onClick={() => { setOpen(true); resetPreview(); }}>Массовая обработка дейликов</Button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent title="Старые дейлики" className="max-h-[90dvh] overflow-y-auto">
        <p className="mb-4 text-[13px] text-ink-2">Эффективность останется неизвестной. Время работы не подставляется; зачтённые часы и начисления не меняются. Сначала проверьте выборку.</p>
        <fieldset disabled={check.isPending || apply.isPending} onChange={resetPreview} className="grid gap-3">
          <Field label="Что обработать"><Select value={target} onChange={(event) => setTarget(event.target.value as Target)}>
            <option value="missing_efficiency">Только нет эффективности — подтвердить как есть</option>
            <option value="no_time">Нет времени работы — закрыть без начисления часов</option>
          </Select></Field>
          <Field label="Сотрудник"><Select value={employee} onChange={(event) => setEmployee(event.target.value)}><option value="">Все сотрудники</option>{employees.map((e) => <option key={e.id} value={e.id}>{e.short_name}</option>)}</Select></Field>
          <Field label="Беседа"><Select value={chat} onChange={(event) => setChat(event.target.value)}><option value="">Все беседы</option>{chats.map((c) => <option key={c.chat_id} value={c.chat_id}>{c.title}</option>)}</Select></Field>
          <div className="grid grid-cols-2 gap-3"><Field label="Сообщения с"><Input type="date" value={start} onChange={(event) => setStart(event.target.value)} /></Field><Field label="Сообщения по"><Input type="date" value={end} onChange={(event) => setEnd(event.target.value)} /></Field></div>
          <Switch checked={importOnly} onChange={(value) => { setImportOnly(value); resetPreview(); }} label="Только импортированные сообщения" />
        </fieldset>
        <Button className="mt-4" disabled={check.isPending || apply.isPending || !!(start && end && end < start)} onClick={() => check.mutate(undefined, { onSuccess: setPreview })}>{check.isPending ? "Подбираем…" : "Предпросмотр выборки"}</Button>
        {preview ? <div className="mt-4 grid gap-3" aria-label="Предпросмотр массовой обработки">
          <p className="font-semibold">Подходит записей: {preview.count}</p>
          <p className="text-[12px] text-ink-2">Учитывается вся выборка, включая другие страницы инбокса. Записи с другими ошибками не подтверждаются действием «Только нет эффективности».</p>
          <ul className="grid gap-2">{preview.samples.map((sample) => <li key={sample.id} className="rounded border border-line p-2 text-[12px]"><p className="font-medium">{sample.author} · {dateTime(sample.sent_at)}</p><p className="mt-1 whitespace-pre-wrap break-words text-ink-2">{sample.text}</p></li>)}</ul>
          <Button variant="primary" disabled={!preview.count || apply.isPending} onClick={() => apply.mutate(undefined, { onSuccess: () => { setOpen(false); resetPreview(); } })}>Закрыть {count(preview.count, ["запись", "записи", "записей"])} без изменения часов</Button>
        </div> : null}
      </DialogContent>
    </Dialog>
  </>;
}
