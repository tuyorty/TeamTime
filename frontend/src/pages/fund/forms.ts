import type { FundOverview, FundRow, TeamActor } from "@/api/fund";
import { money } from "@/lib/format";
import {
  amountField,
  reasonField,
  type FormField,
  type FormSpec,
} from "./formTypes";
import { operationNames, timeNames } from "./format";

export const personField = (data: FundOverview, value?: number): FormField => ({
  name: "employee_id",
  label: "Участник",
  type: "select",
  value: value ? String(value) : undefined,
  options: data.members.map((m) => ({
    value: String(m.id),
    label: m.full_name,
  })),
});
export const monthField = (month: string): FormField => ({
  name: "month",
  label: "Расчётный месяц",
  type: "month",
  value: month.slice(0, 7),
});
export function receiptForm(
  row: FundRow,
  month: string,
  today: string,
): FormSpec {
  return {
    title: "Полученная выплата",
    description:
      "Укажите фактически полученную сумму на руки. Несколько выплат одного источника суммируются.",
    path: "/fund/receipts",
    fields: [
      monthField(month),
      {
        name: "source",
        label: "Источник",
        type: row.sources.length ? "select" : "text",
        options: row.sources.map((s) => ({ value: s.name, label: s.name })),
      },
      amountField,
      {
        name: "date",
        label: "Дата получения",
        type: "date",
        value: today,
        max: today,
      },
    ],
    body: (v, id) => ({
      request_id: id,
      origin_month: `${v.month}-01`,
      source: v.source,
      amount: v.amount,
      received_on: v.date,
    }),
  };
}
export function claimForm(month: string, today: string): FormSpec {
  return {
    title: "Расход за свой счёт",
    description:
      "Руководитель проверит заявку. После одобрения сумма попадёт в обязательства фонда.",
    path: "/fund/claims",
    fields: [
      { name: "title", label: "На что потрачено" },
      amountField,
      {
        name: "date",
        label: "Дата покупки",
        type: "date",
        value: today,
        max: today,
      },
      monthField(month),
    ],
    body: (v, id) => ({
      request_id: id,
      title: v.title,
      amount: v.amount,
      spent_on: v.date,
      month: `${v.month}-01`,
    }),
  };
}
export function operationForm(
  data: FundOverview,
  actor: TeamActor,
  today: string,
): FormSpec {
  const kinds = [
    "contribution",
    "interest",
    "expense",
    "refund",
    "payment",
    "transfer",
    "loan_issue",
    "loan_repayment",
    "overpayment_return",
    "compensation_return",
    "cash_correction",
    ...(actor.leader ? ["loan_offset", "allocate"] : []),
  ];
  const cash = (v: Record<string, string>) =>
    !["loan_offset", "allocate"].includes(v.kind!);
  const personal = (v: Record<string, string>) =>
    [
      "payment",
      "loan_issue",
      "loan_repayment",
      "overpayment_return",
      "compensation_return",
      "loan_offset",
      "allocate",
    ].includes(v.kind!);
  const allocations = data.obligations
    .filter((o) => Number(o.due) > 0)
    .map((o) => ({
      name: `allocation_${o.id}`,
      label: `${o.month.slice(0, 7)} · ${o.kind === "salary" ? "Доплата" : "Компенсация"} · остаток ${money(o.due)}`,
      type: "number" as const,
      min: "0",
      max: o.due,
      optional: true,
      when: (v: Record<string, string>) =>
        ["payment", "allocate", "loan_offset"].includes(v.kind!) &&
        Number(v.employee_id) === o.employee_id,
    }));
  return {
    title: "Операция фонда",
    description:
      "Сначала сохранится черновик. Движение денег проведёт ответственный за корзину после проверки.",
    path: "/fund/operations",
    fields: [
      {
        name: "kind",
        label: "Вид операции",
        type: "select",
        options: kinds.map((k) => ({ value: k, label: operationNames[k]! })),
      },
      amountField,
      {
        name: "date",
        label: "Дата операции",
        type: "date",
        value: today,
        max: today,
      },
      {
        name: "basket_id",
        label: "Корзина",
        type: "select",
        options: data.baskets
          .filter((b) => b.owner_id === actor.employee_id)
          .map((b) => ({ value: String(b.id), label: b.name })),
        when: cash,
      },
      {
        name: "target_basket_id",
        label: "Куда переводим",
        type: "select",
        options: data.baskets.map((b) => ({
          value: String(b.id),
          label: b.name,
        })),
        when: (v) => v.kind === "transfer",
      },
      { ...personField(data), when: personal },
      {
        name: "loan_id",
        label: "Заём",
        type: "select",
        options: data.loans
          .filter((l) => !l.issued || Number(l.outstanding) > 0)
          .map((l) => ({
            value: String(l.id),
            label: `#${l.id} · ${data.members.find((m) => m.id === l.employee_id)?.short_name} · ${money(l.amount)}`,
          })),
        when: (v) =>
          ["loan_issue", "loan_repayment", "loan_offset"].includes(v.kind!),
      },
      {
        name: "original_id",
        label: "Исходный расход",
        type: "select",
        options: data.operations
          .filter((o) => o.kind === "expense" && o.state === "posted")
          .map((o) => ({
            value: String(o.id),
            label: `#${o.id} · ${o.reason} · ${money(o.amount)}`,
          })),
        when: (v) => v.kind === "refund",
      },
      {
        name: "compensation_id",
        label: "Отрицательный остаток компенсации",
        type: "select",
        options: data.obligations
          .filter((o) => o.kind === "compensation" && Number(o.due) < 0)
          .map((o) => ({
            value: String(o.id),
            label: `${data.members.find((m) => m.id === o.employee_id)?.short_name} · ${o.title} · ${money(o.due)}`,
          })),
        when: (v) => v.kind === "compensation_return",
      },
      {
        name: "direction",
        label: "Изменение",
        type: "select",
        options: [
          { value: "1", label: "Увеличить остаток" },
          { value: "-1", label: "Уменьшить остаток" },
        ],
        when: (v) => v.kind === "cash_correction",
      },
      ...allocations,
      reasonField,
    ],
    body: (v, id) => ({
      request_id: id,
      kind: v.kind,
      amount: v.amount,
      occurred_on: v.date,
      basket_id: cash(v) ? Number(v.basket_id) : null,
      target_basket_id:
        v.kind === "transfer" ? Number(v.target_basket_id) : null,
      employee_id: personal(v) ? Number(v.employee_id) : null,
      loan_id: ["loan_issue", "loan_repayment", "loan_offset"].includes(v.kind!)
        ? Number(v.loan_id)
        : null,
      original_id:
        v.kind === "refund"
          ? Number(v.original_id)
          : v.kind === "compensation_return"
            ? Number(v.compensation_id)
            : null,
      correction_direction: Number(v.direction || 1),
      allocations: allocations
        .filter((f) => f.when(v) && Number(v[f.name]) > 0)
        .map((f) => ({
          obligation_id: Number(f.name.slice(11)),
          amount: v[f.name],
        })),
      reason: v.reason,
    }),
  };
}
export function timeForm(employeeId: number, today: string): FormSpec {
  return {
    title: "Отсутствие или исключение",
    description: "Изменение учитывается в расчёте после решения руководителя.",
    path: `/fund/time-requests/${employeeId}`,
    fields: [
      {
        name: "kind",
        label: "Что согласовать",
        type: "select",
        options: Object.entries(timeNames).map(([value, label]) => ({
          value,
          label,
        })),
      },
      { name: "start", label: "С даты", type: "date", value: today },
      {
        name: "end",
        label: "По дату включительно",
        type: "date",
        value: today,
        when: (v) => ["vacation", "sick", "trip"].includes(v.kind!),
      },
      {
        name: "minutes",
        label: "Исключить минут опоздания",
        type: "number",
        min: "1",
        step: "1",
        when: (v) => v.kind === "waiver",
      },
      reasonField,
    ],
    body: (v, id) => {
      const days: string[] = [];
      const start = new Date(`${v.start}T12:00:00Z`);
      const end = ["vacation", "sick", "trip"].includes(v.kind!)
        ? v.end!
        : v.start!;
      for (
        let i = 0;
        i < 366 && start.toISOString().slice(0, 10) <= end;
        i++, start.setUTCDate(start.getUTCDate() + 1)
      )
        days.push(start.toISOString().slice(0, 10));
      if (!days.length || days.at(-1) !== end)
        throw new Error("Проверьте границы периода: не более 366 дней");
      return {
        request_id: id,
        kind: v.kind,
        days,
        seconds: v.kind === "waiver" ? Number(v.minutes) * 60 : 0,
        reason: v.reason,
      };
    },
  };
}
