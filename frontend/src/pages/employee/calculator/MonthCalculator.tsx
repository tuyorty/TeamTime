import { useQuery } from "@tanstack/react-query";
import { ArrowRight, RotateCcw, Target } from "lucide-react";
import { useState } from "react";

import { api } from "@/api/client";
import type { EmployeeDetail, Finance, FinanceRow } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { hm, money } from "@/lib/format";

import { Breakdown, EfficiencyField, HoursField, Metric } from "./fields";
import { readHours, readNumber } from "./input";
import { calculateMonth, calculateTarget, type MoneyBreakdown } from "./model";

export function MonthCalculator({ data, today, suggestedEfficiency, suggestionId }: {
  data: EmployeeDetail; today: string; suggestedEfficiency?: number; suggestionId: number;
}) {
  const profileMonth = data.start.slice(0, 7) === data.end.slice(0, 7) ? data.start.slice(0, 7) : today.slice(0, 7);
  const [month, setMonth] = useState(profileMonth);
  const [manual, setManual] = useState(false);
  const [revision, setRevision] = useState(0);
  const validMonth = /^\d{4}-(0[1-9]|1[0-2])$/.test(month);
  const [year, number] = month.split("-").map(Number);
  const query = useQuery({
    queryKey: ["calculator-finance", year, number],
    queryFn: () => api.get<Finance>(`/finances/${year}/${number}`),
    enabled: validMonth, retry: false,
  });
  const row = query.data?.rows.find((item) => item.employee.id === data.employee.id);
  return <div className="space-y-4">
    <div className="flex flex-wrap items-end justify-between gap-3">
      <Field label="Месяц расчёта"><Input type="month" value={month} min="2000-01" max="2100-12" className="h-10 w-44"
        onChange={(event) => { setMonth(event.target.value); setManual(false); }} /></Field>
      <p className="max-w-sm text-[12px] text-ink-2">Полный оклад за норму + переработка по той же ставке + проектные премии.</p>
    </div>
    {!validMonth ? <p role="alert" className="text-sm text-late-ink">Выберите месяц.</p>
      : query.isPending && !manual ? <p role="status" className="py-10 text-center text-sm text-ink-2">Загружаем условия и часы сотрудника…</p>
        : !row && !manual ? <div className="rounded-lg border border-line bg-surface-2 p-4 text-sm">
          <p>{query.isError ? "Не удалось загрузить финансовые данные." : "В финансовом расчёте за этот месяц нет сотрудника."}</p>
          <p className="mt-1 text-[12px] text-ink-2">Можно повторить загрузку или указать все условия вручную.</p>
          <div className="mt-3 flex flex-wrap gap-2"><Button onClick={() => void query.refetch()}>Повторить</Button><Button variant="ghost" onClick={() => setManual(true)}>Ввести вручную</Button></div>
        </div> : <MonthForm key={`${month}:${manual}:${revision}`} row={manual ? undefined : row} suggestedEfficiency={suggestedEfficiency} suggestionId={suggestionId}
          onReset={() => setRevision((value) => value + 1)} />}
  </div>;
}

