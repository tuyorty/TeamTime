import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { FundOverview, TeamActor } from "@/api/fund";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { money } from "@/lib/format";
import { amountField, reasonField, type FormSpec } from "./formTypes";
import { personField } from "./forms";
import { dateLabel, formatShare } from "./format";
import { Card } from "./shared";

export function FundSettings({
  data,
  actor,
  month,
  today,
  onForm,
  onClose,
}: {
  data: FundOverview;
  actor: TeamActor;
  month: string;
  today: string;
  onForm: (s: FormSpec) => void;
  onClose: () => void;
}) {
  const [calendar, setCalendar] = useState(false);
  const [tvLink, setTvLink] = useState("");
  const [error, setError] = useState("");
  const setup = useQuery({
    queryKey: ["fund", "setup"],
    queryFn: () =>
      api.get<{ employees: { id: number; full_name: string }[] }>(
        "/fund/setup",
      ),
  });
  return (
    <Sheet
      open
      onOpenChange={(v) => {
        if (!v) onClose();
      }}
    >
      <SheetContent
        title="Настройки фонда"
        subtitle="Условия и начальные остатки подтверждает руководитель"
      >
        <div className="grid gap-5">
          {!data.config.enabled && (
            <Card>
              <h3 className="font-semibold">Подготовка к переходу</h3>
              <p className="mt-2 text-sm text-ink-2">
                После сверки исходных данных включите именной доступ ко всему
                дэшборду. Вход сотрудников подтверждается через бота.
              </p>
              <Button
                className="mt-3"
                onClick={() =>
                  onForm({
                    title: "Включить именной доступ",
                    description:
                      "Общий доступ к рабочим данным будет закрыт. Для телевизора заранее создайте отдельную ссылку ниже.",
                    path: "/fund/activate",
                    fields: [],
                    submit: "Включить",
                    body: () => ({ joined_on: data.config.first_month }),
                  })
                }
              >
                Включить доступ участников
              </Button>
            </Card>
          )}
          <section>
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-semibold">Участники и условия</h3>
              <Button
                size="sm"
                onClick={() =>
                  onForm({
                    title: "Участие в фонде",
                    path: "/fund/members",
                    method: "put",
                    fields: [
                      {
                        name: "employee_id",
                        label: "Сотрудник",
                        type: "select",
                        options: setup.data?.employees.map((e) => ({
                          value: String(e.id),
                          label: e.full_name,
                        })),
                      },
                      {
                        name: "joined_on",
                        label: "Участвует с",
                        type: "date",
                        value: month,
                      },
                      {
                        name: "leader",
                        label: "Руководитель фонда",
                        type: "checkbox",
                      },
                      reasonField,
                    ],
                    body: (v) => ({
                      employee_id: Number(v.employee_id),
                      joined_on: v.joined_on,
                      leader: v.leader === "true",
                      active: true,
                      reason: v.reason,
                    }),
                  })
                }
              >
                Добавить
              </Button>
            </div>
            <div className="mt-3 grid gap-3">
              {data.members.map((m) => {
                const terms = data.terms.find((t) => t.employee_id === m.id);
                return (
                  <Card key={m.id}>
                    <strong className="text-sm">{m.full_name}</strong>
                    <p className="mt-1 text-xs text-ink-3">
                      {m.leader ? "Руководитель" : "Участник"} · с{" "}
                      {dateLabel(m.joined_on)}
                      {m.left_on && ` по ${dateLabel(m.left_on)}`}
                    </p>
                    <p className="mt-2 text-sm">
                      {terms
                        ? `${money(terms.target)} · ставка ${formatShare(terms.share)} · с ${dateLabel(terms.effective_from)}`
                        : "Условия не заданы"}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        onClick={() =>
                          onForm({
                            title: `Условия: ${m.short_name}`,
                            description:
                              "Целевая сумма уже соответствует доле ставки. Повторно умножать её на долю не нужно.",
                            path: `/fund/members/${m.id}/terms`,
                            fields: [
                              {
                                name: "date",
                                label: "Действуют с",
                                type: "date",
                                value: month,
                              },
                              {
                                ...amountField,
                                name: "target",
                                label: "Целевая сумма на руки, ₽",
                                value: terms?.target,
                                min: "0",
                              },
                              {
                                name: "share",
                                label: "Доля ставки",
                                type: "number",
                                value: terms?.share ?? "1",
                                min: "0.0001",
                                max: "10",
                                step: "0.0001",
                              },
                              {
                                name: "sources",
                                label:
                                  "Ожидаемые источники выплат, каждый с новой строки",
                                type: "textarea",
                                optional: true,
                                value: terms?.sources.join("\n"),
                              },
                              {
                                name: "no_other_income",
                                label: "Нет иных источников дохода",
                                type: "checkbox",
                                value: String(terms?.no_other_income ?? false),
                              },
                              reasonField,
                            ],
                            body: (v) => ({
                              effective_from: v.date,
                              target: v.target,
                              share: v.share,
                              sources:
                                v.sources
                                  ?.split("\n")
                                  .map((s) => s.trim())
                                  .filter(Boolean) ?? [],
                              no_other_income: v.no_other_income === "true",
                              reason: v.reason,
                            }),
                          })
                        }
                      >
                        Изменить условия
                      </Button>
                      {!m.opening && (
                        <Button
                          size="sm"
                          onClick={() =>
                            onForm({
                              title: `Начальная переплата: ${m.short_name}`,
                              description:
                                "Укажите подтверждённый остаток, в том числе нулевой.",
                              path: `/fund/members/${m.id}/opening`,
                              fields: [
                                { ...amountField, min: "0" },
                                reasonField,
                              ],
                              body: (v) => ({
                                month: data.config.first_month,
                                amount: v.amount,
                                reason: v.reason,
                              }),
                            })
                          }
                        >
                          Начальная переплата
                        </Button>
                      )}
                      <Button
                        size="sm"
                        onClick={() =>
                          onForm({
                            title: `Отпуск: ${m.short_name}`,
                            path: "/fund/vacations",
                            fields: [
                              {
                                name: "start",
                                label: "Начало рабочего года",
                                type: "date",
                              },
                              {
                                name: "end",
                                label: "Конец рабочего года",
                                type: "date",
                              },
                              {
                                name: "as_of",
                                label: "Остаток подтверждён на дату",
                                type: "date",
                                value: today,
                              },
                              {
                                name: "opening_days",
                                label: "Доступно дней на эту дату",
                                type: "number",
                                min: "0",
                                step: "1",
                              },
                              reasonField,
                            ],
                            body: (v) => ({
                              employee_id: m.id,
                              start: v.start,
                              end: v.end,
                              as_of: v.as_of,
                              opening_days: Number(v.opening_days),
                              reason: v.reason,
                            }),
                          })
                        }
                      >
                        Остаток отпуска
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          onForm({
                            title: `Изменить участие: ${m.short_name}`,
                            path: "/fund/members",
                            method: "put",
                            fields: [
                              {
                                name: "joined_on",
                                label: "Участвует с",
                                type: "date",
                                value: m.joined_on,
                              },
                              {
                                name: "left_on",
                                label: "Последний день участия",
                                type: "date",
                                value: m.left_on ?? "",
                                optional: true,
                              },
                              {
                                name: "active",
                                label: "Доступ к фонду включён",
                                type: "checkbox",
                                value: String(m.active),
                              },
                              {
                                name: "leader",
                                label: "Руководитель",
                                type: "checkbox",
                                value: String(m.leader),
                              },
                              reasonField,
                            ],
                            body: (v) => ({
                              employee_id: m.id,
                              joined_on: v.joined_on,
                              left_on: v.left_on || null,
                              active: v.active === "true",
                              leader: v.leader === "true",
                              reason: v.reason,
                            }),
                          })
                        }
                      >
                        Участие и роль
                      </Button>
                    </div>
                  </Card>
                );
              })}
            </div>
          </section>
          <section>
            <h3 className="font-semibold">Производственный календарь</h3>
            <p className="mt-2 text-xs text-ink-3">
              Без подтверждённой версии календаря месяц не рассчитывается.
            </p>
            {data.calendars
              .filter(
                (c, i, all) => all.findIndex((x) => x.month === c.month) === i,
              )
              .map((c) => (
                <p key={c.id} className="mt-2 text-sm">
                  {c.month.slice(0, 7)} ·{" "}
                  {Object.values(c.days).reduce((a, b) => a + b, 0) / 3600} ч ·{" "}
                  {c.source_version}
                </p>
              ))}
            <Button className="mt-3" onClick={() => setCalendar(!calendar)}>
              Ввести календарь месяца
            </Button>
            {calendar && <CalendarEditor month={month} />}
          </section>
          <section>
            <h3 className="font-semibold">Корзины фонда</h3>
            {data.baskets.map((b) => (
              <div
                key={b.id}
                className="my-3 rounded-lg border border-line p-3"
              >
                <p className="text-sm">
                  {b.name} ·{" "}
                  {data.members.find((m) => m.id === b.owner_id)?.short_name}
                </p>
                {b.owner_id === actor.employee_id && (
                  <Button
                    size="sm"
                    className="mt-2"
                    onClick={() =>
                      onForm({
                        title: `Начальный остаток: ${b.name}`,
                        description:
                          "Однократная настройка до первого движения денег. Остаток включает все операции до выбранной даты.",
                        path: `/fund/baskets/${b.id}/opening`,
                        fields: [
                          { ...amountField, min: "0" },
                          {
                            name: "as_of",
                            label: "На конец даты",
                            type: "date",
                            value: today,
                            max: today,
                          },
                          reasonField,
                        ],
                        body: (v) => ({
                          as_of: v.as_of,
                          amount: v.amount,
                          reason: v.reason,
                        }),
                      })
                    }
                  >
                    Начальный остаток
                  </Button>
                )}
              </div>
            ))}
            {data.baskets.length < 3 && (
              <Button
                onClick={() =>
                  onForm({
                    title: "Добавить корзину",
                    path: "/fund/baskets",
                    fields: [
                      { name: "name", label: "Название" },
                      {
                        ...personField(data),
                        name: "owner_id",
                        label: "Ответственный за подтверждение",
                      },
                    ],
                    body: (v) => ({
                      name: v.name,
                      owner_id: Number(v.owner_id),
                    }),
                  })
                }
              >
                Добавить корзину
              </Button>
            )}
          </section>
          <section>
            <h3 className="font-semibold">Личные запросы и резервные копии</h3>
            <p className="mt-2 text-xs text-ink-3">
              Запросы 18, 19, 2 и 3 числа в часовом поясе команды. Повторный
              запуск не повторяет отправку.
            </p>
            <Button
              className="mt-3"
              onClick={() =>
                onForm({
                  title: "Расписание запросов",
                  path: "/fund/preferences",
                  fields: [
                    {
                      name: "hour",
                      label: "Часы",
                      type: "number",
                      min: "0",
                      max: "23",
                      step: "1",
                      value: String(data.config.notification_hour),
                    },
                    {
                      name: "minute",
                      label: "Минуты",
                      type: "number",
                      min: "0",
                      max: "59",
                      step: "1",
                      value: String(data.config.notification_minute),
                    },
                    {
                      name: "enabled",
                      label: "Личные запросы включены",
                      type: "checkbox",
                      value: String(data.config.reminders_enabled),
                    },
                    {
                      name: "technical",
                      label:
                        "Технические администраторы для получения резервных копий",
                      type: "select",
                      options: data.members.map((m) => ({
                        value: String(m.id),
                        label: m.full_name,
                      })),
                      value: String(
                        data.config.technical_employee_ids[0] ??
                          actor.employee_id,
                      ),
                    },
                  ],
                  body: (v) => ({
                    notification_hour: Number(v.hour),
                    notification_minute: Number(v.minute),
                    reminders_enabled: v.enabled === "true",
                    technical_employee_ids: [Number(v.technical)],
                  }),
                })
              }
            >
              Настроить запросы и получателя копий
            </Button>
          </section>
          <section>
            <h3 className="font-semibold">Экран телевизора</h3>
            <p className="mt-2 text-xs text-ink-3">
              Отдельный доступ только к сегодняшнему расписанию, без финансов.
            </p>
            <Button
              className="mt-3"
              onClick={async () => {
                try {
                  const result = await api.post<{ token: string }>(
                    "/team/display-token",
                  );
                  setTvLink(
                    `${window.location.origin}/tv#access=${result.token}`,
                  );
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              Создать ссылку для телевизора
            </Button>
            {tvLink && (
              <Input
                className="mt-2"
                aria-label="Ссылка для телевизора"
                readOnly
                value={tvLink}
                onFocus={(e) => e.target.select()}
              />
            )}
          </section>
          {error && (
            <p role="alert" className="text-sm text-late-ink">
              {error}
            </p>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function CalendarEditor({ month }: { month: string }) {
  const count = new Date(
    Number(month.slice(0, 4)),
    Number(month.slice(5, 7)),
    0,
  ).getDate();
  const [days, setDays] = useState<Record<string, string>>({});
  const [source, setSource] = useState("");
  const [version, setVersion] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const cache = useQueryClient();
  return (
    <form
      className="mt-4 grid gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setError("");
        if (Object.keys(days).length !== count) {
          setError("Укажите норму каждого дня, включая выходные и праздники");
          return;
        }
        setBusy(true);
        try {
          await api.post("/fund/calendars", {
            month,
            source,
            version,
            reason,
            days: Object.fromEntries(
              Object.entries(days).map(([d, v]) => [
                d,
                v === "holiday" ? 0 : Number(v) * 3600,
              ]),
            ),
            holidays: Object.entries(days)
              .filter(([, v]) => v === "holiday")
              .map(([d]) => d),
          });
          await cache.invalidateQueries({ queryKey: ["fund"] });
          setError("Календарь сохранён");
        } catch (err) {
          setError((err as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <p className="text-sm font-medium">Календарь {month.slice(0, 7)}</p>
      <div className="grid grid-cols-3 gap-2">
        {Array.from({ length: count }, (_, i) => {
          const d = `${month.slice(0, 7)}-${String(i + 1).padStart(2, "0")}`;
          return (
            <Field
              key={d}
              label={`${i + 1} ${new Date(`${d}T12:00`).toLocaleDateString("ru", { weekday: "short" })}`}
            >
              <Select
                required
                value={days[d] ?? ""}
                onChange={(e) => setDays({ ...days, [d]: e.target.value })}
              >
                <option value="" disabled>
                  Выбрать
                </option>
                <option value="8">8 ч</option>
                <option value="7">7 ч</option>
                <option value="0">Выходной</option>
                <option value="holiday">Праздник</option>
              </Select>
            </Field>
          );
        })}
      </div>
      <Field label="Источник календаря">
        <Input
          required
          value={source}
          onChange={(e) => setSource(e.target.value)}
        />
      </Field>
      <Field label="Версия источника">
        <Input
          required
          value={version}
          onChange={(e) => setVersion(e.target.value)}
        />
      </Field>
      <Field label="Основание">
        <Textarea
          required
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </Field>
      {error && (
        <p role="status" className="text-sm text-ink-2">
          {error}
        </p>
      )}
      <Button type="submit" variant="primary" disabled={busy}>
        Подтвердить календарь
      </Button>
    </form>
  );
}
