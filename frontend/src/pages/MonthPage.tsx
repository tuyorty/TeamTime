import { ChevronLeft, ChevronRight, Download, Printer } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router";

import { exportUrl } from "@/api/client";
import { useMeta, useMonth } from "@/api/queries";
import { ErrorState, TruncationNote } from "@/components/domain/feedback";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dropdown, DropdownContent, DropdownItem, DropdownTrigger } from "@/components/ui/dropdown";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/cn";
import { MONTHS, parseDate, shiftMonth } from "@/lib/format";

import { BonusTab } from "./month/BonusTab";
import { MonthFilters } from "./month/filters";
import { useMonthFilter } from "./month/useMonthFilter";
import { LatenessTab } from "./month/LatenessTab";
import { MonthCharts } from "./month/MonthCharts";
import { SummaryTab } from "./month/SummaryTab";

const TABS = [
  { value: "summary", label: "Итог за месяц" },
  { value: "late", label: "Опоздания" },
  { value: "bonus", label: "Премии" },
] as const;

export default function MonthPage() {
  const params = useParams();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const today = useMeta().data?.today;
  const now = today ? parseDate(today) : new Date();
  const year = Number(params.year ?? now.getFullYear());
  const month = Number(params.month ?? now.getMonth() + 1);
  const { data, error, refetch, isPlaceholderData } = useMonth(year, month);
  const filter = useMonthFilter(data?.rows ?? []);
  const tab = search.get("tab") ?? "summary";

  const go = (delta: number) => {
    const t = shiftMonth(year, month, delta);
    navigate(`/month/${t.year}/${t.month}?tab=${tab}`);
  };

  return (
    <div className="grid gap-5">
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="flex items-baseline gap-3">
          <h1 className="font-display text-[34px] font-semibold leading-none tracking-tight">
            {MONTHS[month - 1]} <span className="text-ink-3 tnum">{year}</span>
          </h1>
          {data && !data.complete ? <Badge tone="deviation">месяц не закончился, итоги промежуточные</Badge> : null}
        </div>
        <div className="no-print flex flex-wrap items-center gap-2">
          <div className="flex items-center">
            <Button variant="ghost" size="icon" aria-label="Предыдущий месяц" onClick={() => go(-1)}>
              <ChevronLeft />
            </Button>
            <Button size="sm" onClick={() => navigate(`/month?tab=${tab}`)}>
              Текущий
            </Button>
            <Button variant="ghost" size="icon" aria-label="Следующий месяц" onClick={() => go(1)}>
              <ChevronRight />
            </Button>
          </div>
          <Button size="sm" onClick={() => window.print()}>
            <Printer /> Печать
          </Button>
          <Dropdown>
            <DropdownTrigger asChild>
              <Button size="sm">
                <Download /> Экспорт
              </Button>
            </DropdownTrigger>
            <DropdownContent>
              <DropdownItem asChild>
                <a href={exportUrl(`/months/${year}/${month}.xlsx`)} download>
                  Excel: итог, опоздания, дни
                </a>
              </DropdownItem>
              <DropdownItem asChild>
                <a href={exportUrl(`/months/${year}/${month}.csv`)} download>
                  CSV: итог за месяц
                </a>
              </DropdownItem>
            </DropdownContent>
          </Dropdown>
        </div>
      </header>

      {error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : !data ? (
        <div className="grid gap-4">
          <Skeleton className="h-9 w-80" />
          <Skeleton className="h-80" />
        </div>
      ) : (
        <div className={cn("grid gap-5 transition-opacity", isPlaceholderData && "opacity-60")}>
          <Tabs value={tab} onValueChange={(v) => setSearch({ tab: v }, { replace: true })}>
            <TabsList className="no-print">
              {TABS.map((t) => (
                <TabsTrigger key={t.value} value={t.value}>
                  {t.label}
                </TabsTrigger>
              ))}
            </TabsList>
            <div className="pt-4">
              <MonthFilters state={filter} total={data.rows.length} />
            </div>
            <TabsContent value="summary" className="pt-3">
              <SummaryTab data={data} rows={filter.visible} />
            </TabsContent>
            <TabsContent value="late" className="pt-3">
              <LatenessTab data={data} rows={filter.visible} />
            </TabsContent>
            <TabsContent value="bonus" className="pt-3">
              <BonusTab data={data} rows={filter.visible} />
            </TabsContent>
          </Tabs>
          <TruncationNote />
          <MonthCharts data={data} />
        </div>
      )}
    </div>
  );
}
