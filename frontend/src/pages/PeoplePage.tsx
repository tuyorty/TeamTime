import { Users } from "lucide-react";
import { Link } from "react-router";

import { useMeta, useMonth, useWeek } from "@/api/queries";
import { Avatar } from "@/components/domain/Avatar";
import { EmptyState, ErrorState } from "@/components/domain/feedback";
import { PageHeader } from "@/components/layout/PageHeader";
import { Panel } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { MONTHS, hm, isoWeek, parseDate, percent } from "@/lib/format";

import { NormBar } from "./month/shared";

/** Команда: по фамилии, без рейтингов. Каждая строка ведёт в карточку сотрудника. */
export default function PeoplePage() {
  const today = useMeta().data?.today;
  const d = today ? parseDate(today) : new Date();
  const w = isoWeek(d);
  const month = useMonth(d.getFullYear(), d.getMonth() + 1);
  const week = useWeek(w.year, w.week);

  if (month.error) return <ErrorState error={month.error} onRetry={() => month.refetch()} />;
  const rows = month.data?.rows ?? [];
  const weekById = new Map(week.data?.rows.map((r) => [r.employee.id, r]) ?? []);
  const max = Math.max(1, ...rows.map((r) => Math.max(r.summary.total_sec, r.summary.norm_sec))) * 1.05;

  return (
    <div className="grid gap-5">
      <PageHeader
        title="Люди"
        subtitle={`Команда по фамилии. Итоги за ${MONTHS[d.getMonth()]!.toLowerCase()} и текущую неделю.`}
      />
      {!month.data ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      ) : !rows.length ? (
        <Panel>
          <EmptyState icon={Users} title="В справочнике пока никого">
            Добавьте сотрудников в админке: ФИО как в расписании, должность, норму и ставку.
          </EmptyState>
        </Panel>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {rows.map((r) => {
            const s = r.summary;
            const wr = weekById.get(r.employee.id);
            return (
              <li key={r.employee.id}>
                <Link
                  to={`/people/${r.employee.id}`}
                  className="grid h-full gap-3 rounded-lg border border-line bg-surface p-4 transition-colors hover:border-line-strong"
                >
                  <div className="flex items-center gap-3">
                    <Avatar employee={r.employee} size={36} />
                    <div className="min-w-0">
                      <div className="truncate font-display text-[15px] font-semibold">{r.employee.full_name}</div>
                      <div className="truncate text-[12px] text-ink-3">{r.employee.position}</div>
                    </div>
                  </div>
                  <div className="grid gap-1.5">
                    <div className="flex items-baseline justify-between text-[12px] text-ink-2">
                      <span>
                        Итого <span className="font-semibold text-ink tnum">{hm(s.total_sec)}</span> из {hm(s.norm_sec)}
                      </span>
                      <span className={cn("tnum", s.norm_progress >= 1 && "font-semibold text-accent-ink")}>
                        {percent(s.norm_progress)}
                      </span>
                    </div>
                    <NormBar total={s.total_sec} norm={s.norm_sec} max={max} />
                  </div>
                  <dl className="grid grid-cols-3 gap-2 text-[12px]">
                    <div>
                      <dt className="text-ink-3">эта неделя</dt>
                      <dd className="font-medium tnum">{wr ? hm(wr.totals.worked_sec) : "—"}</dd>
                    </div>
                    <div>
                      <dt className="text-ink-3">опоздания</dt>
                      <dd className={cn("font-medium tnum", s.late_count > 0 && "text-late-ink")}>
                        {s.late_count ? `${s.late_count}, ${hm(s.late_total_sec)}` : "нет"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-ink-3">без дейлика</dt>
                      <dd className="font-medium tnum">{s.days_missing || "нет"}</dd>
                    </div>
                  </dl>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
