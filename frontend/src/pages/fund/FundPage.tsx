import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { FinanceModeButton } from "@/components/domain/FinanceMode";
import { useNavigate, useSearchParams } from "react-router";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  Plus,
  Settings2,
  LogOut,
  LockKeyhole,
  Wallet,
  AlertCircle,
} from "lucide-react";
import { api } from "@/api/client";
import {
  useFundOverview,
  useFundReport,
  useTeamSession,
  type FundAmounts,
  type FundOverview,
  type TeamActor,
} from "@/api/fund";
import { useMeta } from "@/api/queries";
import { TeamLogin } from "@/components/layout/TeamGate";
import { DepartmentFilter } from "@/components/domain/DepartmentFilter";
import { ErrorState } from "@/components/domain/feedback";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { useDepartmentFilter } from "@/lib/departments";
import { money, shiftMonth } from "@/lib/format";
import { sumMoney } from "../finance/amounts";
import { FundCharts } from "./FundCharts";
import { FundDetails } from "./FundDetails";
import { FundForm } from "./FundForm";
import {
  amountField,
  decisionForm,
  reasonField,
  type FormSpec,
} from "./formTypes";
import { claimForm, operationForm, personField } from "./forms";
import { FundSettings } from "./FundSettings";
import { FundReviews } from "./FundReviews";
import { FundHistory } from "./FundHistory";
import {
  dateLabel,
  formatShare,
  hours,
  operationNames,
  tableClass,
} from "./format";
import { Card, Empty, State, Stat } from "./shared";

export default function FundPage({
  year,
  month,
}: {
  year: number;
  month: number;
}) {
  const session = useTeamSession();
  const setup = useQuery({
    queryKey: ["fund", "setup"],
    queryFn: () =>
      api.get<{ needs_bootstrap: boolean; first_month: string }>("/fund/setup"),
    enabled: !!session.data?.actor,
  });
  const [initializing, setInitializing] = useState(false);
  const cache = useQueryClient();
  if (!session.data) return <Skeleton className="h-64" />;
  if (!session.data.actor) return <TeamLogin compact />;
  if (setup.data?.needs_bootstrap)
    return (
      <Card>
        <h1 className="text-xl font-semibold">
          Первоначальная настройка фонда
        </h1>
        <p className="my-3 text-sm text-ink-2">
          Подтвердите назначение первого руководителя под своей учётной записью.
          Для этого включите режим администратора в меню приложения.
        </p>
        <Button onClick={() => setInitializing(true)}>
          Назначить меня руководителем
        </Button>
        {initializing && (
          <FundForm
            onClose={() => setInitializing(false)}
            spec={{
              title: "Первый руководитель фонда",
              path: "/fund/bootstrap",
              fields: [],
              body: () => ({ joined_on: setup.data!.first_month }),
              after: async () => {
                await cache.invalidateQueries();
              },
            }}
          />
        )}
      </Card>
    );
  return (
    <FundContent
      key={`${year}-${month}-${session.data.actor.employee_id}`}
      year={year}
      month={month}
      actor={session.data.actor}
    />
  );
}

