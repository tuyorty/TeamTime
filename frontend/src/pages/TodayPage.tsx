import { CheckCircle2, CircleAlert, Clock3, MessageSquareText, PencilLine } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";

import { useToday } from "@/api/queries";
import type { FeedItem, Today, TodayRow } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { DayDetailSheet, type DayRef } from "@/components/domain/DayDetail";
import { AxisTicks, DayStrip } from "@/components/domain/DayStrip";
import { axisFor } from "@/lib/axis";
import { EmptyState, ErrorState } from "@/components/domain/feedback";
import { STATUS } from "@/components/domain/states";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { WEEKDAYS_LONG, WEEKDAYS_SHORT, clock, count, dayMonth, hm, relative, weekday } from "@/lib/format";
import { useFlashed } from "@/lib/realtime";

const PRESENCE: Record<TodayRow["presence"], { label: string; order: number }> = {
  on_site: { label: "на месте по плану", order: 0 },
  remote: { label: "на удалёнке", order: 1 },
  expected_later: { label: "придёт позже", order: 2 },
  left: { label: "план закончился", order: 3 },
  no_plan: { label: "без плана", order: 4 },
  absent: { label: "отсутствует", order: 5 },
};

function presenceText(r: TodayRow): string {
  const c = r.cell;
  if (r.presence === "absent" && c.status) return STATUS[c.status].label;
  if (r.presence === "expected_later" && c.plan) return `с ${clock(c.plan.start)}`;
  if (r.presence === "on_site" && c.plan) return `до ${clock(c.plan.end)}`;
  if (r.presence === "no_plan" && c.plan?.kind === "note") return `«${c.plan.note}»`;
  return PRESENCE[r.presence].label;
}

