import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { api } from "@/api/client";
import { useAdminMutation, useMeta, useStatusRequests } from "@/api/queries";
import type { StatusRequest, StatusKind } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { EmptyState, ErrorState } from "@/components/domain/feedback";
import { Pagination } from "@/components/domain/Pagination";
import { STATUS } from "@/components/domain/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Select, Textarea } from "@/components/ui/field";
import { dateTime, dayMonth } from "@/lib/format";

function statusLabel(request: StatusRequest) {
  return request.kind ? (STATUS[request.kind as StatusKind]?.label ?? request.kind) : "Снять статус";
}

export function StatusRequestsPanel() {
  const meta = useMeta().data;
  const [search] = useSearchParams();
  const selectedId = Number(search.get("request"));
  const [filter, setFilter] = useState("pending");
  const [offset, setOffset] = useState(0);
  const { data, error, refetch } = useStatusRequests(filter, offset);
  const [decision, setDecision] = useState<{ request: StatusRequest; accepted: boolean } | null>(null);
  const [note, setNote] = useState("");
  const mutation = useAdminMutation(
    () =>
      api.post(`/admin/status-requests/${decision!.request.id}/decision`, {
        accepted: decision!.accepted,
        note,
      }),
    { success: "Решение сохранено" },
  );
  return (
    <section className="grid gap-4" aria-label="Заявки на статусы">
      {meta?.demo ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface p-3 text-[12px]">
          <p>Для наглядной проверки создайте пример заявки в эмуляторе.</p>
          <Button asChild size="sm">
            <Link to="/demo">Создать пример заявки</Link>
          </Button>
        </div>
      ) : null}
      <div className="flex flex-wrap gap-3">
        <Select
          className="w-52"
          aria-label="Состояние заявок"
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value);
            setOffset(0);
          }}
        >
          <option value="pending">Ждут решения</option>
          <option value="accepted">Согласованные</option>
          <option value="rejected">Отклонённые и отозванные</option>
          <option value="all">Все заявки</option>
        </Select>
        <p className="self-center text-[12px] text-ink-3">
          До согласования сохраняются прежние статусы и расчёты.
        </p>
      </div>
      {error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : !data ? (
        <p>Загружаем заявки…</p>
      ) : !data.items.length ? (
        <EmptyState title="Заявок нет">
          Сотрудник может запросить отсутствие, отпуск или удалёнку в личке бота через /absent.
        </EmptyState>
      ) : (
        <ul className="grid gap-3">
          {data.items.map((request) => (
            <li
              key={request.id}
              data-request-id={request.id}
              className={`grid gap-3 rounded-lg border bg-surface p-4 ${selectedId === request.id ? "border-accent ring-1 ring-accent/20" : "border-line"}`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <Avatar employee={request.employee} size={24} />
                <b className="text-[13px]">{request.employee.short_name}</b>
                <Badge
                  tone={
                    request.state === "pending"
                      ? "deviation"
                      : request.state === "accepted"
                        ? "accent"
                        : "neutral"
                  }
                >
                  {request.state === "pending"
                    ? "Ждёт решения"
                    : request.state === "accepted"
                      ? "Согласована"
                      : "Отклонена / отозвана"}
                </Badge>
                <span className="ml-auto text-[11px] text-ink-3">
                  #{request.id} · {dateTime(request.created_at)}
                </span>
              </div>
              <p className="text-[14px] font-medium">
                {statusLabel(request)} · {dayMonth(request.start)}–{dayMonth(request.end)}
              </p>
              {request.note ? (
                <p className="whitespace-pre-wrap text-[13px] text-ink-2">{request.note}</p>
              ) : null}
              {request.decision_note ? (
                <p className="text-[12px] text-ink-3">Решение: {request.decision_note}</p>
              ) : null}
              {request.state === "pending" ? (
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => {
                      setDecision({ request, accepted: true });
                      setNote("");
                    }}
                  >
                    Согласовать
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => {
                      setDecision({ request, accepted: false });
                      setNote("");
                    }}
                  >
                    Отклонить
                  </Button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {data ? <Pagination offset={offset} total={data.total} onChange={setOffset} /> : null}
      <Dialog open={!!decision} onOpenChange={(open) => !open && setDecision(null)}>
        {decision ? (
          <DialogContent title={decision.accepted ? "Согласовать статус" : "Отклонить заявку"}>
            <form
              className="grid gap-4"
              onSubmit={(event) => {
                event.preventDefault();
                mutation.mutate(undefined, { onSuccess: () => setDecision(null) });
              }}
            >
              <p className="text-[13px]">
                {decision.request.employee.short_name} · {statusLabel(decision.request)} ·{" "}
                {dayMonth(decision.request.start)}–{dayMonth(decision.request.end)}
              </p>
              <p className="text-[12px] text-ink-3">
                {decision.accepted
                  ? "Статус будет применён ко всем дням указанного периода, расчёты обновятся."
                  : "Статусы дней останутся прежними. Сотрудник увидит решение при проверке заявки в боте."}
              </p>
              <Field label="Комментарий к решению">
                <Textarea maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
              </Field>
              <Button type="submit" variant="primary" disabled={mutation.isPending}>
                Подтвердить решение
              </Button>
            </form>
          </DialogContent>
        ) : null}
      </Dialog>
    </section>
  );
}
