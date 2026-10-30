import { ChevronLeft, ChevronRight, Download, Plus, Search } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";

import { exportUrl } from "@/api/client";
import { useFinance, useMeta } from "@/api/queries";
import { ErrorState } from "@/components/domain/feedback";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dropdown, DropdownContent, DropdownItem, DropdownTrigger } from "@/components/ui/dropdown";
import { Input, Select } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { MONTHS, money, shiftMonth } from "@/lib/format";

import { BonusForm } from "./finance/BonusForm";
import { FinanceDetails } from "./finance/FinanceDetails";
import { FinanceSummary } from "./finance/FinanceSummary";
import { FinanceTable } from "./finance/FinanceTable";
import NotFound from "./NotFound";

export default function FinancePage() {
  const params = useParams();
  const meta = useMeta();
  if (!meta.data?.today) return meta.error ? <ErrorState error={meta.error} onRetry={() => void meta.refetch()} /> : <Skeleton className="h-80" />;
  const current = meta.data.today.slice(0, 7);
  const year = Number(params.year ?? current.slice(0, 4));
  const month = Number(params.month ?? current.slice(5, 7));
  if (!Number.isInteger(year) || !Number.isInteger(month) || year < 2000 || year > 2100 || month < 1 || month > 12) return <NotFound />;
  return <FinancePeriod key={`${year}-${month}`} year={year} month={month} current={current} />;
}

