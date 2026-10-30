import { useSystem } from "@/api/queries";
import { ErrorState } from "@/components/domain/feedback";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { dateTime } from "@/lib/format";

const LABELS: Record<string, string> = {
  ok: "Работает",
  running: "Работает",
  online: "На связи",
  polling: "На связи",
  starting: "Запускается",
  stopped: "Остановлен",
  stale: "Давно нет связи",
  error: "Ошибка",
  unknown: "Нет данных",
  success: "Успешно",
  sent: "Отправлено",
  attempted: "Результат неизвестен",
  failed: "Не доставлено",
  unsupported: "Не поддерживается",
  deferred: "Отложено",
  pending: "Ожидает",
  queued: "В очереди",
  retry: "Ждёт повтора после 429",
};
const KINDS: Record<string, string> = {
  reaction: "Реакция",
  reply: "Ответ",
  reply_edit: "Правка ответа",
  warning: "Вопрос к сообщению",
};
function when(value: string | null | undefined) {
  return value ? dateTime(value) : "Нет данных";
}
function State({ value }: { value: string }) {
  return (
    <Badge
      tone={
        ["ok", "online", "running", "polling", "success", "sent"].includes(value)
          ? "accent"
          : ["error", "failed", "stale"].includes(value)
            ? "deviation"
            : "neutral"
      }
    >
      {LABELS[value] ?? value}
    </Badge>
  );
}

export function SystemTab() {
  const { data, error, refetch } = useSystem();
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!data) return <Skeleton className="h-80" />;
  const names = new Map(data.personal_notifications.map((person) => [person.employee_id, person.name]));
  return (
    <div className="grid gap-5">
      <p className="text-[12px] text-ink-3">
        Версия {data.version} · база {data.database === "ok" ? "доступна" : data.database} · миграция{" "}
        {data.migration ?? "нет данных"} · проверено {when(data.checked_at)}. Обновление каждые 30 секунд.
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        {data.services.map((service) => (
          <Panel
            key={service.service}
            title={service.service === "bot" ? "Telegram-бот" : "Резервная копия"}
            actions={<State value={service.state} />}
          >
            <dl className="grid grid-cols-[1fr_1fr] gap-2 text-[12px]">
              <dt className="text-ink-3">Последняя связь</dt>
              <dd>{when(service.heartbeat_at)}</dd>
              <dt className="text-ink-3">Последний успех</dt>
              <dd>{when(service.last_success_at)}</dd>
              {service.service === "bot" ? (
                <>
                  <dt className="text-ink-3">Последнее обновление из Telegram</dt>
                  <dd>{when(service.last_update_at)}</dd>
                </>
              ) : null}
              <dt className="text-ink-3">Последняя ошибка</dt>
              <dd>
                {when(service.last_error_at)}
                {service.error_code ? ` · ${service.error_code}` : ""}
              </dd>
            </dl>
            <p className="mt-3 text-[11px] leading-5 text-ink-3">
              {service.service === "bot"
                ? "Состояние определяется запросами к Telegram. Подключение сайта к обновлениям не подтверждает работу бота."
                : "Фиксируется результат backup.sh. Нет данных означает, что скрипт ещё не сообщил о выполнении. Это не проверка восстановления копии."}
            </p>
          </Panel>
        ))}
      </div>
      <Panel
        title="Готовность личных напоминаний"
        description="Бот может писать человеку после того, как тот открыл личку и нажал /start."
      >
        <div className="max-h-96 divide-y divide-line overflow-y-auto">
          {data.personal_notifications.map((person) => (
            <div key={person.employee_id} className="flex flex-wrap items-center gap-3 py-2 text-[12px]">
              <b className="min-w-40">{person.name}</b>
              <Badge tone={person.ready ? "accent" : "deviation"}>
                {person.ready ? "Личка доступна" : "Нет доступной лички"}
              </Badge>
              <span>{person.enabled ? `Через ${person.delay_minutes} мин` : "Отключил напоминания"}</span>
              {person.quiet_start != null && person.quiet_end != null ? (
                <span className="text-ink-3">
                  Тихое время: {`${Math.floor(person.quiet_start / 60)}`.padStart(2, "0")}:
                  {`${person.quiet_start % 60}`.padStart(2, "0")}–
                  {`${Math.floor(person.quiet_end / 60)}`.padStart(2, "0")}:
                  {`${person.quiet_end % 60}`.padStart(2, "0")}
                </span>
              ) : null}
            </div>
          ))}
        </div>
      </Panel>
      <Panel
        title="Последние реакции и ответы"
        description="Сохраняем попытку перед обращением к Telegram. При потере ответа результат может остаться неизвестным."
      >
        <div className="max-h-80 divide-y divide-line overflow-y-auto">
          {data.deliveries.map((item) => (
            <div key={item.id} className="flex flex-wrap gap-3 py-2 text-[12px]">
              <span className="min-w-36 text-ink-3">{when(item.created_at)}</span>
              <b>{KINDS[item.kind] ?? item.kind}</b>
              <span>{item.employee_id ? (names.get(item.employee_id) ?? `#${item.employee_id}`) : ""}</span>
              <State value={item.state} />
              <span>Попыток: {item.attempts}</span>
              {item.error_code ? <span className="text-ink-3">{item.error_code}</span> : null}
            </div>
          ))}
          {!data.deliveries.length ? (
            <p className="text-[13px] text-ink-3">Доставок после обновления пока нет.</p>
          ) : null}
        </div>
      </Panel>
      <Panel
        title="Последние напоминания"
        description="Неопределённую отправку автоматически не повторяем. Один дополнительный повтор возможен по просьбе сотрудника."
      >
        <div className="max-h-80 divide-y divide-line overflow-y-auto">
          {data.reminders.map((item, index) => (
            <div key={index} className="flex flex-wrap gap-3 py-2 text-[12px]">
              <b>{names.get(item.employee_id) ?? `#${item.employee_id}`}</b>
              <span>{item.work_date}</span>
              <State value={item.state} />
              <span>Попыток: {item.attempts}</span>
              {item.deferred_until ? <span>Отложено до {when(item.deferred_until)}</span> : null}
              {item.snooze_until ? <span>Попросил повтор: {when(item.snooze_until)}</span> : null}
              {item.followup_sent_at ? <span>Повтор отправлен: {when(item.followup_sent_at)}</span> : null}
              {item.error_code ? <span>{item.error_code}</span> : null}
            </div>
          ))}
          {!data.reminders.length ? <p className="text-[13px] text-ink-3">Напоминаний пока нет.</p> : null}
        </div>
      </Panel>
    </div>
  );
}