function MonthForm({ row, suggestedEfficiency, suggestionId, onReset }: { row?: FinanceRow; suggestedEfficiency?: number; suggestionId: number; onReset: () => void }) {
  // Снимок при открытии: фоновое обновление API не затирает введённый сценарий.
  const [source] = useState(row);
  const summary = source?.summary;
  const [mode, setMode] = useState<"target" | "hours">("target");
  const [rate, setRate] = useState(summary ? String(Number(summary.hourly_rate)) : "");
  const [contract, setContract] = useState(summary ? hm(summary.contract_norm_sec) : "");
  const [norm, setNorm] = useState(summary ? hm(summary.norm_sec) : "");
  const [bonuses, setBonuses] = useState(source ? String(Number(source.amounts.project_bonuses)) : "0");
  const [penalty, setPenalty] = useState(hm(summary?.penalty_sec ?? 0));
  const [current, setCurrent] = useState(hm(summary?.result_sec ?? 0));
  const [worked, setWorked] = useState(hm(summary?.worked_sec ?? 0));
  const [effective, setEffective] = useState<string | null>(summary && suggestedEfficiency === undefined ? hm(summary.result_sec) : null);
  const initialEfficiency = summary?.worked_sec ? Math.min(100, summary.result_sec / summary.worked_sec * 100) : 100;
  const [efficiency, setEfficiency] = useState(String(suggestedEfficiency ?? Number(initialEfficiency.toFixed(2))));
  const [previousSuggestion, setPreviousSuggestion] = useState(suggestionId);
  if (previousSuggestion !== suggestionId) {
    setPreviousSuggestion(suggestionId);
    if (suggestedEfficiency !== undefined) { setEfficiency(String(suggestedEfficiency)); setEffective(null); }
  }
  const [target, setTarget] = useState(source ? String(Math.ceil(Number(source.amounts.total) + Number(summary!.hourly_rate) * 20)) : "");
  const [days, setDays] = useState("");
  // Длительности API могут содержать секунды: сохраняем точность, пока поле не изменено.
  const duration = (text: string, original?: number) => original !== undefined && text === hm(original) ? original : readHours(text);
  const terms = {
    contractNormSec: duration(contract, summary?.contract_norm_sec), normSec: duration(norm, summary?.norm_sec),
    hourlyRate: rate, projectBonuses: bonuses, penaltySec: duration(penalty, summary?.penalty_sec),
  };
  const workedSec = duration(worked, summary?.worked_sec);
  const efficiencyPercent = readNumber(efficiency);
  const effectiveText = effective ?? (Number.isFinite(workedSec * efficiencyPercent) ? hm(workedSec * efficiencyPercent / 100) : "");
  const goal = calculateTarget({ ...terms, targetAmount: target, currentEffectiveSec: duration(current, summary?.result_sec), efficiencyPercent });
  const forecast = calculateMonth({ ...terms, workedSec, efficiencyPercent,
    ...(effective !== null ? { effectiveSec: duration(effective, summary?.result_sec) } : {}),
  });
  const result = mode === "target" ? goal : forecast;
  const amount = mode === "target" ? goal.ok ? goal.value.projected ?? goal.value.current : null : forecast.ok ? forecast.value : null;
  const changeEfficiency = (text: string) => { setEfficiency(text); setEffective(null); };
  const dayCount = readNumber(days);
  const validDays = Number.isInteger(dayCount) && dayCount > 0 && dayCount <= 31;
  const perDay = goal.ok && goal.value.additionalWorkedSec !== null && validDays
    ? Math.ceil(goal.value.additionalWorkedSec / dayCount / 60) * 60 : null;

  return <>
    <div className="grid grid-cols-2 gap-1 rounded-lg border border-line bg-surface-2 p-1" aria-label="Способ расчёта дохода">
      <Button className="h-auto whitespace-normal py-2" variant={mode === "target" ? "primary" : "ghost"} aria-pressed={mode === "target"} onClick={() => setMode("target")}><Target />Цель по сумме</Button>
      <Button className="h-auto whitespace-normal py-2" variant={mode === "hours" ? "primary" : "ghost"} aria-pressed={mode === "hours"} onClick={() => setMode("hours")}>Расчёт по часам<ArrowRight /></Button>
    </div>
    {!source ? <p className="rounded-md bg-deviation-soft p-3 text-[12px] text-deviation-ink">Ручной расчёт. Укажите ставку и обе нормы в условиях ниже; часы, премии и штрафы из таблицы не загружены.</p> : null}
    <div className="grid items-start gap-5 md:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <div className="min-w-0 space-y-5">
        {mode === "target" ? <>
          <Field label="Хочу получить, ₽"><Input inputMode="decimal" value={target} onChange={(event) => setTarget(event.target.value)} className="h-12 text-xl font-semibold" /></Field>
          <EfficiencyField label="Эффективность оставшихся часов, %" value={efficiency} onChange={changeEfficiency} />
          <p className="text-[12px] text-ink-2">Применяется только к будущей работе. Уже учтённые эффективные часы сохраняются.</p>
          <Field label="На сколько рабочих дней распределить" hint="Необязательно. Укажите, сколько дней ещё планируете работать." error={days && !validDays ? "Укажите целое число от 1 до 31." : undefined}>
            <Input type="number" min="1" max="31" step="1" placeholder="Например, 10" value={days} onChange={(event) => setDays(event.target.value)} className="h-10" />
          </Field>
        </> : <>
          <HoursField label="Фактические часы за месяц, ч:мм" value={worked} onChange={(text) => { setWorked(text); setEffective(null); }} hint="Общее время в интервалах. Можно ввести 160:30 или 160,5." />
          <EfficiencyField label="Эффективность за месяц, %" value={efficiency} onChange={changeEfficiency} />
          <HoursField label="Эффективные часы за месяц, ч:мм" value={effectiveText} onChange={(text) => {
            setEffective(text);
            const seconds = readHours(text);
            if (Number.isFinite(seconds) && workedSec > 0 && seconds <= workedSec) setEfficiency(String(Number((seconds / workedSec * 100).toFixed(4))));
          }} hint="Фактические × эффективность. Можно задать вручную; штраф вычитается после этого." />
        </>}
        <details className="rounded-lg border border-line p-4" open={!source || undefined}>
          <summary className="cursor-pointer text-[13px] font-semibold">Условия расчёта</summary>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field label="Ставка, ₽/ч"><Input inputMode="decimal" value={rate} onChange={(event) => setRate(event.target.value)} className="h-10" /></Field>
            <Field label="Проектные премии, ₽"><Input inputMode="decimal" value={bonuses} onChange={(event) => setBonuses(event.target.value)} className="h-10" /></Field>
            <HoursField label="Норма для оклада, ч:мм" value={contract} onChange={setContract} />
            <HoursField label="Норма для переработки, ч:мм" value={norm} onChange={setNorm} hint="С учётом отпусков и командировок." />
            <HoursField label="Штрафное время, ч:мм" value={penalty} onChange={setPenalty} hint="Готовый месячный штраф, а не исходные опоздания." />
            <HoursField label="Уже учтено эффективных часов, ч:мм" value={current} onChange={setCurrent} hint="Исходная точка для цели по сумме, до штрафа." />
          </div>
        </details>
        <Button variant="ghost" size="sm" onClick={onReset}><RotateCcw />Сбросить расчёт</Button>
      </div>
      <section aria-label="Результат расчёта дохода" className="min-w-0 rounded-xl border border-line bg-surface-2/70 p-5">
        {!result.ok ? <p role="alert" className="text-[13px] leading-relaxed text-late-ink">{result.error}</p> : <>
          {mode === "target" && goal.ok ? <>
            <p className="text-[13px] text-ink-2">{goal.value.targetReached ? "Цель уже достигнута по этим условиям" : "Ещё фактического времени"}</p>
            <div data-testid="monthly-needed-actual" className="mt-2 break-words font-display text-[42px] font-semibold leading-none text-accent-ink tnum">{goal.value.additionalWorkedSec === null ? "—" : hm(goal.value.additionalWorkedSec)}</div>
            <p className="mt-2 text-[12px] text-ink-2">часы : минуты · при эффективности {efficiency}%</p>
            {goal.value.unreachable ? <p className="mt-4 rounded-md bg-deviation-soft p-3 text-[13px] text-deviation-ink">{goal.value.unreachable === "zero_rate" ? "При нулевой ставке переработка не увеличит сумму." : "При эффективности 0% новые часы не приближают к цели."}</p> : <>
              <dl className="mt-5 grid grid-cols-2 gap-4">
                <Metric label="Ещё эффективно"><span data-testid="monthly-needed-effective">{hm(goal.value.additionalEffectiveSec ?? 0)}</span></Metric>
                <Metric label="Уже эффективно">{hm(duration(current, summary?.result_sec))}</Metric>
              </dl>
              {!goal.value.targetReached ? <p className="mt-4 text-[12px] text-ink-2">Всего нужно эффективно за месяц: <b className="text-ink tnum">{hm(goal.value.requiredTotalEffectiveSec ?? 0)}</b>, включая покрытие штрафа.</p> : null}
              {perDay !== null ? <p className="mt-4 rounded-md border border-line bg-surface p-3 text-[13px]">В среднем <b className="tnum">{hm(perDay)}</b> в день за оставшиеся {days} раб. дн.</p> : null}
              {perDay !== null && perDay > 86400 ? <p className="mt-2 text-[12px] text-late-ink">Больше 24 часов в день: при таком числе дней цель недостижима.</p> : null}
              <p className="mt-4 text-[12px] leading-relaxed text-ink-2">Дополнительное время округлено вверх до минуты. Оклад выплачивается полностью даже при недоборе нормы.</p>
            </>}
          </> : <>
            <p className="text-[13px] text-ink-2">Расчётная сумма за месяц</p>
            <div data-testid="monthly-total" className="mt-2 break-words font-display text-[30px] font-semibold leading-tight text-accent-ink tnum">{amount ? money(amount.totalPay) : "—"}</div>
            {forecast.ok ? <dl className="mt-5 grid grid-cols-2 gap-4"><Metric label="После штрафа">{hm(forecast.value.creditedSec)}</Metric><Metric label="Переработка">{hm(forecast.value.overtimeSec)}</Metric></dl> : null}
          </>}
          {amount ? <div className="mt-5 border-t border-line pt-4">
            {mode === "target" ? <p className="mb-3 text-[12px] text-ink-2">{goal.ok && goal.value.unreachable ? "По уже учтённым часам" : "Начисления при таком расчёте"} · <b className="text-ink tnum">{money(amount.totalPay)}</b></p> : null}
            <PayBreakdown value={amount} />
          </div> : null}
        </>}
        {source ? <p className="mt-5 border-t border-line pt-3 text-[12px] text-ink-2">Сейчас в финансах: <b className="text-ink tnum">{money(source.amounts.total)}</b>. Условия загружены при открытии калькулятора.</p> : null}
      </section>
    </div>
    <p className="text-[12px] leading-relaxed text-ink-3">Это прикидка по указанным условиям. Новые дейлики, изменения премий и дополнительные штрафы изменят итог. Будущие опоздания автоматически не добавляются.</p>
  </>;
}

function PayBreakdown({ value }: { value: MoneyBreakdown }) {
  return <Breakdown items={[
    { label: "Оклад", value: money(value.salary), amount: value.salary, color: "var(--accent)" },
    { label: "Переработка", value: money(value.overtimePay), amount: value.overtimePay, color: "var(--absence)" },
    { label: "Проектные премии", value: money(value.projectBonuses), amount: value.projectBonuses, color: "var(--deviation)" },
  ]} />;
}