function FinancePeriod({ year, month, current }: { year: number; month: number; current: string }) {
  const { data, error, refetch, isFetching } = useFinance(year, month);
  const navigate = useNavigate();
  const admin = useIsAdmin();
  const [search, setSearch] = useSearchParams();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [adding, setAdding] = useState(false);
  const monthValue = `${year}-${String(month).padStart(2, "0")}`;
  const label = `${MONTHS[month - 1]} ${year}`;
  const go = (delta: number) => {
    const next = shiftMonth(year, month, delta);
    navigate(`/finances/${next.year}/${next.month}`);
  };
  const rows = (data?.rows ?? []).filter((row) => {
    const e = row.employee;
    return `${e.full_name} ${e.short_name} ${e.position}`.toLocaleLowerCase("ru-RU").includes(query.trim().toLocaleLowerCase("ru-RU")) && (
      filter === "all" || (filter === "overtime" && row.summary.overtime_sec > 0) ||
      (filter === "bonuses" && Number(row.amounts.project_bonuses) > 0) || (filter === "no-rate" && Number(row.summary.hourly_rate) === 0)
    );
  });
  const selected = data?.rows.find((row) => row.employee.id === Number(search.get("employee")));
  const select = (id: number) => setSearch({ employee: String(id) });
  const bonuses = rows.flatMap((row) => row.bonuses.filter((b) => !b.cancelled_at).map((bonus) => ({ employee: row.employee, bonus })));
  const selection = rows.map((row) => `employee_id=${row.employee.id}`).join("&");
  return (
    <div className="grid min-w-0 gap-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div><h1 className="font-display text-[34px] font-semibold leading-none tracking-tight">Финансы</h1><p className="mt-2 text-[13px] text-ink-2">Оклады, переработки и премии команды</p></div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 rounded-lg border border-line bg-surface p-1">
            <Button size="icon" variant="ghost" aria-label="Предыдущий месяц" onClick={() => go(-1)} disabled={year === 2000 && month === 1}><ChevronLeft /></Button>
            <Input className="w-40 border-0" type="month" aria-label="Месяц расчёта" value={monthValue} min="2000-01" max="2100-12" onChange={(event) => {
              if (/^\d{4}-\d{2}$/.test(event.target.value) && event.target.value >= "2000-01" && event.target.value <= "2100-12") {
                const [y, m] = event.target.value.split("-");
                navigate(`/finances/${Number(y)}/${Number(m)}`);
              }
            }} />
            <Button size="icon" variant="ghost" aria-label="Следующий месяц" onClick={() => go(1)} disabled={year === 2100 && month === 12}><ChevronRight /></Button>
          </div>
          <Button onClick={() => navigate("/finances")} disabled={current === monthValue}>Текущий</Button>
        </div>
      </header>
      {error ? <ErrorState error={error} onRetry={() => void refetch()} /> : !data ? <Skeleton className="h-96" /> : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2"><h2 className="font-display text-[20px] font-semibold">{label}</h2>{!data.complete ? <Badge tone="deviation">Промежуточный расчёт</Badge> : null}</div>
            <div className="flex gap-2">
              <Dropdown><DropdownTrigger asChild><Button disabled={isFetching}><Download /> Экспорт</Button></DropdownTrigger><DropdownContent>
                <DropdownItem asChild><a href={exportUrl(`/finances/${year}/${month}.xlsx`)} download>Вся команда · Excel</a></DropdownItem>
                <DropdownItem asChild><a href={exportUrl(`/finances/${year}/${month}.csv`)} download>Вся команда · CSV</a></DropdownItem>
                <DropdownItem asChild disabled={!rows.length}><a href={rows.length ? exportUrl(`/finances/${year}/${month}.xlsx?${selection}`) : undefined} download>Текущий отбор ({rows.length}) · Excel</a></DropdownItem>
              </DropdownContent></Dropdown>
              {admin ? <Button variant="primary" onClick={() => setAdding(true)} disabled={isFetching}><Plus /> Добавить премию</Button> : null}
            </div>
          </div>
          <FinanceSummary amounts={data.totals} count={data.rows.length} />
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative min-w-44 flex-1 sm:max-w-80"><Search className="pointer-events-none absolute left-2.5 top-2 size-4 text-ink-3" /><Input className="pl-8" aria-label="Найти сотрудника" placeholder="Имя или должность" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
            <Select className="w-auto" aria-label="Отбор начислений" value={filter} onChange={(event) => setFilter(event.target.value)}>
              <option value="all">Все сотрудники</option><option value="overtime">С переработкой</option><option value="bonuses">С проектными премиями</option><option value="no-rate">Без ставки</option>
            </Select>
            <span className="text-[12px] text-ink-3">Показано: {rows.length} из {data.rows.length}</span>
          </div>
          <FinanceTable rows={rows} onSelect={select} />
          <section className="rounded-lg border border-line bg-surface p-4">
            <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">Премии за проекты</h2><span className="text-[12px] text-ink-3">За выбранный месяц и отбор · {bonuses.length}</span></div>
            {bonuses.length ? <ul className="mt-3 max-h-80 overflow-y-auto divide-y divide-line">{bonuses.map(({ employee, bonus }) => (
              <li key={bonus.id}><button onClick={() => select(employee.id)} className="flex w-full items-center justify-between gap-4 rounded px-1 py-3 text-left hover:bg-surface-2">
                <span className="min-w-0"><span className="block truncate text-[13px] font-medium">{bonus.title}</span><span className="text-[12px] text-ink-3">{employee.short_name}</span></span><span className="whitespace-nowrap text-[14px] font-semibold tnum">{money(bonus.amount)}</span>
              </button></li>
            ))}</ul> : <p className="mt-2 text-[13px] text-ink-3">Премий по этому отбору пока нет. Администратор может добавить сумму за закрытый проект.</p>}
          </section>
          <details className="rounded-lg border border-line px-4 py-3 text-[13px] text-ink-2">
            <summary className="cursor-pointer font-medium text-ink">Как считается оплата</summary>
            <div className="mt-3 grid max-w-3xl gap-2 leading-relaxed"><p>Оклад — полная месячная норма × часовая ставка. Если зачтённых часов меньше нормы, оклад сохраняется.</p><p>Переработка — часы сверх нормы × та же ставка. Используем итог таблицы: часы с учётом эффективности за вычетом штрафа за опоздания.</p><p>К окладу и переработке прибавляются проектные премии администратора. Ставка и норма берутся из условий выбранного месяца. Здесь отображается расчёт сумм; фактические перечисления не отмечаются.</p></div>
          </details>
          {selected ? <FinanceDetails key={selected.employee.id} row={selected} year={year} month={month} label={label} onClose={() => setSearch({})} /> : null}
          {adding ? <BonusForm month={`${monthValue}-01`} label={label} onClose={() => setAdding(false)} /> : null}
        </>
      )}
    </div>
  );
}