export default function TodayPage() {
  const { data, error, refetch } = useToday();
  const [selected, setSelected] = useState<DayRef | null>(null);

  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!data) return <TodaySkeleton />;

  const wd = weekday(data.date);
  const dateLabel = `${WEEKDAYS_LONG[wd]}, ${dayMonth(data.date)}`;
  return (
    <div className="grid gap-5">
      <PageHeader
        title="Сегодня"
        subtitle={
          <>
            {dateLabel[0]!.toUpperCase() + dateLabel.slice(1)}, сейчас <span className="tnum">{clock(data.now_sec)}</span>.
            Факт появляется, когда приходит дейлик.
          </>
        }
      />
      <KeyNumbers data={data} />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <TeamDay data={data} onOpen={setSelected} />
        <div className="grid content-start gap-5">
          <AwaitingDaily data={data} />
          <Feed items={data.feed} />
        </div>
      </div>
      <DayDetailSheet value={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function KeyNumbers({ data }: { data: Today }) {
  const c = data.counts;
  const planned = c.planned ?? 0;
  const items = [
    { label: "по плану сейчас на месте", value: c.on_site ?? 0, strong: true },
    { label: "придут позже", value: c.expected_later ?? 0 },
    { label: "на удалёнке", value: c.remote ?? 0 },
    { label: "отсутствуют", value: c.absent ?? 0, tone: (c.absent ?? 0) > 0 ? "text-absence-ink" : "" },
    { label: `дейликов из ${planned}`, value: c.dailies ?? 0 },
    { label: "опоздали по дейликам", value: c.late ?? 0, tone: (c.late ?? 0) > 0 ? "text-late-ink" : "" },
  ];
  return (
    <section aria-label="Ключевые числа дня" className="flex flex-wrap gap-y-3 rounded-lg border border-line bg-surface px-1 py-3">
      {items.map((it) => (
        <div key={it.label} className="flex min-w-[9.5rem] flex-1 flex-col gap-0.5 border-line px-4 [&:not(:first-child)]:border-l">
          <span className={cn("font-display tnum leading-none", it.strong ? "text-[34px] font-semibold" : "text-[26px] font-medium", it.tone)}>
            {it.value}
          </span>
          <span className="text-[12px] text-ink-2">{it.label}</span>
        </div>
      ))}
    </section>
  );
}

function TeamRow({ row, axis, now, onOpen }: { row: TodayRow; axis: ReturnType<typeof axisFor>; now: number; onOpen: () => void }) {
  const flashed = useFlashed(row.employee.id, row.cell.date);
  const c = row.cell;
  return (
    <li className={cn(flashed && "flash")}>
      <button type="button" onClick={onOpen} className="grid w-full grid-cols-[minmax(9rem,12rem)_1fr] items-center gap-x-4 gap-y-1 px-4 py-2.5 text-left hover:bg-surface-2/60 max-sm:grid-cols-1">
        <span className="flex min-w-0 items-center gap-2">
          <Avatar employee={row.employee} size={26} />
          <span className="min-w-0">
            <span className="block truncate text-[13px] font-medium">{row.employee.short_name}</span>
            <span className={cn("block truncate text-[12px]", row.presence === "absent" ? "text-absence-ink" : "text-ink-3")}>
              {presenceText(row)}
            </span>
          </span>
        </span>
        <span className="grid gap-1">
          <DayStrip cell={c} axis={axis} now={now} height={18} />
          {c.fact ? (
            <span className="flex gap-2 text-[12px] text-ink-2 tnum">
              <CheckCircle2 className="size-3.5 text-accent" /> дейлик: {hm(c.fact.worked_sec)}
              {c.fact.efficiency !== null && c.fact.efficiency !== undefined ? `, ${c.fact.efficiency}%` : ""}
              {c.late_sec ? <span className="font-medium text-late-ink">опоздание {hm(c.late_sec)}</span> : null}
            </span>
          ) : null}
        </span>
      </button>
    </li>
  );
}

function TeamDay({ data, onOpen }: { data: Today; onOpen: (r: DayRef) => void }) {
  const rows = useMemo(
    () =>
      [...data.rows].sort(
        (a, b) =>
          PRESENCE[a.presence].order - PRESENCE[b.presence].order ||
          (a.cell.plan?.start ?? 86400) - (b.cell.plan?.start ?? 86400) ||
          a.employee.short_name.localeCompare(b.employee.short_name, "ru"),
      ),
    [data.rows],
  );
  const axis = axisFor(data.rows.map((r) => r.cell), { start: 8 * 3600, end: 22 * 3600 });
  if (!rows.length) {
    return (
      <Panel title="День команды">
        <EmptyState title="Сотрудников пока нет">Добавьте их в админке, и здесь появится план на день.</EmptyState>
      </Panel>
    );
  }
  return (
    <Panel
      title="День команды"
      description="Контур — план, заливка — факт из дейлика, вертикальная черта — сейчас"
      bodyClassName="px-0 pb-1"
    >
      <div className="grid grid-cols-[minmax(9rem,12rem)_1fr] gap-x-4 px-4 pb-1 max-sm:hidden">
        <span />
        <AxisTicks axis={axis} />
      </div>
      <ul className="divide-y divide-line border-t border-line">
        {rows.map((r) => (
          <TeamRow key={r.employee.id} row={r} axis={axis} now={data.now_sec} onOpen={() => onOpen({ employee: r.employee, cell: r.cell })} />
        ))}
      </ul>
      <WeekStrip data={data} />
    </Panel>
  );
}

/** Неделя одной строкой: сколько часов набрано по дням и сколько дейликов пришло. */
function WeekStrip({ data }: { data: Today }) {
  const max = Math.max(1, ...data.week_pulse.map((d) => d.worked_sec));
  return (
    <div className="mt-1 border-t border-line px-4 pt-3 pb-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-[13px] font-semibold">Эта неделя</h3>
        <Link to="/week" className="text-[12px] text-accent-ink hover:underline">
          Открыть табель
        </Link>
      </div>
      <div className="grid grid-cols-7 gap-2">
        {data.week_pulse.map((d, i) => (
          <div key={d.date} className="grid gap-1 text-center">
            <div className="flex h-12 items-end justify-center rounded-sm bg-surface-2/70" aria-hidden>
              <div className="w-3/5 rounded-t-[3px] bg-accent" style={{ height: `${(d.worked_sec / max) * 100}%` }} />
            </div>
            <span className={cn("text-[11px] text-ink-3", d.date === data.date && "font-semibold text-ink")}>
              {WEEKDAYS_SHORT[i]}
            </span>
            <span className="text-[11px] text-ink-2 tnum">{d.worked_sec ? hm(d.worked_sec) : "—"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AwaitingDaily({ data }: { data: Today }) {
  const waiting = data.rows.filter((r) => r.cell.plan?.kind === "work" && !r.cell.fact && r.presence !== "absent");
  const overdue = waiting.filter((r) => r.daily_overdue);
  return (
    <Panel
      title="Ждём дейлик"
      description={waiting.length ? `${count(waiting.length, ["человек", "человека", "человек"])} с планом на сегодня` : undefined}
    >
      {waiting.length ? (
        <ul className="grid gap-1.5">
          {waiting.map((r) => (
            <li key={r.employee.id} className="flex items-center gap-2 text-[13px]">
              <Avatar employee={r.employee} size={20} />
              <span className="min-w-0 truncate">{r.employee.short_name}</span>
              <span className="ml-auto flex items-center gap-1 text-[12px] text-ink-3 tnum">
                {r.daily_overdue ? (
                  <Badge tone="deviation">
                    <Clock3 /> план закончился в {clock(r.cell.plan?.end)}
                  </Badge>
                ) : (
                  <>до {clock(r.cell.plan?.end)}</>
                )}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[13px] text-ink-2">Все, у кого был план, уже прислали дейлик.</p>
      )}
      {overdue.length ? (
        <p className="mt-3 text-[12px] text-ink-3">
          Напоминания можно включить в настройках бота.
        </p>
      ) : null}
    </Panel>
  );
}

function FeedRow({ item }: { item: FeedItem }) {
  const problem = item.status !== "ok";
  return (
    <li className="flex gap-2.5 py-2">
      <span className="mt-0.5">
        {item.employee ? (
          <Avatar employee={item.employee} size={22} />
        ) : (
          <span className="flex size-[22px] items-center justify-center rounded-full bg-surface-2 text-ink-3">
            <MessageSquareText className="size-3.5" />
          </span>
        )}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] leading-snug">
          <span className="font-medium">{item.employee?.short_name ?? item.author_name}</span>{" "}
          <span className="text-ink-2">{item.summary}</span>
        </p>
        <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[12px] text-ink-3">
          {relative(item.at)}
          {item.edited ? (
            <span className="inline-flex items-center gap-0.5">
              <PencilLine className="size-3" /> правка
            </span>
          ) : null}
          {problem && item.resolution === "pending" ? (
            <Link to="/inbox" className="inline-flex items-center gap-0.5 text-deviation-ink hover:underline">
              <CircleAlert className="size-3" /> в инбоксе
            </Link>
          ) : null}
        </p>
      </div>
    </li>
  );
}

function Feed({ items }: { items: FeedItem[] }) {
  return (
    <Panel title="Последние сообщения" description="Обновляется сама, без перезагрузки">
      {items.length ? (
        <ul className="-my-2 divide-y divide-line">
          {items.slice(0, 8).map((it) => (
            <FeedRow key={it.id} item={it} />
          ))}
        </ul>
      ) : (
        <p className="text-[13px] text-ink-2">
          Сообщений ещё не было. Привяжите темы командой <code className="rounded bg-surface-2 px-1">/bind</code> в чате.
        </p>
      )}
    </Panel>
  );
}

function TodaySkeleton() {
  return (
    <div className="grid gap-5" aria-busy>
      <Skeleton className="h-9 w-48" />
      <Skeleton className="h-20 w-full" />
      <div className="grid gap-5 xl:grid-cols-[1fr_22rem]">
        <Skeleton className="h-96" />
        <Skeleton className="h-96" />
      </div>
    </div>
  );
}
