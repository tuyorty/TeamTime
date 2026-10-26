import type { DayCell, EmployeeDetail } from "@/api/types";
import { STATUS } from "@/components/domain/states";
import { Panel } from "@/components/ui/panel";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { MONTHS, WEEKDAYS_SHORT, dayMonth, hm, parseDate, weekday } from "@/lib/format";

const STEPS = [0, 2, 4, 6, 8, 10];

function level(seconds: number): number {
  const h = seconds / 3600;
  let l = 0;
  for (let i = 0; i < STEPS.length; i++) if (h > STEPS[i]!) l = i + 1;
  return Math.min(l, 5);
}

/** Последовательная шкала одного оттенка (accent), от фона к насыщенному. */
const FILL = ["", "18%", "34%", "52%", "72%", "100%"];

function title(c: DayCell): string {
  if (c.fact) return `${dayMonth(c.date)}: ${hm(c.fact.worked_sec)}`;
  if (c.status) return `${dayMonth(c.date)}: ${STATUS[c.status].label.toLowerCase()}`;
  if (c.state === "missing") return `${dayMonth(c.date)}: нет дейлика`;
  return `${dayMonth(c.date)}: —`;
}

/** Календарь-хитмап месяца: цвет — отработанные часы, легенда в часах. */
export function MonthHeatmap({ data, today }: { data: EmployeeDetail; today: string }) {
  const t = parseDate(today);
  const cells = data.days.filter((d) => {
    const x = parseDate(d.date);
    return x.getFullYear() === t.getFullYear() && x.getMonth() === t.getMonth();
  });
  if (!cells.length) return null;
  const lead = weekday(cells[0]!.date);
  const grid: (DayCell | null)[] = [...Array.from({ length: lead }, () => null), ...cells];

  return (
    <Panel title={`${MONTHS[t.getMonth()]}: часы по дням`} description="Чем насыщеннее цвет, тем больше часов">
      <div className="grid grid-cols-7 gap-1" role="grid" aria-label="Календарь месяца">
        {WEEKDAYS_SHORT.map((d) => (
          <div key={d} className="pb-1 text-center text-[11px] text-ink-3">
            {d}
          </div>
        ))}
        {grid.map((c, i) =>
          c ? (
            <Tooltip key={c.date} content={title(c)}>
              <div
                role="gridcell"
                aria-label={title(c)}
                className={cn(
                  "relative flex h-11 items-start justify-start rounded-[4px] p-1 text-[11px] tnum",
                  c.fact ? "text-ink" : "bg-surface-2 text-ink-3",
                  !c.fact && c.status && c.status !== "remote" && "hatch-absence",
                  c.state === "missing" && "border border-dashed border-ink-3 bg-transparent",
                  c.date > today && "opacity-50",
                )}
                style={c.fact ? { background: `color-mix(in oklab, var(--accent) ${FILL[level(c.fact.worked_sec)] || "8%"}, var(--surface-2))` } : undefined}
              >
                <span className={cn(level(c.fact?.worked_sec ?? 0) >= 4 && "text-on-accent")}>{parseDate(c.date).getDate()}</span>
              </div>
            </Tooltip>
          ) : (
            <div key={`e${i}`} />
          ),
        )}
      </div>
      <div className="mt-3 flex items-center gap-1.5 text-[11px] text-ink-3">
        <span>0 ч</span>
        {FILL.slice(1).map((f, i) => (
          <span key={i} className="size-3 rounded-[3px]" style={{ background: `color-mix(in oklab, var(--accent) ${f}, var(--surface-2))` }} />
        ))}
        <span>10+ ч</span>
        <span className="ml-3 inline-block size-3 rounded-[3px] border border-dashed border-ink-3" /> нет дейлика
        <span className="hatch-absence ml-2 inline-block size-3 rounded-[3px]" /> отсутствие
      </div>
    </Panel>
  );
}