function FundContent({
  year,
  month,
  actor,
}: {
  year: number;
  month: number;
  actor: TeamActor;
}) {
  const monthValue = `${year}-${String(month).padStart(2, "0")}`;
  const monthDate = `${monthValue}-01`;
  const report = useFundReport(monthDate);
  const overview = useFundOverview();
  const meta = useMeta();
  const navigate = useNavigate();
  const cache = useQueryClient();
  const department = useDepartmentFilter();
  const [search, setSearch] = useSearchParams();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("name");
  const [filter, setFilter] = useState("all");
  const [form, setForm] = useState<FormSpec>();
  const [settings, setSettings] = useState(false);
  const tab = search.get("tab") ?? "month";
  const today = meta.data?.today ?? monthDate;
  const rows = (report.data?.rows ?? [])
    .filter(
      (r) =>
        department.matches(r.employee) &&
        r.employee.name
          .toLocaleLowerCase("ru-RU")
          .includes(query.toLocaleLowerCase("ru-RU")) &&
        (filter === "all" ||
          (filter === "issues" && r.blockers.length > 0) ||
          (filter === "priority" && r.no_other_income) ||
          (filter === "due" && Number(r.amounts?.due) > 0)),
    )
    .sort((a, b) =>
      sort === "name"
        ? a.employee.name.localeCompare(b.employee.name, "ru")
        : (Number(
            b.amounts?.[sort.replace("-asc", "") as keyof FundAmounts] ?? 0,
          ) -
            Number(
              a.amounts?.[sort.replace("-asc", "") as keyof FundAmounts] ?? 0,
            )) *
          (sort.endsWith("-asc") ? -1 : 1),
    );
  const selected = report.data?.rows.find(
    (r) => r.employee.id === Number(search.get("employee")),
  );
  const select = (id: number) =>
    setSearch((s) => {
      s.set("employee", String(id));
      return s;
    });
  const totals = (key: keyof FundAmounts) =>
    sumMoney(rows.map((r) => r.amounts?.[key] ?? "0"));
  const go = (delta: number) => {
    const next = shiftMonth(year, month, delta);
    navigate(`/finances/${next.year}/${next.month}?fund=1&tab=${tab}`);
  };
  const pending = overview.data
    ? overview.data.claims.filter((c) => c.state === "pending").length +
      overview.data.requests.filter((c) => c.state === "pending").length +
      overview.data.adjustments.filter((c) => c.state === "pending").length +
      overview.data.closed_changes.length
    : 0;
  return (
    <div className="grid min-w-0 grid-cols-1 gap-5">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-[34px] font-semibold leading-none tracking-tight">
            Финансы
          </h1>
          <p className="mt-2 text-sm text-ink-2">
            Расчёт команды и движение средств фонда
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FinanceModeButton />
          <span className="mr-1 text-xs text-ink-2">
            {actor.name}
            {actor.leader ? " · руководитель" : ""}
          </span>
          <Button
            size="icon"
            aria-label="Выйти из учётной записи"
            onClick={async () => {
              await api.post("/team/logout");
              await cache.invalidateQueries();
            }}
          >
            <LogOut />
          </Button>
          {actor.leader && (
            <Button onClick={() => setSettings(true)}>
              <Settings2 /> Настройки фонда
            </Button>
          )}
        </div>
      </header>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <nav
          aria-label="Разделы финансов"
          className="flex max-w-full gap-1 overflow-x-auto rounded-lg border border-line bg-surface p-1"
        >
          {[
            ["month", "Расчёт месяца"],
            ["fund", "Фонд"],
            ["expenses", "Расходы и компенсации"],
            ["balances", "Переплаты и займы"],
          ].map(([key, title]) => (
            <button
              key={key}
              onClick={() => setSearch({ fund: "1", tab: key! })}
              aria-current={tab === key ? "page" : undefined}
              className={`whitespace-nowrap rounded-md px-3 py-2 text-sm transition-colors ${tab === key ? "bg-accent-soft font-medium text-accent-ink" : "text-ink-2 hover:bg-surface-2"}`}
            >
              {title}
            </button>
          ))}
        </nav>
        <div className="flex items-center gap-1 rounded-lg border border-line bg-surface p-1">
          <Button
            size="icon"
            variant="ghost"
            aria-label="Предыдущий месяц"
            onClick={() => go(-1)}
          >
            <ChevronLeft />
          </Button>
          <Input
            type="month"
            className="w-36 border-0"
            aria-label="Месяц фонда"
            value={monthValue}
            min="2026-09"
            max="2100-12"
            onChange={(e) => {
              if (/^\d{4}-\d{2}$/.test(e.target.value)) {
                const [y, m] = e.target.value.split("-");
                navigate(`/finances/${y}/${Number(m)}?fund=1&tab=${tab}`);
              }
            }}
          />
          <Button
            size="icon"
            variant="ghost"
            aria-label="Следующий месяц"
            onClick={() => go(1)}
          >
            <ChevronRight />
          </Button>
        </div>
      </div>
      {overview.error ? (
        <ErrorState
          error={overview.error}
          onRetry={() => void overview.refetch()}
        />
      ) : !overview.data ? (
        <Skeleton className="h-80" />
      ) : (
        <>
          {pending > 0 && actor.leader && (
            <button
              className="flex items-center justify-between gap-3 rounded-lg border border-deviation/30 bg-deviation-soft px-4 py-3 text-left text-sm text-deviation-ink"
              onClick={() =>
                setSearch({ fund: "1", tab: "expenses", review: "yes" })
              }
            >
              <span className="flex items-center gap-2">
                <AlertCircle className="size-4" />
                На согласовании: {pending}
              </span>
              <span>Посмотреть →</span>
            </button>
          )}
          {tab === "month" ? (
            <>
              {report.error ? (
                <ErrorState
                  error={report.error}
                  onRetry={() => void report.refetch()}
                />
              ) : !report.data ? (
                <Skeleton className="h-80" />
              ) : (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <Badge tone={report.data.closed ? "accent" : "deviation"}>
                        {report.data.closed
                          ? "Месяц закрыт"
                          : "Предварительный расчёт"}
                      </Badge>
                      <span className="text-xs text-ink-3">
                        {rows.length} из {report.data.rows.length} сотрудников
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button asChild disabled={!rows.length}>
                        <a
                          aria-disabled={!rows.length}
                          onClick={(e) => {
                            if (!rows.length) e.preventDefault();
                          }}
                          href={`/api/v1/fund/export/${monthDate}.xlsx?${rows.map((r) => `employee_id=${r.employee.id}`).join("&")}`}
                          download
                        >
                          <Download /> Excel по отбору
                        </a>
                      </Button>
                      <Button asChild>
                        <a
                          href={`/api/v1/fund/export/${monthDate}.csv`}
                          download
                        >
                          CSV всей команды
                        </a>
                      </Button>
                      {actor.leader && !report.data.closed && (
                        <>
                          <Button
                            onClick={() =>
                              setForm({
                                title: "Премия за проект",
                                path: "/fund/bonuses",
                                fields: [
                                  personField(overview.data!),
                                  amountField,
                                  reasonField,
                                ],
                                body: (v, id) => ({
                                  request_id: id,
                                  employee_id: Number(v.employee_id),
                                  month: monthDate,
                                  amount: v.amount,
                                  reason: v.reason,
                                }),
                              })
                            }
                          >
                            <Plus /> Премия
                          </Button>
                          <Button
                            variant="primary"
                            disabled={!report.data.can_close}
                            onClick={() =>
                              setForm({
                                title: `Закрыть ${monthValue}`,
                                description:
                                  "Расчёт и его исходные данные будут сохранены. Последующие исправления оформляются отдельной корректировкой.",
                                path: `/fund/months/${monthDate}/close`,
                                fields: [reasonField],
                                submit: "Закрыть месяц",
                                body: (v) => ({
                                  fingerprint: report.data!.fingerprint,
                                  reason: v.reason,
                                }),
                              })
                            }
                          >
                            <LockKeyhole /> Закрыть месяц
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                  {report.data.blockers.length > 0 && (
                    <div className="rounded-lg bg-deviation-soft px-4 py-3 text-sm text-deviation-ink">
                      {report.data.blockers.map((b, i) => (
                        <p key={i}>{b.message}</p>
                      ))}
                    </div>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <DepartmentFilter
                      value={department.department}
                      onChange={department.setDepartment}
                    />
                    <Input
                      className="w-52"
                      placeholder="Найти сотрудника"
                      aria-label="Поиск в расчёте фонда"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                    />
                    <Select
                      className="w-auto"
                      aria-label="Статус расчёта"
                      value={filter}
                      onChange={(e) => setFilter(e.target.value)}
                    >
                      <option value="all">Все сотрудники</option>
                      <option value="issues">Нужно уточнить</option>
                      <option value="due">Есть к выплате</option>
                      <option value="priority">Без иных доходов</option>
                    </Select>
                    <Select
                      className="w-auto"
                      aria-label="Сортировка расчёта"
                      value={sort}
                      onChange={(e) => setSort(e.target.value)}
                    >
                      <option value="name">По имени</option>
                      <option value="due">К выплате: больше сначала</option>
                      <option value="due-asc">К выплате: меньше сначала</option>
                      <option value="salary">Начислено: больше сначала</option>
                      <option value="overpayment_out">
                        Переплата: больше сначала
                      </option>
                    </Select>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    <Stat
                      label="Начислено за время"
                      amount={totals("salary")}
                      hint="По выбранным сотрудникам"
                    />
                    <Stat
                      label="Получено из источников"
                      amount={totals("received")}
                      hint="Только фактические поступления"
                    />
                    <Stat
                      label="Начислено фондом"
                      amount={totals("accrued")}
                      hint="Доплаты и компенсации"
                    />
                    <Stat
                      label="К выплате из фонда"
                      amount={totals("due")}
                      accent
                      hint={
                        report.data.closed
                          ? "С учётом погашенных обязательств"
                          : "Оценка до закрытия месяца"
                      }
                    />
                  </div>
                  <Card className="!p-0 overflow-hidden">
                    <div className="overflow-x-auto">
                      <table className={tableClass}>
                        <thead>
                          <tr>
                            <th>Сотрудник</th>
                            <th>Целевая сумма / ставка</th>
                            <th>Норма / зачтено</th>
                            <th>Начислено</th>
                            <th>Источники</th>
                            <th>Переплата на конец</th>
                            <th>Доплата фонда</th>
                            <th>Компенсации</th>
                            <th>К выплате</th>
                            <th>Готовность</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((r) => (
                            <tr
                              key={r.employee.id}
                              className="hover:bg-surface-2/50"
                            >
                              <td>
                                <button
                                  onClick={() => select(r.employee.id)}
                                  className="flex items-center gap-2 text-left font-medium text-accent-ink"
                                >
                                  {r.employee.avatar_url && (
                                    <img
                                      className="size-8 rounded-full object-cover"
                                      src={r.employee.avatar_url}
                                      alt=""
                                    />
                                  )}
                                  <span className="whitespace-nowrap">
                                    {r.employee.short_name}
                                    {r.no_other_income && (
                                      <span className="mt-1 block text-[11px] font-normal text-ink-3">
                                        Нет иных доходов
                                      </span>
                                    )}
                                  </span>
                                </button>
                              </td>
                              <td className="tnum whitespace-nowrap">
                                {r.inputs?.conditions.length === 1 ? (
                                  <>
                                    {money(r.inputs.conditions[0]!.target)}
                                    <span className="block text-xs text-ink-3">
                                      доля ставки{" "}
                                      {formatShare(
                                        r.inputs.conditions[0]!.share,
                                      )}
                                    </span>
                                  </>
                                ) : (
                                  <button
                                    className="text-accent-ink"
                                    onClick={() => select(r.employee.id)}
                                  >
                                    История условий
                                  </button>
                                )}
                              </td>
                              <td className="tnum whitespace-nowrap">
                                {hours(r.norm_sec)} /{" "}
                                <strong>{hours(r.credited_sec)}</strong>
                              </td>
                              {(
                                [
                                  "salary",
                                  "received",
                                  "overpayment_out",
                                  "supplement",
                                  "compensation",
                                  "due",
                                ] as const
                              ).map((key) => (
                                <td
                                  key={key}
                                  className={`tnum whitespace-nowrap ${key === "due" ? "font-semibold text-accent" : ""}`}
                                >
                                  {r.amounts ? money(r.amounts[key]) : "—"}
                                </td>
                              ))}
                              <td>
                                <button onClick={() => select(r.employee.id)}>
                                  <Badge
                                    tone={
                                      r.blockers.length ? "deviation" : "accent"
                                    }
                                  >
                                    {r.blockers.length
                                      ? `Вопросов: ${r.blockers.length}`
                                      : "Готово"}
                                  </Badge>
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {!rows.length && (
                      <Empty>Нет сотрудников по выбранным условиям</Empty>
                    )}
                  </Card>
                  <FundCharts rows={rows} onSelect={select} />
                </>
              )}
            </>
          ) : tab === "fund" ? (
            <Treasury
              data={overview.data}
              actor={actor}
              today={today}
              onForm={setForm}
            />
          ) : tab === "expenses" ? (
            <Expenses
              data={overview.data}
              actor={actor}
              today={today}
              month={monthDate}
              onForm={setForm}
            />
          ) : (
            <Balances
              data={overview.data}
              actor={actor}
              today={today}
              onForm={setForm}
            />
          )}
          <FundHistory data={overview.data} />
          {settings && (
            <FundSettings
              data={overview.data}
              actor={actor}
              month={monthDate}
              today={today}
              onForm={setForm}
              onClose={() => setSettings(false)}
            />
          )}
        </>
      )}
      {selected && report.data && (
        <FundDetails
          row={selected}
          report={report.data}
          actor={actor}
          today={today}
          onForm={setForm}
          onClose={() =>
            setSearch((s) => {
              s.delete("employee");
              return s;
            })
          }
        />
      )}
      {form && <FundForm spec={form} onClose={() => setForm(undefined)} />}
    </div>
  );
}

type SectionProps = {
  data: FundOverview;
  actor: TeamActor;
  today: string;
  onForm: (s: FormSpec) => void;
};
function Treasury({ data, actor, today, onForm }: SectionProps) {
  const [kind, setKind] = useState("all");
  const [state, setState] = useState("all");
  const name = (id: number | null) =>
    data.members.find((m) => m.id === id)?.short_name ?? "—";
  const basket = (id: number | null) =>
    data.baskets.find((b) => b.id === id)?.name ?? "Без движения денег";
  const operations = data.operations.filter(
    (o) =>
      (kind === "all" || o.kind === kind) &&
      (state === "all" || o.state === state),
  );
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Деньги фонда"
          amount={data.cash}
          hint="Остатки всех корзин"
        />
        <Stat
          label="Невыплаченные обязательства"
          amount={data.due}
          hint="Закрытые начисления и одобренные компенсации"
        />
        <Stat
          label="Свободные средства"
          amount={data.free}
          hint="Деньги за вычетом обязательств"
          accent
        />
        <Card>
          <p className="text-xs text-ink-2">Запас фонда</p>
          <p className="tnum mt-2 text-[25px] font-semibold">
            {data.runway
              ? `${Number(data.runway).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} мес.`
              : "Пока нет оценки"}
          </p>
          <p className="mt-2 text-xs text-ink-3">
            По фактическим выплатам за {data.runway_months_used} закрытых мес.
          </p>
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        {data.baskets.map((b) => (
          <Card key={b.id}>
            <div className="flex items-center justify-between">
              <h2 className="font-semibold">{b.name}</h2>
              <Wallet className="size-5 text-accent" />
            </div>
            <p className="mt-1 text-xs text-ink-3">
              Ответственный: {name(b.owner_id)}
            </p>
            <p className="tnum my-4 text-2xl font-semibold">
              {money(b.balance)}
            </p>
            <p className="text-xs text-ink-2">
              {b.reconciled_on
                ? `Сверено ${dateLabel(b.reconciled_on)} · фактически ${money(b.actual ?? "0")}`
                : "Остаток ещё не сверяли"}
            </p>
            {Number(b.difference) !== 0 && b.difference !== null && (
              <p className="mt-1 text-xs text-late-ink">
                Расхождение: {money(b.difference)}
              </p>
            )}
            {b.owner_id === actor.employee_id && (
              <Button
                className="mt-3"
                onClick={() =>
                  onForm({
                    title: `Сверить: ${b.name}`,
                    description:
                      "Введите фактический остаток. Сверка сама по себе не меняет деньги фонда.",
                    path: "/fund/reconciliations",
                    fields: [
                      {
                        name: "as_of",
                        label: "На дату",
                        type: "date",
                        value: today,
                        max: today,
                      },
                      {
                        ...amountField,
                        name: "actual",
                        label: "Фактический остаток, ₽",
                        min: "0",
                      },
                      reasonField,
                    ],
                    body: (v, id) => ({
                      request_id: id,
                      basket_id: b.id,
                      as_of: v.as_of,
                      actual: v.actual,
                      reason: v.reason,
                    }),
                  })
                }
              >
                Сверить остаток
              </Button>
            )}
          </Card>
        ))}
      </div>
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold">Журнал операций</h2>
          <Button
            variant="primary"
            onClick={() => onForm(operationForm(data, actor, today))}
          >
            <Plus /> Операция
          </Button>
        </div>
        <div className="my-4 flex flex-wrap gap-2">
          <Select
            className="w-auto"
            aria-label="Вид операции"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
          >
            <option value="all">Все виды</option>
            {Array.from(new Set(data.operations.map((o) => o.kind))).map(
              (k) => (
                <option key={k} value={k}>
                  {operationNames[k] ?? k}
                </option>
              ),
            )}
          </Select>
          <Select
            className="w-auto"
            aria-label="Статус операции"
            value={state}
            onChange={(e) => setState(e.target.value)}
          >
            <option value="all">Все статусы</option>
            <option value="draft">Ждут подтверждения</option>
            <option value="posted">Проведены</option>
            <option value="cancelled">Отменены</option>
          </Select>
        </div>
        <div className="overflow-x-auto">
          <table className={tableClass}>
            <thead>
              <tr>
                <th>Дата / операция</th>
                <th>Корзина / участник</th>
                <th>Сумма</th>
                <th>Основание</th>
                <th>Статус</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {operations.map((o) => {
                const owner =
                  data.baskets.find((b) => b.id === o.basket_id)?.owner_id ===
                    actor.employee_id ||
                  (!o.basket_id && actor.leader);
                const reversible =
                  o.state === "posted" &&
                  owner &&
                  !["opening", "closure", "obligation", "reversal"].includes(o.kind) &&
                  !data.operations.some((r) => r.reverses_id === o.id);
                return (
                  <tr key={o.id}>
                    <td>
                      <span className="block text-xs text-ink-3">
                        {dateLabel(o.occurred_on)} · #{o.id}
                      </span>
                      {operationNames[o.kind] ?? o.kind}
                    </td>
                    <td>
                      {basket(o.basket_id)}
                      {o.target_basket_id && ` → ${basket(o.target_basket_id)}`}
                      <span className="block text-xs text-ink-3">
                        {name(o.employee_id)}
                      </span>
                    </td>
                    <td className="tnum whitespace-nowrap font-medium">
                      {Number(o.amount) === 0 ? (
                        <span title="Запись без денежного перевода">—</span>
                      ) : (
                        money(o.amount)
                      )}
                    </td>
                    <td className="max-w-64 break-words">{o.reason}</td>
                    <td>
                      <State value={o.state} />
                    </td>
                    <td>
                      <div className="flex flex-wrap gap-1">
                        {o.state === "draft" && owner && (
                          <Button
                            size="sm"
                            onClick={() =>
                              onForm({
                                title: "Провести операцию",
                                description: `${operationNames[o.kind]} · ${money(o.amount)} · ${o.reason}`,
                                path: `/fund/operations/${o.id}/confirm`,
                                fields: [],
                                submit: "Подтвердить факт",
                                body: () => ({}),
                              })
                            }
                          >
                            Подтвердить
                          </Button>
                        )}
                        {o.state === "draft" &&
                          (owner || o.created_by === actor.employee_id) && (
                            <Button
                              size="sm"
                              onClick={() =>
                                onForm({
                                  title: "Отменить черновик",
                                  path: `/fund/operations/${o.id}/cancel`,
                                  fields: [reasonField],
                                  body: (v) => ({ reason: v.reason }),
                                })
                              }
                            >
                              Отменить
                            </Button>
                          )}
                        {o.state === "draft" &&
                          o.kind === "loan_offset" &&
                          o.employee_id === actor.employee_id &&
                          !o.consented_at && (
                            <Button
                              size="sm"
                              onClick={() =>
                                onForm({
                                  title: "Согласиться на зачёт займа",
                                  description: `${money(o.amount)} будет зачтено из начисленной выплаты в погашение займа.`,
                                  path: `/fund/operations/${o.id}/consent`,
                                  fields: [],
                                  submit: "Согласен",
                                  body: () => ({}),
                                })
                              }
                            >
                              Согласен на зачёт
                            </Button>
                          )}
                        {reversible && (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() =>
                              onForm({
                                title: "Сторнировать операцию",
                                description:
                                  "Создаст обратную запись. Исходная операция останется в истории.",
                                path: `/fund/operations/${o.id}/reverse`,
                                fields: [reasonField],
                                body: (v) => ({ reason: v.reason }),
                              })
                            }
                          >
                            Сторно
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {!operations.length && <Empty>Нет операций по этому отбору</Empty>}
      </Card>
    </>
  );
}

function Expenses({
  data,
  actor,
  today,
  month,
  onForm,
}: SectionProps & { month: string }) {
  const [filter, setFilter] = useState("all");
  return (
    <>
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-semibold">Расходы за свой счёт</h2>
            <p className="mt-1 text-xs text-ink-3">
              После одобрения фонд возмещает точную сумму, отдельно от доплаты
            </p>
          </div>
          <Button
            variant="primary"
            onClick={() => onForm(claimForm(month, today))}
          >
            <Plus /> Заявить расход
          </Button>
        </div>
        <Select
          aria-label="Статус компенсации"
          className="my-4 w-auto"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">Все заявки</option>
          <option value="pending">Ждут согласования</option>
          <option value="approved">Подтверждены</option>
          <option value="rejected">Отклонены</option>
        </Select>
        <div className="overflow-x-auto">
          <table className={tableClass}>
            <thead>
              <tr>
                <th>Участник / дата</th>
                <th>Расход</th>
                <th>Сумма</th>
                <th>Месяц</th>
                <th>Статус</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {data.claims
                .filter((c) => filter === "all" || c.state === filter)
                .map((c) => (
                  <tr key={c.id}>
                    <td>
                      {
                        data.members.find((m) => m.id === c.employee_id)
                          ?.short_name
                      }
                      <span className="block text-xs text-ink-3">
                        {dateLabel(c.spent_on)}
                      </span>
                    </td>
                    <td className="max-w-80">
                      {c.title}
                      {c.decision_reason && (
                        <span className="mt-1 block text-xs text-ink-3">
                          {c.decision_reason}
                        </span>
                      )}
                    </td>
                    <td className="tnum whitespace-nowrap">
                      {money(c.amount)}
                    </td>
                    <td>{c.month.slice(0, 7)}</td>
                    <td>
                      <State value={c.state} />
                    </td>
                    <td>
                      {actor.leader && c.state === "pending" && (
                        <div className="flex gap-1">
                          <Button
                            size="sm"
                            onClick={() =>
                              onForm(
                                decisionForm(
                                  `/fund/claims/${c.id}/decide`,
                                  "Одобрить компенсацию",
                                  true,
                                ),
                              )
                            }
                          >
                            Одобрить
                          </Button>
                          <Button
                            size="sm"
                            onClick={() =>
                              onForm(
                                decisionForm(
                                  `/fund/claims/${c.id}/decide`,
                                  "Отклонить компенсацию",
                                  false,
                                ),
                              )
                            }
                          >
                            Отклонить
                          </Button>
                        </div>
                      )}
                      <Attachments
                        claimId={c.id}
                        own={c.employee_id === actor.employee_id}
                        allowed={
                          actor.leader || c.employee_id === actor.employee_id
                        }
                      />
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
        {!data.claims.length && <Empty>Заявок на компенсацию пока нет</Empty>}
      </Card>
      <FundReviews data={data} actor={actor} onForm={onForm} />
    </>
  );
}

function Attachments({
  claimId,
  own,
  allowed,
}: {
  claimId: number;
  own: boolean;
  allowed: boolean;
}) {
  const [files, setFiles] = useState<{ id: number; name: string }[]>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (!allowed) return null;
  async function load() {
    try {
      setFiles(await api.get(`/fund/claims/${claimId}/attachments`));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <div className="mt-2 grid gap-2">
      <button
        className="text-left text-xs text-accent-ink"
        onClick={() => void load()}
      >
        Чеки и вложения
      </button>
      {files?.map((f) => (
        <a
          key={f.id}
          href={`/api/v1/fund/attachments/${f.id}`}
          className="max-w-48 truncate text-xs underline"
        >
          {f.name}
        </a>
      ))}
      {own && files && (
        <label className="text-xs text-ink-2">
          {busy ? "Загрузка…" : "Добавить чек"}
          <input
            className="mt-1 block max-w-48 text-xs"
            type="file"
            disabled={busy}
            accept="image/jpeg,image/png,application/pdf"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              if (file.size > 10 * 1024 * 1024) {
                setError("Размер чека — до 10 МБ");
                return;
              }
              setBusy(true);
              setError("");
              try {
                const response = await fetch(
                  `/api/v1/fund/claims/${claimId}/attachment?name=${encodeURIComponent(file.name)}`,
                  {
                    method: "POST",
                    headers: {
                      "Content-Type": file.type,
                      "X-Requested-With": "teamtime",
                    },
                    body: file,
                  },
                );
                if (!response.ok)
                  throw new Error(
                    (await response.json()).detail ??
                      "Не удалось загрузить чек",
                  );
                await load();
              } catch (err) {
                setError((err as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          />
        </label>
      )}
      {error && (
        <p role="alert" className="text-xs text-late-ink">
          {error}
        </p>
      )}
    </div>
  );
}

function Balances({ data, actor, today, onForm }: SectionProps) {
  return (
    <>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="font-semibold">Переплаты участников</h2>
          <p className="mt-1 text-xs text-ink-3">
            Зачитываются в будущую зарплатную доплату. Компенсации и займы
            учитываются отдельно.
          </p>
          <div className="mt-4 overflow-x-auto">
            <table className={tableClass}>
              <thead>
                <tr>
                  <th>Участник</th>
                  <th>Остаток</th>
                  <th>История</th>
                </tr>
              </thead>
              <tbody>
                {data.members.map((m) => (
                  <tr key={m.id}>
                    <td>{m.short_name}</td>
                    <td className="tnum whitespace-nowrap">
                      {money(m.overpayment)}
                    </td>
                    <td>
                      <OverpaymentHistory employeeId={m.id} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card>
          <h2 className="font-semibold">Обязательства к выплате</h2>
          <p className="mt-1 text-xs text-ink-3">
            Очередность выбирает руководитель. Сначала участники без иных
            доходов, затем компенсации.
          </p>
          <div className="mt-4 max-h-96 space-y-3 overflow-y-auto">
            {data.obligations
              .filter((o) => Number(o.due) !== 0)
              .map((o) => (
                <div
                  key={o.id}
                  className="flex justify-between gap-2 border-b border-line pb-3 text-sm"
                >
                  <span>
                    {
                      data.members.find((m) => m.id === o.employee_id)
                        ?.short_name
                    }
                    <small className="mt-1 block text-ink-3">
                      {o.month.slice(0, 7)} · {o.title}
                    </small>
                  </span>
                  <strong className="tnum whitespace-nowrap">
                    {money(o.due)}
                  </strong>
                </div>
              ))}
            {!data.obligations.some((o) => Number(o.due) !== 0) && (
              <Empty>Невыплаченных обязательств нет</Empty>
            )}
          </div>
          <Button onClick={() => onForm(operationForm(data, actor, today))}>
            Оформить выплату
          </Button>
        </Card>
      </div>
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-semibold">Займы</h2>
            <p className="mt-1 text-xs text-ink-3">
              Беспроцентные, до двух месяцев. Новый заём доступен после
              погашения предыдущего.
            </p>
          </div>
          {actor.leader && (
            <Button
              onClick={() =>
                onForm({
                  title: "Одобрить заём",
                  description:
                    "Это решение о выдаче. Саму выдачу денег подтвердит ответственный за корзину.",
                  path: "/fund/loans",
                  fields: [
                    personField(data),
                    amountField,
                    {
                      name: "issued_on",
                      label: "Дата выдачи",
                      type: "date",
                      value: today,
                    },
                    {
                      name: "due_on",
                      label: "Вернуть до",
                      type: "date",
                      min: today,
                    },
                    reasonField,
                  ],
                  body: (v, id) => ({
                    request_id: id,
                    employee_id: Number(v.employee_id),
                    amount: v.amount,
                    issued_on: v.issued_on,
                    due_on: v.due_on,
                    reason: v.reason,
                  }),
                })
              }
            >
              <Plus /> Одобрить заём
            </Button>
          )}
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className={tableClass}>
            <thead>
              <tr>
                <th>Участник</th>
                <th>Сумма</th>
                <th>Остаток долга</th>
                <th>Срок</th>
                <th>Состояние</th>
              </tr>
            </thead>
            <tbody>
              {data.loans.map((l) => (
                <tr key={l.id}>
                  <td>
                    {
                      data.members.find((m) => m.id === l.employee_id)
                        ?.short_name
                    }
                    <span className="block text-xs text-ink-3">{l.reason}</span>
                  </td>
                  <td className="tnum whitespace-nowrap">{money(l.amount)}</td>
                  <td className="tnum whitespace-nowrap font-medium">
                    {money(l.outstanding)}
                  </td>
                  <td>{dateLabel(l.due_on)}</td>
                  <td>
                    <Badge
                      tone={
                        l.overdue
                          ? "late"
                          : l.issued && Number(l.outstanding) === 0
                            ? "accent"
                            : "neutral"
                      }
                    >
                      {l.overdue
                        ? "Срок прошёл"
                        : !l.issued
                          ? "Одобрен, не выдан"
                          : Number(l.outstanding) === 0
                            ? "Погашен"
                            : "Действует"}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!data.loans.length && <Empty>Займов нет</Empty>}
      </Card>
    </>
  );
}

function OverpaymentHistory({ employeeId }: { employeeId: number }) {
  const [history, setHistory] =
    useState<{ date: string; amount: string; reason: string }[]>();
  const [error, setError] = useState("");
  return (
    <div>
      <button
        className="text-xs text-accent-ink"
        onClick={async () => {
          if (history) {
            setHistory(undefined);
            return;
          }
          try {
            setHistory(
              await api.get(`/fund/members/${employeeId}/overpayment-history`),
            );
          } catch (e) {
            setError((e as Error).message);
          }
        }}
      >
        История
      </button>
      {history && (
        <ul className="mt-2 max-h-56 space-y-2 overflow-y-auto text-xs">
          {history.map((h, i) => (
            <li key={i}>
              {dateLabel(h.date)} · {money(h.amount)}
              <span className="block text-ink-3">{h.reason}</span>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="text-xs text-late-ink">{error}</p>}
    </div>
  );
}
