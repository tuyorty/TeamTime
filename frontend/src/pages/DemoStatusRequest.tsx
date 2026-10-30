import { useState } from "react";
import { useNavigate } from "react-router";

import { api } from "@/api/client";
import { useAdminMutation, useEmployees, useToday } from "@/api/queries";
import type { StatusKind } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";

export function DemoStatusRequest({ today }: { today: string }) {
  const navigate = useNavigate();
  const employees = useEmployees().data ?? [];
  const day = useToday().data;
  const [employeeId, setEmployeeId] = useState<number | null>(null);
  const [kind, setKind] = useState<StatusKind>("remote");
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(today);
  const selected =
    employeeId ??
    (day ? day.rows.find((row) => row.presence === "on_site")?.employee.id ?? employees[0]?.id : undefined);
  const create = useAdminMutation(
    () =>
      api.post<{ request_id: number }>("/demo/status-requests", { employee_id: selected, start, end, kind }),
    { success: "Заявка создана. До согласования статус сотрудника остаётся прежним." },
  );
  return (
    <Panel
      title="Проверка согласования статуса"
      description="Эта форма создаёт такую же заявку, как /absent в личке бота. Доступна только в демо."
    >
      <form
        className="grid gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate(undefined, {
            onSuccess: (result) => navigate(`/inbox?view=requests&request=${result.request_id}`),
          });
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Сотрудник для примера">
            <Select
              value={selected ?? ""}
              required
              onChange={(event) => setEmployeeId(Number(event.target.value))}
            >
              {!selected ? <option value="">Загружаем сотрудников…</option> : null}
              {employees.map((employee) => (
                <option key={employee.id} value={employee.id}>
                  {employee.short_name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Запрашиваемый статус">
            <Select value={kind} onChange={(event) => setKind(event.target.value as StatusKind)}>
              <option value="remote">Удалёнка</option>
              <option value="absent">Не приду</option>
              <option value="dayoff">Отгул</option>
              <option value="sick">Больничный</option>
              <option value="vacation">Отпуск</option>
            </Select>
          </Field>
          <Field label="Начало периода">
            <Input
              type="date"
              required
              value={start}
              onChange={(event) => {
                setStart(event.target.value);
                if (event.target.value > end) setEnd(event.target.value);
              }}
            />
          </Field>
          <Field label="Конец периода">
            <Input
              type="date"
              required
              min={start}
              value={end}
              onChange={(event) => setEnd(event.target.value)}
            />
          </Field>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" variant="primary" disabled={!selected || create.isPending}>
            Создать пример заявки
          </Button>
          <p className="text-[12px] text-ink-3">
            После создания откроется инбокс. Согласуйте заявку, затем откройте сотрудника в «Сегодня».
          </p>
        </div>
      </form>
    </Panel>
  );
}
