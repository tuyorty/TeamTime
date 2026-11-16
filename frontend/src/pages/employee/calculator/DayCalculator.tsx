import { ArrowRight, Coffee, Copy, Plus, RotateCcw, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import type { DayCell } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { hm } from "@/lib/format";
import { copyText } from "@/lib/phone";

import { Breakdown, Metric } from "./fields";
import { readNumber } from "./input";
import { calculateDay, serializeDayIntervals, type IntervalDraft } from "./model";

type Row = IntervalDraft & { id: number };
const timeText = (seconds: number) => hm(seconds % 86400).padStart(5, "0");

export function DayCalculator({ day, onMonth }: { day?: DayCell; onMonth: (efficiency: number) => void }) {
  const nextId = useRef(1);
  const [intervals, setIntervals] = useState<Row[]>([{ id: 0, start: "", end: "" }]);
  const [breaks, setBreaks] = useState("0");
  const [edited, setEdited] = useState(false);
  const result = calculateDay(intervals, readNumber(breaks));
  const value = result.ok ? result.value : null;
  const update = (id: number, field: "start" | "end", text: string) => {
    setEdited(true);
    setIntervals((rows) => rows.map((row) => row.id === id ? { ...row, [field]: text, nextDay: undefined } : row));
  };
  const fill = (times: number[][], minutes = 0) => {
    setIntervals(times.map(([start, end]) => ({
      id: nextId.current++, start: timeText(start!), end: timeText(end!),
      nextDay: Math.floor(end! / 86400) > Math.floor(start! / 86400) || end! < start!,
    })));
    setBreaks(String(minutes));
    setEdited(true);
  };
  const dailyText = value ? `${serializeDayIntervals(value)}\nЭффективность: ${value.dailyEfficiency}%` : "";
  const creditedSeconds = value ? Math.round(value.creditedMinutes * 60) : 0;

  return <div className="grid gap-5 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
    <div className="min-w-0 space-y-5">
      <div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-[15px] font-semibold">Когда работали</h3>
          <Button size="sm" variant="ghost" onClick={() => fill([[37200, 64800], [71400, 85200]], 60)}>Пример</Button>
        </div>
        <p className="mt-1 text-[13px] text-ink-2">Добавьте каждый отрезок фактического времени.</p>
        {day?.fact?.intervals.length || day?.plan?.kind === "work" ? <div className="mt-2 flex flex-wrap gap-2">
          {day?.fact?.intervals.length ? <Button size="sm" onClick={() => fill(day.fact!.intervals)}>Интервалы из дейлика</Button> : null}
          {day?.plan?.kind === "work" && day.plan.intervals.length ? <Button size="sm" onClick={() => fill(day.plan!.intervals)}>Интервалы из расписания</Button> : null}
        </div> : null}
        {day?.fact?.intervals.length || day?.plan?.kind === "work" ? <p className="mt-2 text-[11px] text-ink-3">Интервалы на сегодня. Перерывы указываются отдельно.</p> : null}
      </div>

      <div className="space-y-3">
        {intervals.map((row, index) => <fieldset key={row.id} className="min-w-0 rounded-lg border border-line bg-surface-2/50 p-3">
          <legend className="px-1 text-[11px] font-medium uppercase tracking-wide text-ink-3">Интервал {index + 1}</legend>
          <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] items-end gap-2">
            <Field label="Начало"><Input type="time" aria-label={`Начало интервала ${index + 1}`} value={row.start}
              onChange={(event) => update(row.id, "start", event.target.value)} className="h-10 min-w-0 px-1.5 text-sm" /></Field>
            <Field label="Конец"><Input type="time" aria-label={`Конец интервала ${index + 1}`} value={row.end}
              onChange={(event) => update(row.id, "end", event.target.value)} className="h-10 min-w-0 px-1.5 text-sm" /></Field>
            <Button variant="ghost" size="icon" className="mb-1" disabled={intervals.length === 1} aria-label={`Удалить интервал ${index + 1}`}
              onClick={() => setIntervals((rows) => rows.filter((item) => item.id !== row.id))}><Trash2 /></Button>
          </div>
          {row.start && row.end && (row.end < row.start || row.nextDay) ? <p className="mt-2 text-[11px] text-ink-2">Окончание на следующий день</p> : null}
        </fieldset>)}
        <Button className="w-full border-dashed" onClick={() => { setIntervals((rows) => [...rows, { id: nextId.current++, start: "", end: "" }]); setEdited(true); }} disabled={intervals.length >= 12}>
          <Plus />Добавить интервал
        </Button>
      </div>

      <div className="rounded-lg border border-line p-4">
        <div className="mb-3 flex items-center gap-2 text-[14px] font-semibold"><Coffee className="size-4 text-deviation" />Обед и другие перерывы</div>
        <Field label="Перерывы внутри интервалов, мин" hint="Промежутки между интервалами уже исключены. Здесь укажите только перерывы внутри них.">
          <Input type="number" min="0" max="1440" step="1" value={breaks} onChange={(event) => { setBreaks(event.target.value); setEdited(true); }} className="h-10" />
        </Field>
        <div className="mt-3 flex flex-wrap gap-2">
          {[0, 15, 30, 60].map((minutes) => <Button key={minutes} size="sm" variant={breaks === String(minutes) ? "primary" : "secondary"}
            onClick={() => { setBreaks(String(minutes)); setEdited(true); }}>{minutes ? `${minutes} мин` : "Без перерывов"}</Button>)}
        </div>
      </div>
      {!result.ok && edited ? <p role="alert" className="rounded-md bg-late-soft p-3 text-[13px] text-late-ink">{result.error}</p> : null}
      <Button variant="ghost" size="sm" onClick={() => { setIntervals([{ id: nextId.current++, start: "", end: "" }]); setBreaks("0"); setEdited(false); }}><RotateCcw />Очистить</Button>
    </div>

    <section aria-label="Результат эффективности" className="min-w-0 self-start rounded-xl border border-line bg-surface-2/70 p-5">
      <div className="relative mx-auto mb-5 grid size-44 place-items-center">
        <svg viewBox="0 0 120 120" className="absolute inset-0 size-full -rotate-90" aria-hidden>
          <circle cx="60" cy="60" r="52" fill="none" stroke="var(--line)" strokeWidth="7" />
          {value ? <circle cx="60" cy="60" r="52" fill="none" stroke="var(--accent)" strokeWidth="7" pathLength="100"
            strokeDasharray={`${value.efficiencyPercent} 100`} strokeLinecap={value.efficiencyPercent ? "round" : "butt"} /> : null}
        </svg>
        <div className="text-center"><strong data-testid="daily-efficiency" className="font-display text-[42px] font-semibold leading-none tnum">{value ? `${value.dailyEfficiency}%` : "—"}</strong>
          <p className="mt-2 text-[12px] text-ink-2">для дейлика</p></div>
      </div>
      {value ? <>
        <dl className="mb-5 grid grid-cols-2 gap-4"><Metric label="В интервалах">{hm(value.factMinutes * 60)}</Metric><Metric label="Эффективно" accent>{hm(value.effectiveMinutes * 60)}</Metric></dl>
        <Breakdown items={[
          { label: "Работа", value: hm(value.effectiveMinutes * 60), amount: value.effectiveMinutes, color: "var(--accent)" },
          { label: "Перерывы", value: hm(value.breakMinutes * 60), amount: value.breakMinutes, color: "var(--deviation)" },
        ]} />
        <div className="mt-5 border-t border-line pt-3 text-[12px] leading-relaxed text-ink-2">
          <p>По времени: <b className="text-ink">{value.efficiencyPercent.toLocaleString("ru-RU", { maximumFractionDigits: 2 })}%</b>. В дейлике используется целый процент.</p>
          <p className="mt-1">С {value.dailyEfficiency}% таблица учтёт <b className="text-ink tnum">{hm(creditedSeconds)}:{String(creditedSeconds % 60).padStart(2, "0")}</b>.</p>
        </div>
        <pre className="mt-4 whitespace-pre-wrap break-words rounded-md border border-line bg-surface p-3 font-mono text-[12px] leading-relaxed" aria-label="Текст для дейлика">{dailyText}</pre>
        <Button variant="primary" size="lg" className="mt-3 w-full" onClick={async () => {
          try { await copyText(dailyText); toast.success("Интервалы и эффективность скопированы"); }
          catch { toast.error("Не удалось скопировать. Выделите текст для дейлика и скопируйте вручную."); }
        }}><Copy />Скопировать для дейлика</Button>
        <Button variant="ghost" className="mt-2 h-auto w-full whitespace-normal py-2" onClick={() => onMonth(value.dailyEfficiency)}>К доходу с этой эффективностью<ArrowRight /></Button>
      </> : <p className="text-center text-[13px] leading-relaxed text-ink-2">Укажите интервалы и перерывы — здесь появятся часы и процент для дейлика.</p>}
    </section>
  </div>;
}
