import { ChevronDown, ChevronLeft, ChevronRight, ClipboardList, GitCompareArrows } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router";

import { useMeta, usePlans } from "@/api/queries";
import type { PlanDay, PlanRow, PlanVersion } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { EmptyState, ErrorState } from "@/components/domain/feedback";
import { SourceMessage } from "@/components/domain/SourceMessage";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { WEEKDAYS_SHORT, dateTime, dayMonthShort, hm, isoWeek, parseDate, rangeShort, shiftWeek } from "@/lib/format";

function dayText(p: PlanDay | undefined): string {
  if (!p) return "—";
  if (p.kind === "off") return "выходной";
  if (p.kind === "note") return `«${p.note ?? ""}»`;
  return p.intervals.map(([a, b]) => `${hm(a)}–${hm(b)}`).join("; ");
}

function byDate(v: PlanVersion): Map<string, PlanDay> {
  return new Map(v.days.map(([d, p]) => [d, p]));
}

const SOURCE = { telegram: "из сообщения", import: "из импорта", demo: "из сообщения", manual: "правка вручную" } as const;

export default function PlansPage() {
  const params = useParams();
  const navigate = useNavigate();
  const today = useMeta().data?.today;
  const fallback = isoWeek(today ? parseDate(today) : new Date());
  const year = Number(params.year ?? fallback.year);
  const week = Number(params.week ?? fallback.week);
  const { data, error, refetch } = usePlans(year, week);
  const [diff, setDiff] = useState<PlanRow | null>(null);

  const go = (delta: number) => {
    const t = shiftWeek(year, week, delta);
    navigate(`/plans/${t.year}/${t.week}`);
  };

  return (
    <div className="grid gap-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-[28px] font-semibold tracking-tight">Планы: {week} неделя</h1>
          <p className="mt-1 text-[13px] text-ink-2">
            {data ? rangeShort(data.days[0]!, data.days[6]!) : " "}. Расписания из темы, их версии и задачи спринта.
          </p>
        </div>
        <div className="flex items-center">
          <Button variant="ghost" size="icon" aria-label="Предыдущая неделя" onClick={() => go(-1)}>
            <ChevronLeft />
          </Button>
          <Button size="sm" onClick={() => navigate("/plans")}>
            Текущая
          </Button>
          <Button variant="ghost" size="icon" aria-label="Следующая неделя" onClick={() => go(1)}>
            <ChevronRight />
          </Button>
        </div>
      </header>

      {error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : !data ? (
        <Skeleton className="h-96" />
      ) : !data.rows.some((r) => r.current) ? (
        <EmptyState icon={ClipboardList} title="Расписаний на эту неделю нет">
          Они появятся, когда сотрудники пришлют «Спринт ДД.ММ - ДД.ММ» в тему с расписанием.
        </EmptyState>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full min-w-[1080px] table-fixed border-collapse text-[13px]">
            <colgroup>
              <col className="w-[13rem]" />
              {data.days.map((d) => (
                <col key={d} />
              ))}
              <col className="w-[16rem]" />
            </colgroup>
            <thead className="border-b border-line bg-surface-2/60 text-left text-[12px] text-ink-3">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">Сотрудник</th>
                {data.days.map((d, i) => (
                  <th key={d} scope="col" className="border-l border-line px-2.5 py-2 font-medium">
                    {WEEKDAYS_SHORT[i]} <span className="font-normal tnum">{dayMonthShort(d)}</span>
                  </th>
                ))}
                <th scope="col" className="border-l border-line px-3 py-2 font-medium">Задачи спринта</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => {
                const days = r.current ? byDate(r.current) : new Map<string, PlanDay>();
                return (
                  <tr key={r.employee.id} className="border-b border-line align-top last:border-b-0">
                    <th scope="row" className="px-3 py-2.5 text-left font-normal">
                      <div className="flex items-center gap-2">
                        <Avatar employee={r.employee} size={24} />
                        <span className="truncate font-medium">{r.employee.short_name}</span>
                      </div>
                      {r.current ? (
                        <div className="mt-1.5 flex flex-wrap items-center gap-1.5 pl-8 text-[12px] text-ink-3">
                          <span>
                            версия {r.current.version}, {SOURCE[r.current.source]}
                          </span>
                          {r.versions.length > 1 ? (
                            <Button size="sm" variant="link" className="h-auto text-[12px]" onClick={() => setDiff(r)}>
                              <GitCompareArrows className="!size-3.5" /> что менялось
                            </Button>
                          ) : null}
                        </div>
                      ) : (
                        <div className="mt-1 pl-8 text-[12px] text-ink-3">расписания нет</div>
                      )}
                    </th>
                    {data.days.map((d) => {
                      const p = days.get(d);
                      return (
                        <td
                          key={d}
                          className={cn(
                            "border-l border-line px-2.5 py-2.5 tnum",
                            !p && "text-ink-3",
                            p?.kind === "off" && "hatch text-ink-2",
                            p?.kind === "note" && "italic text-ink-2",
                            p?.note_has_time && "text-deviation-ink",
                          )}
                        >
                          {dayText(p)}
                        </td>
                      );
                    })}
                    <td className="border-l border-line px-3 py-2.5">
                      {r.current?.tasks.length ? <TaskList tasks={r.current.tasks} /> : <span className="text-ink-3">—</span>}
                      {r.current ? (
                        <p className="mt-2 text-[12px] text-ink-3">
                          Дней с планом: {r.days_planned}, с дейликом: {r.days_with_daily}
                          {r.done_tasks.length ? `, сделано пунктов: ${r.done_tasks.length}` : ""}
                        </p>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <Sheet open={!!diff} onOpenChange={(o) => !o && setDiff(null)}>
        {diff ? (
          <SheetContent title={`${diff.employee.short_name}: версии плана`} subtitle={`${week} неделя`}>
            <VersionsDiff row={diff} days={data?.days ?? []} />
          </SheetContent>
        ) : null}
      </Sheet>
    </div>
  );
}

/** Различия версий: какие дни поменялись между соседними версиями. */
const COLLAPSED_TASKS = 3;
/** Длиннее — в свёрнутом виде обрезается многоточием. */
const LONG_TASK = 70;

/** Задачи спринта: свёрнуто — первые пункты в одну строку, чтобы строки табеля не разъезжались. */
function TaskList({ tasks }: { tasks: string[] }) {
  const [open, setOpen] = useState(false);
  const collapsible = tasks.length > COLLAPSED_TASKS || tasks.some((t) => t.length > LONG_TASK);
  const shown = open || !collapsible ? tasks : tasks.slice(0, COLLAPSED_TASKS);
  const hidden = tasks.length - shown.length;
  return (
    <div className="grid justify-items-start gap-1">
      <ul className="grid w-full gap-0.5">
        {shown.map((t, i) => (
          <li key={i} className="flex min-w-0 gap-1.5" title={open ? undefined : t}>
            <span className="mt-[7px] size-1.5 shrink-0 rounded-full border border-ink-3" />
            <span className={cn("min-w-0", !open && collapsible && "truncate")}>{t}</span>
          </li>
        ))}
      </ul>
      {collapsible ? (
        <Button
          size="sm"
          variant="link"
          className="h-auto text-[12px]"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <ChevronDown className={cn("!size-3.5 transition-transform motion-reduce:transition-none", open && "rotate-180")} />
          {open ? "Свернуть" : hidden > 0 ? `Ещё ${hidden} · развернуть` : "Развернуть"}
        </Button>
      ) : null}
    </div>
  );
}

function VersionsDiff({ row, days }: { row: PlanRow; days: string[] }) {
  const versions = [...row.versions].reverse();
  return (
    <ol className="grid gap-5">
      {versions.map((v, idx) => {
        const prev = versions[idx + 1];
        const cur = byDate(v);
        const old = prev ? byDate(prev) : null;
        const changed = days.filter((d) => old && dayText(cur.get(d)) !== dayText(old.get(d)));
        return (
          <li key={v.id} className="grid gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-display text-[15px] font-semibold">Версия {v.version}</span>
              {v.retracted ? <Badge>отозвана</Badge> : idx === 0 ? <Badge tone="accent">актуальная</Badge> : null}
              {v.edited ? <Badge tone="outline">из правки сообщения</Badge> : null}
              <span className="text-[12px] text-ink-3">
                {dateTime(v.created_at)}, {SOURCE[v.source]}
              </span>
            </div>
            {old ? (
              changed.length ? (
                <table className="w-full text-[13px] tnum">
                  <tbody>
                    {changed.map((d) => (
                      <tr key={d} className="border-b border-line last:border-b-0">
                        <th scope="row" className="w-16 py-1 text-left font-normal text-ink-3">
                          {WEEKDAYS_SHORT[days.indexOf(d)]} {dayMonthShort(d)}
                        </th>
                        <td className="py-1 text-ink-3 line-through">{dayText(old.get(d))}</td>
                        <td className="py-1 font-medium">{dayText(cur.get(d))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="text-[13px] text-ink-2">Дни не менялись, поменялись задачи или текст.</p>
              )
            ) : (
              <p className="text-[13px] text-ink-2">Первая версия.</p>
            )}
            {v.raw_message_id ? <SourceMessage rawId={v.raw_message_id} title="Сообщение" /> : null}
          </li>
        );
      })}
    </ol>
  );
}
