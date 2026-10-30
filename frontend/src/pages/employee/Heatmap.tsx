import type { DayCell, EmployeeDetail } from "@/api/types";
import { STATUS } from "@/components/domain/states";
import { Panel } from "@/components/ui/panel";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { MONTHS, WEEKDAYS_SHORT, dayMonth, hm, parseDate, rangeShort, weekday } from "@/lib/format";

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

/** Календарь часов по месяцам выбранного периода. */
export function MonthHeatmap({ data, today }: { data: EmployeeDetail; today: string }) {
  const months = new Map<string, DayCell[]>();
  for (const cell of data.days) {
    const key = cell.date.slice(0, 7);
    const group = months.get(key) ?? [];
    group.push(cell);
    months.set(key, group);
  }
  const groups = [...months.entries()];
  if (!groups.length) return null;
  const first = parseDate(groups[0]![0] + "-01");
  return (
    <Panel
      title={groups.length === 1 ? MONTHS[first.getMonth()] + ": часы по дням" : "Часы по дням за период"}
      description={rangeShort(data.start, data.end) + " · насыщенность цвета показывает отработанные часы"}
      className="flex h-[28rem] flex-col overflow-hidden"
      bodyClassName="flex min-h-0 flex-1 flex-col"
    >
      <div
        key={`${data.start}-${data.end}`}
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1 [scrollbar-gutter:stable]"
        aria-label="Календарь выбранного периода"
        role="region"
        tabIndex={0}
      >
        <div className="grid content-start gap-5">
          {groups.map(([key, cells]) => (
            <CalendarMonth key={key} month={key} cells={cells} today={today} showTitle={groups.length > 1} />
          ))}
        </div>
      </div>
      <div className="mt-3 flex shrink-0 flex-wrap items-center gap-1.5 text-[11px] text-ink-3">
        <span>0 ч</span>
        {FILL.slice(1).map((fill, index) => (
          <span
            key={index}
            className="size-3 rounded-[3px]"
            style={{ background: "color-mix(in oklab, var(--accent) " + fill + ", var(--surface-2))" }}
          />
        ))}
        <span>10+ ч</span>
        <span className="ml-3 size-3 rounded-[3px] border border-dashed border-ink-3" /> нет дейлика{" "}
        <span className="hatch-absence ml-2 size-3 rounded-[3px]" /> отсутствие
      </div>
    </Panel>
  );
}

function CalendarMonth({
  month,
  cells,
  today,
  showTitle,
}: {
  month: string;
  cells: DayCell[];
  today: string;
  showTitle: boolean;
}) {
  const first = parseDate(month + "-01");
  const length = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
  const byDate = new Map(cells.map((cell) => [cell.date, cell]));
  const label = MONTHS[first.getMonth()] + " " + first.getFullYear();
  return (
    <section aria-label={label}>
      {showTitle ? <h3 className="mb-2 text-[13px] font-medium">{label}</h3> : null}
      <div className="grid grid-cols-7 gap-1" role="grid" aria-label={label + ": календарь часов"}>
        {WEEKDAYS_SHORT.map((day) => (
          <div key={day} className="pb-1 text-center text-[11px] text-ink-3">
            {day}
          </div>
        ))}
        {Array.from({ length: weekday(month + "-01") }, (_, index) => (
          <div key={"empty" + index} />
        ))}
        {Array.from({ length }, (_, index) => {
          const date = month + "-" + String(index + 1).padStart(2, "0");
          const cell = byDate.get(date);
          if (!cell)
            return (
              <div
                key={date}
                role="gridcell"
                aria-disabled="true"
                aria-label={dayMonth(date) + ": вне выбранного периода"}
                className="h-10 rounded p-1 text-[11px] text-ink-3/40"
              >
                {index + 1}
              </div>
            );
          return (
            <Tooltip key={date} content={title(cell)}>
              <div
                role="gridcell"
                data-date={date}
                aria-label={title(cell)}
                className={cn(
                  "relative flex h-10 items-start rounded-[4px] p-1 text-[11px] tnum",
                  cell.fact ? "text-ink" : "bg-surface-2 text-ink-3",
                  !cell.fact && cell.status && cell.status !== "remote" && "hatch-absence",
                  cell.state === "missing" && "border border-dashed border-ink-3 bg-transparent",
                  date > today && "opacity-50",
                )}
                style={
                  cell.fact
                    ? {
                        background:
                          "color-mix(in oklab, var(--accent) " +
                          (FILL[level(cell.fact.worked_sec)] || "8%") +
                          ", var(--surface-2))",
                      }
                    : undefined
                }
              >
                <span className={cn(level(cell.fact?.worked_sec ?? 0) >= 4 && "text-on-accent")}>
                  {index + 1}
                </span>
              </div>
            </Tooltip>
          );
        })}
      </div>
    </section>
  );
}
