import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { FundAmounts, FundReport, FundRow, TeamActor } from "@/api/fund";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { money } from "@/lib/format";
import { amountField, reasonField, type FormSpec } from "./formTypes";
import { receiptForm, timeForm } from "./forms";
import { dateLabel, formatShare, hours } from "./format";
import { Card, State } from "./shared";

const labels: [keyof FundAmounts, string][] = [
  ["salary", "Начислено за время"],
  ["bonus", "Премии"],
  ["correction", "Корректировки прошлых месяцев"],
  ["received", "Получено из источников"],
  ["overpayment_in", "Переплата на начало"],
  ["offset", "Зачтено из переплаты"],
  ["overpayment_new", "Новая переплата"],
  ["overpayment_out", "Переплата на конец"],
  ["supplement_before_rounding", "Доплата до округления"],
  ["rounding", "Добавлено округлением"],
  ["supplement", "Доплата фонда"],
  ["compensation", "Компенсации"],
  ["accrued", "Всего начислено фондом"],
  ["paid", "Погашено обязательств"],
  ["due", "Остаток к выплате"],
];
export function FundDetails({
  row,
  report,
  actor,
  today,
  onForm,
  onClose,
}: {
  row: FundRow;
  report: FundReport;
  actor: TeamActor;
  today: string;
  onForm: (s: FormSpec) => void;
  onClose: () => void;
}) {
  const vacation = useQuery({
    queryKey: ["fund", "vacation", row.employee.id],
    queryFn: () =>
      api.get<
        {
          id: number;
          start: string;
          end: string;
          available: number;
          reserved: number;
          adjustment_days: number;
        }[]
      >(`/fund/vacations/${row.employee.id}`),
    retry: false,
  });
  const own = row.employee.id === actor.employee_id;
  return (
    <Sheet
      open
      onOpenChange={(v) => {
        if (!v) onClose();
      }}
    >
      <SheetContent
        title={row.employee.name}
        subtitle={`Расчёт за ${report.month.slice(0, 7)} · ${report.closed ? "Закрыт" : "Предварительный"}`}
      >
        <div className="grid gap-5">
          {row.blockers.length > 0 && (
            <div className="rounded-lg bg-deviation-soft p-3 text-sm text-deviation-ink">
              <strong>Нужно уточнить</strong>
              <ul className="mt-2 list-inside list-disc space-y-1">
                {row.blockers.map((b, i) => (
                  <li key={i}>
                    {b.day && `${dateLabel(b.day)}: `}
                    {b.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            {[
              ["Норма", row.norm_sec],
              ["С эффективностью", row.effective_sec],
              ["Штрафное время", row.penalty_sec],
              ["Зачтено", row.credited_sec],
            ].map(([label, value]) => (
              <Card key={label}>
                <p className="text-xs text-ink-3">{label}</p>
                <strong className="tnum text-xl">{hours(Number(value))}</strong>
              </Card>
            ))}
          </div>
          {row.inputs?.conditions.map((c, i) => (
            <div key={i} className="rounded-lg bg-surface-2 p-3 text-sm">
              <strong>
                {dateLabel(c.start)} — {dateLabel(c.end)}
              </strong>
              <p className="mt-1">
                Целевая сумма {money(c.target)} · доля ставки{" "}
                {formatShare(c.share)}
              </p>
            </div>
          ))}
          <section>
            <h3 className="font-semibold">Как получилась сумма</h3>
            {row.amounts ? (
              <dl className="mt-2 divide-y divide-line">
                {labels.map(([key, label]) => (
                  <div
                    key={key}
                    className={`flex justify-between gap-3 py-2 text-sm ${["supplement", "due"].includes(key) ? "font-semibold text-accent" : ""}`}
                  >
                    <dt>{label}</dt>
                    <dd className="tnum whitespace-nowrap">
                      {money(row.amounts![key])}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="mt-2 text-sm text-ink-2">
                Расчёт появится после уточнения условий и исходных данных.
              </p>
            )}
          </section>
          <section>
            <h3 className="font-semibold">Выплаты других источников</h3>
            <div className="mt-3 grid gap-3">
              {row.sources.map((s) => (
                <Card key={s.name}>
                  <div className="flex justify-between gap-2 text-sm">
                    <strong>{s.name}</strong>
                    <span>{money(s.amount)}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                    <State value={s.state} />
                    {own && !report.closed && (
                      <Button
                        size="sm"
                        onClick={() =>
                          onForm({
                            title:
                              s.state === "complete"
                                ? "Ожидаются ещё выплаты"
                                : "Все выплаты получены",
                            description: `${s.name} · ${report.month.slice(0, 7)} · сумма ${money(s.amount)}`,
                            path: "/fund/sources/confirm",
                            fields: [],
                            submit: "Подтвердить",
                            body: () => ({
                              month: report.month,
                              source: s.name,
                              complete: s.state !== "complete",
                              expected_total: s.amount,
                              expected_version: s.version,
                            }),
                          })
                        }
                      >
                        {s.state === "complete" ? "Жду ещё" : "Всё получено"}
                      </Button>
                    )}
                  </div>
                </Card>
              ))}
            </div>
            {row.receipts.length > 0 && (
              <ul className="mt-3 space-y-2 text-xs text-ink-2">
                {row.receipts.map((r) => (
                  <li key={r.id} className="flex justify-between gap-2">
                    <span>
                      {dateLabel(r.received_on)} · {r.source} · за{" "}
                      {r.origin_month.slice(0, 7)}
                    </span>
                    <span className="tnum whitespace-nowrap">
                      {money(r.amount)}
                      {(own || actor.leader) && (
                        <button
                          className="ml-2 text-accent-ink"
                          onClick={() =>
                            onForm({
                              title: "Исправить поступление",
                              description:
                                "Укажите правильную итоговую сумму этого поступления. Это заявка на корректировку, исходная запись сохранится.",
                              path: "/fund/corrections",
                              fields: [
                                {
                                  ...amountField,
                                  name: "corrected_amount",
                                  label: "Правильная сумма, ₽",
                                  value: r.amount,
                                  min: "0",
                                },
                                reasonField,
                              ],
                              body: (v, id) => ({
                                request_id: id,
                                employee_id: row.employee.id,
                                origin_month: r.origin_month,
                                kind: "source",
                                reference_id: r.id,
                                corrected_amount: v.corrected_amount,
                                reason: v.reason,
                              }),
                            })
                          }
                        >
                          Исправить
                        </button>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {own && (
              <Button
                className="mt-3"
                onClick={() => onForm(receiptForm(row, report.month, today))}
              >
                Добавить полученную выплату
              </Button>
            )}
          </section>
          <section>
            <h3 className="font-semibold">Отпуск и исключения</h3>
            <p className="mt-2 text-sm text-ink-2">
              {vacation.error
                ? "Рабочий год и начальный остаток отпуска ещё не подтверждены."
                : vacation.data
                  ? `Доступно дней: ${String(vacation.data.at(-1)?.available ?? "—")} · запланировано: ${String(vacation.data.at(-1)?.reserved ?? "—")}`
                  : "Загрузка…"}
            </p>
            {(own || actor.leader) && (
              <Button
                className="mt-3"
                onClick={() => onForm(timeForm(row.employee.id, today))}
              >
                Согласовать отсутствие или опоздание
              </Button>
            )}
          </section>
          {actor.leader && (
            <Button
              onClick={() =>
                onForm({
                  title: "Рабочие интервалы и эффективность",
                  description:
                    "Каждая строка: 09:00–13:00 80%. Для ночной работы укажите дату начала. Правка создаёт новую версию; закрытое начисление меняется отдельной корректировкой.",
                  path: `/fund/members/${row.employee.id}/work`,
                  fields: [
                    {
                      name: "day",
                      label: "Дата начала работы",
                      type: "date",
                      value: report.month,
                    },
                    {
                      name: "intervals",
                      label: "Интервалы и эффективность",
                      type: "textarea",
                    },
                    reasonField,
                  ],
                  body: (v) => ({
                    day: v.day,
                    reason: v.reason,
                    intervals: v
                      .intervals!.split("\n")
                      .filter((x) => x.trim())
                      .map((line) => {
                        const m =
                          /^(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})\s+(\d{1,3})%?$/.exec(
                            line.trim(),
                          );
                        if (!m || Number(m[2]) > 59 || Number(m[4]) > 59)
                          throw new Error("Формат строки: 09:00–13:00 80%");
                        return {
                          start: Number(m[1]) * 3600 + Number(m[2]) * 60,
                          end: Number(m[3]) * 3600 + Number(m[4]) * 60,
                          efficiency: Number(m[5]),
                        };
                      }),
                  }),
                })
              }
            >
              Исправить часы
            </Button>
          )}
          {actor.leader &&
            vacation.data?.map((y) => (
              <Button
                key={y.id}
                onClick={() =>
                  onForm({
                    title: "Корректировка отпускного остатка",
                    description: `Рабочий год ${dateLabel(y.start)} — ${dateLabel(y.end)}. Положительное число добавляет дни, отрицательное уменьшает остаток.`,
                    path: `/fund/vacations/${y.id}/adjust`,
                    fields: [
                      {
                        name: "adjustment",
                        label: "Общая корректировка рабочего года, дней",
                        type: "number",
                        step: "1",
                        value: String(y.adjustment_days),
                      },
                      reasonField,
                    ],
                    body: (v) => ({
                      adjustment: Number(v.adjustment),
                      expected_adjustment: y.adjustment_days,
                      reason: v.reason,
                    }),
                  })
                }
              >
                Поправить остаток отпуска за {y.start.slice(0, 4)}
              </Button>
            ))}
          {report.closed && (own || actor.leader) && (
            <Button
              onClick={() =>
                onForm({
                  title: "Исправить компенсации месяца",
                  path: "/fund/corrections",
                  fields: [
                    {
                      ...amountField,
                      name: "corrected_amount",
                      label: "Правильный итог компенсаций, ₽",
                      min: "0",
                      value: row.amounts?.compensation,
                    },
                    reasonField,
                  ],
                  body: (v, id) => ({
                    request_id: id,
                    employee_id: row.employee.id,
                    origin_month: report.month,
                    kind: "compensation",
                    corrected_amount: v.corrected_amount,
                    reason: v.reason,
                  }),
                })
              }
            >
              Корректировка компенсаций
            </Button>
          )}
          {report.closed && (own || actor.leader) && (
            <Button
              onClick={() =>
                onForm({
                  title: "Исправление закрытого расчёта",
                  description:
                    "Начисление будет пересчитано по исправленным данным времени с сохранёнными условиями месяца. Разница поступит на согласование руководителю.",
                  path: "/fund/corrections",
                  fields: [
                    {
                      name: "change_terms",
                      label: "Исправить также условия оплаты этого месяца",
                      type: "checkbox",
                    },
                    ...(row.inputs?.conditions.flatMap((c, i) => [
                      {
                        name: `target_${i}`,
                        label: `Целевая сумма с ${dateLabel(c.start)}, ₽`,
                        type: "number" as const,
                        min: "0",
                        value: c.target,
                        when: (v: Record<string, string>) =>
                          v.change_terms === "true",
                      },
                      {
                        name: `share_${i}`,
                        label: "Доля ставки",
                        type: "number" as const,
                        min: "0.0001",
                        step: "0.0001",
                        value: c.share,
                        when: (v: Record<string, string>) =>
                          v.change_terms === "true",
                      },
                    ]) ?? []),
                    reasonField,
                  ],
                  submit: "Рассчитать разницу",
                  body: (v, id) => ({
                    request_id: id,
                    employee_id: row.employee.id,
                    origin_month: report.month,
                    kind: "salary",
                    reason: v.reason,
                    corrected_conditions:
                      v.change_terms === "true"
                        ? row.inputs?.conditions.map((c, i) => ({
                            ...c,
                            target: v[`target_${i}`],
                            share: v[`share_${i}`],
                          }))
                        : null,
                  }),
                })
              }
            >
              Предложить корректировку
            </Button>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
