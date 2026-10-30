import { useEffect, useMemo, useState } from "react";

import { api } from "@/api/client";
import { keys, useAdminMutation, useSettings, useMeta } from "@/api/queries";
import type { AppSettings, PenaltyScale } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Switch, Textarea } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { WEEKDAYS_SHORT, hm } from "@/lib/format";

import { penaltyHours } from "../month/penalty";
import { CalculationHistory } from "./CalculationHistory";

/** Эмодзи, которые Bot API разрешает для реакций (полный список проверяет сервер). */
const REACTIONS = ["👌", "👍", "🤔", "✍", "👀", "🫡", "🔥", "🎉", "💯", "🤝", "😐", "🙏", "⚡", "🏆"];
const TIMEZONES = [
  "Asia/Yekaterinburg",
  "Europe/Moscow",
  "Europe/Samara",
  "Asia/Omsk",
  "Asia/Novosibirsk",
  "Asia/Krasnoyarsk",
  "Asia/Irkutsk",
  "Asia/Vladivostok",
  "Europe/Kaliningrad",
];

function num(v: string): number {
  return Number(v.replace(",", "."));
}

type Penalty = NonNullable<AppSettings["penalty"]>;
type Bot = NonNullable<AppSettings["bot"]>;
type Form = Omit<AppSettings, "penalty" | "bot"> & { penalty: Penalty; bot: Bot };

const DEFAULT_PENALTY: Penalty = {
  soft_limit_h: "5",
  hard_limit_h: "12",
  quad_coef: "3/14",
  hard_value_h: "22.5",
  tail_slope: "4",
};
const DEFAULT_BOT: Bot = {
  feedback: "reaction",
  reaction_ok: "👌",
  reaction_warn: "🤔",
  reaction_edit: "✍",
  reminders_enabled: true,
  reminder_delay_minutes: 15,
};

function scaleOf(p: Penalty): PenaltyScale {
  const frac = (v: string) => {
    const [a, b] = v.split("/");
    return b ? num(a!) / num(b) : num(v);
  };
  return {
    soft_limit_h: frac(p.soft_limit_h),
    hard_limit_h: frac(p.hard_limit_h),
    quad_coef: frac(p.quad_coef),
    hard_value_h: frac(p.hard_value_h),
    tail_slope: frac(p.tail_slope),
    problems: [],
  };
}

