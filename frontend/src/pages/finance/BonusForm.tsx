import { useState } from "react";

import { api } from "@/api/client";
import { useAdminMutation, useEmployees } from "@/api/queries";
import type { ProjectBonus } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/field";

/** getRandomValues работает и по HTTP в локальной сети, где randomUUID недоступен. */
function requestId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6]! & 15) | 64;
  bytes[8] = (bytes[8]! & 63) | 128;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function BonusForm({ month, label, employeeId, bonus, onClose }: {
  month: string; label: string; employeeId?: number; bonus?: ProjectBonus; onClose: () => void;
}) {
  const employees = useEmployees(true);
  const [id] = useState(requestId);
  const [employee, setEmployee] = useState(String(bonus?.employee_id ?? employeeId ?? ""));
  const [title, setTitle] = useState(bonus?.title ?? "");
  const [amount, setAmount] = useState(bonus?.amount ?? "");
  const [note, setNote] = useState(bonus?.note ?? "");
  const mutation = useAdminMutation(async () => {
    const values = { title: title.trim(), amount: amount.replace(",", "."), note: note.trim() };
    return bonus
      ? api.put(`/admin/bonuses/${bonus.id}`, { ...values, version: bonus.version })
      : api.post("/admin/bonuses", { ...values, request_id: id, employee_id: Number(employee), month });
  }, { success: bonus ? "Премия исправлена" : "Премия добавлена", invalidate: [["finances"], ["audit"]] });
  return (
    <Dialog open onOpenChange={(open) => { if (!open && !mutation.isPending) onClose(); }}>
      <DialogContent title={bonus ? "Изменить премию" : "Добавить премию"} description={`В расчёт за ${label.toLocaleLowerCase("ru-RU")}`} className="max-h-[80dvh] overflow-y-auto">
        <form className="grid gap-4" onSubmit={(event) => { event.preventDefault(); mutation.mutate(undefined, { onSuccess: onClose }); }}>
          <Field label="Сотрудник">
            <Select value={employee} onChange={(event) => setEmployee(event.target.value)} required disabled={!!bonus || employees.isPending || mutation.isPending}>
              <option value="">Выберите сотрудника</option>
              {employees.data?.map((e) => <option key={e.id} value={e.id}>{e.full_name}{e.is_active ? "" : " · в архиве"}</option>)}
            </Select>
          </Field>
          {employees.error ? <p role="alert" className="text-[13px] text-late-ink">Не удалось загрузить сотрудников. <Button variant="link" onClick={() => void employees.refetch()}>Повторить</Button></p> : null}
          <Field label="Проект / основание"><Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Например, запуск личного кабинета" required maxLength={200} disabled={mutation.isPending} /></Field>
          <Field label="Сумма, ₽"><Input value={amount} onChange={(event) => setAmount(event.target.value.replace(/\s/g, ""))} inputMode="decimal" placeholder="10000" pattern="[0-9]+([.,][0-9]{1,2})?" title="Положительная сумма, до двух знаков после запятой" required disabled={mutation.isPending} /></Field>
          <Field label="Комментарий" hint="Необязательно: что завершено и за что назначена премия."><Textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={1000} disabled={mutation.isPending} /></Field>
          {mutation.error ? <p role="alert" className="text-[13px] text-late-ink">{mutation.error.message}</p> : null}
          <div className="flex justify-end gap-2"><Button onClick={onClose} disabled={mutation.isPending}>Закрыть</Button><Button type="submit" variant="primary" disabled={mutation.isPending || !employee || !title.trim() || !Number(amount.replace(",", ".")) || !!employees.error}>{mutation.isPending ? "Сохраняем…" : "Сохранить премию"}</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function CancelBonus({ bonus, onClose }: { bonus: ProjectBonus; onClose: () => void }) {
  const [reason, setReason] = useState("");
  const mutation = useAdminMutation(() => api.post(`/admin/bonuses/${bonus.id}/cancel`, { version: bonus.version, reason: reason.trim() }),
    { success: "Премия отменена", invalidate: [["finances"], ["audit"]] });
  return (
    <Dialog open onOpenChange={(open) => { if (!open && !mutation.isPending) onClose(); }}>
      <DialogContent title="Отменить премию" description={`«${bonus.title}» перестанет учитываться в сумме. Запись останется в истории.`}>
        <form className="grid gap-4" onSubmit={(event) => { event.preventDefault(); mutation.mutate(undefined, { onSuccess: onClose }); }}>
          <Field label="Причина отмены"><Textarea value={reason} onChange={(event) => setReason(event.target.value)} required maxLength={500} disabled={mutation.isPending} /></Field>
          {mutation.error ? <p role="alert" className="text-[13px] text-late-ink">{mutation.error.message}</p> : null}
          <div className="flex justify-end gap-2"><Button onClick={onClose} disabled={mutation.isPending}>Оставить премию</Button><Button variant="danger" type="submit" disabled={!reason.trim() || mutation.isPending}>Отменить премию</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
