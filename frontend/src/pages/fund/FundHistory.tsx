import { useState } from "react";
import type { FundOverview } from "@/api/fund";
import { money } from "@/lib/format";
import { Card } from "./shared";
import { formatShare } from "./format";

const actions: Record<string, string> = {
  "calendar.created": "Версия календаря",
  "terms.created": "Условия сотрудника",
  "receipt.created": "Поступление от источника",
  "source.confirmed": "Полнота выплат",
  "operation.draft": "Черновик операции",
  "operation.posted": "Операция проведена",
  "operation.cancelled": "Черновик отменён",
  "operation.reversed": "Обратная операция",
  "period.closed": "Месяц закрыт",
  "bonus.approved": "Премия утверждена",
  "adjustment.proposed": "Предложена корректировка",
  "adjustment.approved": "Корректировка утверждена",
  "adjustment.rejected": "Корректировка отклонена",
  "claim.created": "Заявка на компенсацию",
  "claim.approved": "Компенсация утверждена",
  "claim.rejected": "Компенсация отклонена",
  "time.requested": "Запрос отсутствия или исключения",
  "time.approved": "Отсутствие или исключение утверждено",
  "time.rejected": "Запрос отклонён",
  "time.cancelled": "Решение отменено",
  "vacation.opening": "Начальный остаток отпуска",
  "vacation.adjusted": "Остаток отпуска уточнён",
  "loan.created": "Заём согласован",
  "loan.consent": "Согласие на зачёт займа",
  "basket.created": "Корзина добавлена",
  "basket.reconciled": "Остаток сверен",
  "member.bootstrap": "Назначен первый руководитель",
  "member.updated": "Участие и полномочия",
  "fund.activated": "Учёт фонда включён",
  "closed_time.changed": "Правка исходников закрытого месяца",
  "closed_time.reviewed": "Исходники проверены",
};

/** Показываем учётные поля аудита, не выводя произвольные личные исходники. */
export function FundHistory({ data }: { data: FundOverview }) {
  const [filter, setFilter] = useState("");
  const name = (id: number) =>
    data.members.find((m) => m.id === id)?.full_name ?? `Участник #${id}`;
  const rows = data.history.filter((e) =>
    `${actions[e.action] ?? e.action} ${name(e.actor_id)}`
      .toLowerCase()
      .includes(filter.toLowerCase()),
  );
  return (
    <Card>
      <details>
        <summary className="cursor-pointer text-sm font-semibold">
          История финансовых изменений
        </summary>
        <p className="mt-2 text-xs text-ink-3">
          Последние 200 событий: кто внёс изменение, когда и на каком основании.
        </p>
        <input
          aria-label="Поиск в истории финансов"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Участник или действие"
          className="mt-3 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
        />
        <ol className="mt-3 max-h-96 space-y-3 overflow-y-auto">
          {rows.map((entry) => {
            const terms =
              entry.action === "terms.created"
                ? data.terms.find((t) => t.id === entry.data.id)
                : undefined;
            const calendar =
              entry.action === "calendar.created"
                ? data.calendars.find((c) => c.id === entry.data.id)
                : undefined;
            const reason = entry.data.reason;
            return (
              <li key={entry.id} className="border-t border-line pt-3 text-sm">
                <div className="flex flex-wrap justify-between gap-2">
                  <strong>{actions[entry.action] ?? "Изменение учёта"}</strong>
                  <time
                    className="text-xs text-ink-3"
                    dateTime={entry.created_at}
                  >
                    {new Date(entry.created_at).toLocaleString("ru-RU")}
                  </time>
                </div>
                <p className="mt-1 text-xs text-ink-3">
                  {entry.action === "closed_time.changed"
                    ? "Получена новая версия рабочего исходника"
                    : name(entry.actor_id)}{" "}
                  · запись #{entry.id}
                </p>
                {typeof reason === "string" && (
                  <p className="mt-1 text-ink-2">{reason}</p>
                )}
                {typeof entry.data.amount === "string" && (
                  <p className="mt-1 tnum">{money(entry.data.amount)}</p>
                )}
                {typeof entry.data.month === "string" && (
                  <p className="text-xs text-ink-3">
                    Период: {entry.data.month.slice(0, 7)}
                  </p>
                )}
                {terms && (
                  <p className="mt-1 text-ink-2">
                    {name(terms.employee_id)} · с {terms.effective_from} ·{" "}
                    {money(terms.target)} · доля {formatShare(terms.share)} ·
                    версия {terms.revision}
                  </p>
                )}
                {calendar && (
                  <p className="mt-1 text-ink-2">
                    {calendar.month.slice(0, 7)} · {calendar.source} · версия{" "}
                    {calendar.version}
                  </p>
                )}
              </li>
            );
          })}
          {!rows.length && (
            <li className="py-4 text-sm text-ink-3">
              Изменений по этому запросу нет
            </li>
          )}
        </ol>
      </details>
    </Card>
  );
}
