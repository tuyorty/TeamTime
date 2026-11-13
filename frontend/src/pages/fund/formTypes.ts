export type FormField = {
  name: string;
  label: string;
  type?:
    | "text"
    | "number"
    | "date"
    | "month"
    | "textarea"
    | "select"
    | "checkbox";
  value?: string;
  hint?: string;
  optional?: boolean;
  options?: { value: string; label: string }[];
  min?: string;
  max?: string;
  step?: string;
  when?: (values: Record<string, string>) => boolean;
};
export type FormSpec = {
  title: string;
  description?: string;
  path: string;
  method?: "post" | "put";
  fields: FormField[];
  submit?: string;
  body: (values: Record<string, string>, id: string) => unknown;
  after?: (result: Record<string, unknown>) => Promise<void>;
};

export const reasonField: FormField = {
  name: "reason",
  label: "Основание",
  type: "textarea",
};
export const amountField: FormField = {
  name: "amount",
  label: "Сумма, ₽",
  type: "number",
  min: "0.01",
};
export function decisionForm(
  path: string,
  title: string,
  approve: boolean,
): FormSpec {
  return {
    path,
    title,
    submit: approve ? "Подтвердить" : "Отклонить",
    fields: [reasonField],
    body: (v) => ({ approve, reason: v.reason }),
  };
}
