import { useState } from "react";

import { useAudit, useEmployees } from "@/api/queries";
import type { Audit } from "@/api/types";
import { Select } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { dateTime } from "@/lib/format";

const ACTIONS: Record<string, string> = {
  "bonus.created": "Проектная премия добавлена",
  "bonus.updated": "Проектная премия изменена",
  "bonus.cancelled": "Проектная премия отменена",
  "daily.set": "Факт дня исправлен",
  "daily.retract": "Факт дня убран",
  "plan_day.set": "План дня изменён",
  "status.set": "Статус дня",
  "status.clear": "Статус снят",
  "employee.create": "Сотрудник добавлен",
  "employee.update": "Сотрудник изменён",
  "identity.link": "Привязка Telegram",
  "topic.bind": "Тема привязана",
  "topic.unbind": "Тема отвязана",
  "settings.update": "Настройки изменены",
  "import.telegram": "Импорт истории",
  "inbox.accepted": "Инбокс: принято",
  "inbox.ignored": "Инбокс: игнорировать",
  "inbox.fixed": "Инбокс: исправлено",
  "inbox.pending": "Инбокс: возвращено",
};

function actor(a: string): string {
  if (a === "admin") return "админ";
  if (a.startsWith("bot:")) return `через бота (${a.slice(4)})`;
  if (a === "seed") return "демо-генератор";
  return a;
}

function Diff({ a }: { a: Audit }) {
  const keys = [...new Set([...Object.keys(a.before ?? {}), ...Object.keys(a.after ?? {})])];
  if (!keys.length) return null;
  return (
    <table className="mt-1.5 text-[12px] tnum">
      <tbody>
        {keys.map((k) => {
          const b = JSON.stringify(a.before?.[k] ?? null);
          const n = JSON.stringify(a.after?.[k] ?? null);
          if (b === n) return null;
          return (
            <tr key={k}>
              <th scope="row" className="pr-3 text-left font-normal text-ink-3">{k}</th>
              <td className="pr-2 text-ink-3 line-through">{a.before ? b : ""}</td>
              <td className="text-ink">{a.after ? n : "удалено"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function AuditTab() {
  const [employee, setEmployee] = useState<string>("");
  const { data } = useAudit(employee ? Number(employee) : undefined);
  const employees = useEmployees(true).data ?? [];
  const names = new Map(employees.map((e) => [e.id, e.short_name]));
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select className="w-56" value={employee} onChange={(e) => setEmployee(e.target.value)} aria-label="Сотрудник">
          <option value="">Все сотрудники</option>
          {employees.map((e) => (
            <option key={e.id} value={e.id}>
              {e.short_name}
            </option>
          ))}
        </Select>
        <p className="text-[12px] text-ink-3">Журнал пополняется только: записи нельзя изменить или удалить.</p>
      </div>
      {!data ? (
        <Skeleton className="h-80" />
      ) : (
        <ol className="divide-y divide-line rounded-lg border border-line bg-surface">
          {data.map((a) => (
            <li key={a.id} className="px-4 py-3 text-[13px]">
              <div className="flex flex-wrap items-baseline gap-x-3">
                <span className="font-medium">{ACTIONS[a.action] ?? a.action}</span>
                {a.employee_id ? <span>{names.get(a.employee_id) ?? `#${a.employee_id}`}</span> : null}
                <span className="text-ink-3">{actor(a.actor)}</span>
                <span className="ml-auto text-[12px] text-ink-3 tnum">{dateTime(a.at)}</span>
              </div>
              {a.reason ? <p className="mt-0.5 text-ink-2">Причина: {a.reason}</p> : null}
              <Diff a={a} />
            </li>
          ))}
          {!data.length ? <li className="px-4 py-8 text-center text-[13px] text-ink-2">Правок пока не было.</li> : null}
        </ol>
      )}
    </div>
  );
}
