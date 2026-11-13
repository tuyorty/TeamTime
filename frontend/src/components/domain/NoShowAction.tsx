import { AlertTriangle, UserX } from "lucide-react";
import { useState } from "react";

import { api } from "@/api/client";
import { useAdminMutation } from "@/api/queries";
import type { DayCell } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Field, Textarea } from "@/components/ui/field";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { cn } from "@/lib/cn";
import { dateTime, dayMonth, hm, span } from "@/lib/format";

/** Решение о невыходе принимается отдельно от правки расписания и отсутствия дейлика. */
export function NoShowAction({ employeeId, cell }: { employeeId: number; cell: DayCell }) {
  return (
    <NoShowForm
      key={`${employeeId}:${cell.date}:${cell.source.plan_id}:${cell.plan?.planned_sec}:${cell.no_show?.id ?? "new"}`}
      employeeId={employeeId}
      cell={cell}
    />
  );
}

function NoShowForm({ employeeId, cell }: { employeeId: number; cell: DayCell }) {
  const admin = useIsAdmin();
  const [editing, setEditing] = useState(false);
  const [reason, setReason] = useState("");
  const existing = cell.no_show;
  const conflict = cell.flags.includes("no_show_conflict");
  const planId = cell.source.plan_id;
  const seconds = cell.plan?.planned_sec;
  // Сервер учитывает конец всех интервалов, ночную смену, факт и согласованные статусы.
  const eligible = !!cell.can_confirm_no_show && !!planId && !!seconds && cell.plan?.kind === "work";
  const endpoint = `/admin/days/${employeeId}/${cell.date}/no-show`;
  const save = useAdminMutation(
    () => existing
      ? api.post(`${endpoint}/cancel`, { reason: reason.trim(), expected_id: existing.id })
      : api.post(endpoint, { reason: reason.trim(), expected_plan_id: planId, expected_seconds: seconds }),
    { success: existing ? "Подтверждение невыхода отменено" : "Невыход подтверждён. Итоги пересчитаны" },
  );

  if (!existing && (!admin || !eligible)) return null;

  return (
    <section className={cn("grid gap-3 rounded-lg border p-3 text-[13px]", conflict ? "border-deviation/40 bg-deviation-soft/30" : "border-line bg-surface-2/40")}>
      <h3 className="flex items-center gap-2 font-semibold">
        {conflict ? <AlertTriangle className="size-4 text-deviation-ink" /> : <UserX className="size-4 text-late-ink" />}
        {existing ? (conflict ? "Невыход требует пересмотра" : "Невыход подтверждён") : "Проверка невыхода"}
      </h3>
      {existing ? (
        <>
          {conflict ? (
            <p className="text-deviation-ink">
              После подтверждения появился дейлик, согласованный статус или праздник. В расчёте действует новое основание:
              время невыхода не добавляется к опозданию. Проверьте день и при необходимости отмените подтверждение.
            </p>
          ) : (
            <p>В опоздания включено <strong className="tnum">{hm(existing.seconds)}</strong> за всю смену. Штрафное время считается по месячной шкале.</p>
          )}
          <dl className="grid gap-1 text-ink-2">
            <div><dt className="inline text-ink-3">Подтверждённый план: </dt><dd className="inline tnum">{existing.intervals.map(([a, b]) => span(a, b)).join("; ")}</dd></div>
            <div><dt className="inline text-ink-3">Причина: </dt><dd className="inline whitespace-pre-wrap break-words">{existing.reason}</dd></div>
            <div className="text-[12px] text-ink-3"><dt className="inline">Подтвердил: </dt><dd className="inline">{existing.created_by} · {dateTime(existing.created_at)}</dd></div>
          </dl>
        </>
      ) : (
        <p className="text-ink-2">Смена закончилась, дейлика нет. Это ещё не означает невыход: подтвердите его только после проверки, что сотрудник действительно не работал.</p>
      )}

      {admin ? editing ? (
        <form className="grid gap-3" onSubmit={(event) => {
          event.preventDefault();
          if (reason.trim().length < 3 || save.isPending || (!existing && !eligible)) return;
          save.mutate(undefined, { onSuccess: () => setEditing(false) });
        }}>
          <p className="rounded-md bg-surface p-2.5 text-ink-2">
            <span className="mb-1 block font-medium">
              {dayMonth(cell.date)} · {(existing?.intervals ?? cell.plan?.intervals ?? []).map(([start, end]) => span(start, end)).join("; ")}
            </span>
            {existing
              ? "Подтверждение будет отменено, итоги дня и месяца пересчитаются. История решения сохранится."
              : <>В опоздания добавится <strong className="tnum text-late-ink">{hm(seconds)}</strong> за всю смену; далее применяется месячная шкала штрафного времени.</>}
          </p>
          <Field label={existing ? "Причина отмены" : "Причина подтверждения"} hint="Обязательно, от 3 до 1000 символов. Сохранится в журнале правок.">
            <Textarea value={reason} onChange={(event) => setReason(event.target.value)} required minLength={3} maxLength={1000} disabled={save.isPending} />
          </Field>
          {save.error ? <p role="alert" className="text-late-ink">{save.error.message}</p> : null}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="danger" disabled={reason.trim().length < 3 || save.isPending}>
              {save.isPending ? "Сохраняем…" : existing ? "Отменить подтверждение" : "Подтвердить невыход"}
            </Button>
            <Button variant="ghost" disabled={save.isPending} onClick={() => { setEditing(false); setReason(""); }}>Закрыть</Button>
          </div>
        </form>
      ) : (
        <Button className="justify-self-start" variant={existing ? "secondary" : "danger"} onClick={() => setEditing(true)}>
          {existing ? "Отменить подтверждение…" : "Подтвердить невыход…"}
        </Button>
      ) : null}
    </section>
  );
}