export function SettingsTab() {
  const { data } = useSettings();
  const today = useMeta().data?.today ?? new Date().toISOString().slice(0, 10);
  const [effectiveMonth, setEffectiveMonth] = useState(today.slice(0, 7));
  const [form, setForm] = useState<Form | null>(null);
  const [holidays, setHolidays] = useState("");
  useEffect(() => {
    if (data) {
      setForm({
        ...data,
        penalty: { ...DEFAULT_PENALTY, ...data.penalty },
        bot: { ...DEFAULT_BOT, ...data.bot },
      });
      setHolidays((data.holidays ?? []).join("\n"));
    }
  }, [data]);

  const save = useAdminMutation(
    () =>
      api.put<{ warnings: string[] }>(`/admin/settings?effective_from=${effectiveMonth}-01`, {
        ...form,
        holidays: holidays.split(/[\s,;]+/).filter(Boolean),
      }),
    {
      success: (r) =>
        r.warnings.length ? `Сохранено. Внимание: ${r.warnings.join("; ")}` : "Настройки сохранены",
      invalidate: [
        [...keys.settings],
        ["meta"],
        ["week"],
        ["month"],
        ["today"],
        ["day-summary"],
        ["employee"],
        ["calculation-history"],
      ],
    },
  );

  const scale = useMemo(() => (form ? scaleOf(form.penalty) : null), [form]);
  if (!form || !scale) return <Skeleton className="h-96" />;
  const gap = penaltyHours(scale.hard_limit_h, { ...scale, hard_value_h: Infinity }) - scale.hard_value_h;
  const continuous =
    Math.abs(
      scale.soft_limit_h +
        (scale.hard_limit_h - scale.soft_limit_h) *
          (1 + scale.quad_coef * (scale.hard_limit_h - scale.soft_limit_h)) -
        scale.hard_value_h,
    ) < 1e-6;
  const badDates = holidays.split(/[\s,;]+/).filter((d) => d && !/^\d{4}-\d{2}-\d{2}$/.test(d));
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm({ ...form, [k]: v });
  const setPenalty = (k: keyof Penalty, v: string) =>
    setForm({ ...form, penalty: { ...form.penalty, [k]: v } });
  const setBot = <K extends keyof Bot>(k: K, v: Bot[K]) => setForm({ ...form, bot: { ...form.bot, [k]: v } });

  return (
    <form
      className="grid gap-5"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <Panel title="С какого месяца действуют условия">
        <Field
          label="Месяц применения"
          hint="Допуски, календарь и штрафы сохраняются по месяцам. Настройки бота применяются сразу. Будущие версии видны в истории ниже; форма при открытии показывает действующие условия."
        >
          <Input
            type="month"
            required
            min="2000-01"
            max="2100-12"
            className="max-w-52"
            value={effectiveMonth}
            onChange={(e) => setEffectiveMonth(e.target.value)}
          />
        </Field>
        <div className="mt-4">
          <CalculationHistory
            onSelect={(month, value) => {
              setEffectiveMonth(month);
              setForm({ ...form, ...value, bot: form.bot, penalty: { ...form.penalty, ...value.penalty } });
              setHolidays((value.holidays ?? []).join("\n"));
            }}
          />
        </div>
      </Panel>
      <div className="grid gap-5 lg:grid-cols-2">
        <Panel
          title="Расчёт дня"
          description="Влияет на опоздания, ранний уход и недоработку во всех отчётах"
        >
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Допуск опоздания, мин" hint="В исходной таблице 0">
              <Input
                inputMode="numeric"
                value={form.late_tolerance_min ?? 0}
                onChange={(e) => set("late_tolerance_min", Number(e.target.value) || 0)}
              />
            </Field>
            <Field label="Ранний уход, мин">
              <Input
                inputMode="numeric"
                value={form.early_tolerance_min ?? 0}
                onChange={(e) => set("early_tolerance_min", Number(e.target.value) || 0)}
              />
            </Field>
            <Field label="Недоработка, мин">
              <Input
                inputMode="numeric"
                value={form.undertime_tolerance_min ?? 0}
                onChange={(e) => set("undertime_tolerance_min", Number(e.target.value) || 0)}
              />
            </Field>
          </div>
          <p className="mt-2 text-[12px] text-ink-3">
            Опоздание в пределах допуска не считается, сверх допуска считается целиком.
          </p>
          <Field
            label="Предупредить об изменении расписания, ч"
            hint="Правка, присланная раньше этого срока до начала дня, применяется сама. Позже — ждёт подтверждения в инбоксе."
            className="mt-4 sm:w-72"
          >
            <Input
              inputMode="numeric"
              value={form.plan_notice_hours ?? 12}
              onChange={(e) => set("plan_notice_hours", Number(e.target.value) || 0)}
            />
          </Field>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Field label="Часовой пояс команды">
              <Select value={form.timezone} onChange={(e) => set("timezone", e.target.value)}>
                {[...new Set([form.timezone!, ...TIMEZONES])].map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Норма по умолчанию, ч/мес" hint="Для новых сотрудников">
              <Input
                inputMode="numeric"
                value={form.default_norm_hours ?? 160}
                onChange={(e) => set("default_norm_hours", Number(e.target.value) || 0)}
              />
            </Field>
          </div>
          <fieldset className="mt-4">
            <legend className="mb-1.5 text-[13px] font-medium">Выходные без плана</legend>
            <div className="flex flex-wrap gap-1.5">
              {WEEKDAYS_SHORT.map((d, i) => {
                const on = (form.weekly_off ?? []).includes(i);
                return (
                  <button
                    key={d}
                    type="button"
                    aria-pressed={on}
                    onClick={() =>
                      set(
                        "weekly_off",
                        on ? form.weekly_off!.filter((x) => x !== i) : [...(form.weekly_off ?? []), i],
                      )
                    }
                    className={
                      on
                        ? "h-7 rounded-md bg-surface-3 px-2.5 text-[12px] font-medium"
                        : "h-7 rounded-md border border-line px-2.5 text-[12px] text-ink-2"
                    }
                  >
                    {d}
                  </button>
                );
              })}
            </div>
            <p className="mt-1.5 text-[12px] text-ink-3">
              Суббота по умолчанию рабочая по плану сотрудника, воскресенье — выходной.
            </p>
          </fieldset>
          <Field
            className="mt-4"
            label="Праздники"
            error={badDates.length ? `Не дата: ${badDates.join(", ")}` : null}
            hint="По одной дате ГГГГ-ММ-ДД в строке. В праздник план отменяется"
          >
            <Textarea value={holidays} onChange={(e) => setHolidays(e.target.value)} rows={4} />
          </Field>
        </Panel>

        <Panel title="Шкала штрафа" description="Опоздания(−) за месяц от суммы опозданий x (в часах)">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Первый порог, ч" hint="До него штраф = x">
              <Input
                value={form.penalty.soft_limit_h ?? ""}
                onChange={(e) => setPenalty("soft_limit_h", e.target.value)}
              />
            </Field>
            <Field label="Второй порог, ч">
              <Input
                value={form.penalty.hard_limit_h ?? ""}
                onChange={(e) => setPenalty("hard_limit_h", e.target.value)}
              />
            </Field>
            <Field label="Коэффициент между порогами" hint="Можно дробью: 3/14">
              <Input
                value={form.penalty.quad_coef ?? ""}
                onChange={(e) => setPenalty("quad_coef", e.target.value)}
              />
            </Field>
            <Field label="Штраф на втором пороге, ч">
              <Input
                value={form.penalty.hard_value_h ?? ""}
                onChange={(e) => setPenalty("hard_value_h", e.target.value)}
              />
            </Field>
            <Field label="Наклон после второго порога">
              <Input
                value={form.penalty.tail_slope ?? ""}
                onChange={(e) => setPenalty("tail_slope", e.target.value)}
              />
            </Field>
          </div>
          <div className="mt-4 rounded-md bg-bg p-3 text-[13px] tnum">
            <p className="mb-1 font-medium">Проверка</p>
            {[2 + 17 / 60, 5 + 40 / 60, 6 + 45 / 60, 12, 13].map((x) => (
              <p key={x} className="text-ink-2">
                {hm(x * 3600)} → {hm(penaltyHours(x, scale) * 3600)}
              </p>
            ))}
            <p className={continuous ? "mt-1 text-accent-ink" : "mt-1 text-deviation-ink"}>
              {continuous
                ? "Шкала непрерывна на втором пороге"
                : `Шкала разрывна на втором пороге (${gap > 0 ? "+" : ""}${gap.toFixed(2)} ч)`}
            </p>
          </div>
        </Panel>

        <Panel title="Бот" description="Как бот отмечает сообщения в теме">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Отметка в теме">
              <Select
                value={form.bot.feedback ?? "reaction"}
                onChange={(e) => setBot("feedback", e.target.value as "reaction" | "reply")}
              >
                <option value="reaction">реакция (тема остаётся чистой)</option>
                <option value="reply">короткий ответ</option>
              </Select>
            </Field>
            <div />
            {(
              [
                ["reaction_ok", "Разобрано"],
                ["reaction_warn", "Есть вопросы"],
                ["reaction_edit", "Правка учтена"],
              ] as const
            ).map(([k, label]) => (
              <Field key={k} label={label}>
                <Select value={form.bot[k] ?? ""} onChange={(e) => setBot(k, e.target.value)}>
                  {[...new Set([form.bot[k] ?? "👌", ...REACTIONS])].map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </Select>
              </Field>
            ))}
          </div>
          <p className="mt-2 text-[12px] text-ink-3">
            ✅ и ⚠️ Telegram не разрешает ставить реакциями ботам, поэтому их нет в списке.
          </p>
          <div className="mt-4 flex flex-wrap items-end gap-4">
            <Switch
              checked={!!form.bot.reminders_enabled}
              onChange={(v) => setBot("reminders_enabled", v)}
              label="Напоминать о дейлике в личке"
            />
            <Field label="Через, мин" hint="После окончания последнего рабочего интервала">
              <Input
                className="w-24"
                type="number"
                min={1}
                max={240}
                required
                value={form.bot.reminder_delay_minutes ?? 15}
                onChange={(e) => setBot("reminder_delay_minutes", Number(e.target.value))}
              />
            </Field>
          </div>
          <p className="mt-3 text-[12px] text-ink-3">
            Одно напоминание за рабочий день, если дейлик не получен. Учитывается переход смены через полночь.
            Для уведомлений сотруднику нужно один раз написать боту в личку, например /start.
          </p>
        </Panel>
      </div>
      <div className="sticky bottom-20 flex justify-end lg:bottom-4">
        <Button
          type="submit"
          variant="primary"
          size="lg"
          className="shadow-panel"
          disabled={save.isPending || badDates.length > 0}
        >
          Сохранить настройки
        </Button>
      </div>
    </form>
  );
}
