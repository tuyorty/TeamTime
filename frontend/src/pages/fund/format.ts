export const operationNames: Record<string, string> = {
  compensation_return: "Возврат излишней компенсации",
  contribution: "Взнос в фонд",
  interest: "Проценты на остаток",
  expense: "Расход фонда",
  refund: "Возврат расхода",
  payment: "Выплата сотруднику",
  transfer: "Между корзинами",
  loan_issue: "Выдача займа",
  loan_repayment: "Возврат займа",
  loan_offset: "Зачёт займа из выплаты",
  overpayment_return: "Возврат переплаты",
  allocate: "Распределение выплаты",
  cash_correction: "Корректировка остатка",
  opening: "Начальный остаток",
  obligation: "Начисление обязательства",
  closure: "Закрытие месяца",
  compensation_correction: "Корректировка компенсации",
  import_payment: "Выплата из архива",
  salary_accrual: "Начисление месяца",
  compensation_accrual: "Компенсация",
  reversal: "Сторно",
  month_close: "Закрытие месяца",
};
export const timeNames: Record<string, string> = {
  vacation: "Отпуск",
  sick: "Больничный",
  trip: "Командировка",
  missed: "Пропуск смены",
  waiver: "Уважительное опоздание",
  no_work: "День без работы",
};
export const correctionNames: Record<string, string> = {
  salary: "Начисление",
  source: "Выплата источника",
  compensation: "Компенсация",
  bonus: "Премия",
};
export const stateNames: Record<string, string> = {
  pending: "На согласовании",
  approved: "Подтверждено",
  rejected: "Отклонено",
  cancelled: "Отменено",
  draft: "Ждёт подтверждения",
  posted: "Проведено",
  unknown: "Нет ответа",
  partial: "Ждём ещё",
  complete: "Всё получено",
};
export function hours(seconds: number) {
  const s = Math.round(seconds);
  return `${s < 0 ? "−" : ""}${Math.floor(Math.abs(s) / 3600)}:${String(Math.floor(Math.abs(s) / 60) % 60).padStart(2, "0")}`;
}
export function dateLabel(value: string) {
  return new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString("ru-RU");
}
export function formatShare(value: string) {
  return Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 4 });
}
export const tableClass =
  "w-full text-left text-[13px] [&_th]:whitespace-nowrap [&_th]:bg-surface-2 [&_th]:px-3 [&_th]:py-3 [&_th]:font-medium [&_th]:text-ink-2 [&_td]:border-t [&_td]:border-line [&_td]:px-3 [&_td]:py-3";
