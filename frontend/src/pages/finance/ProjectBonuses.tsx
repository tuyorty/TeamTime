import { Search } from "lucide-react";
import { useState } from "react";

import type { EmployeeBrief, FinanceRow, ProjectBonus } from "@/api/types";
import { SortSelect, type SortOption } from "@/components/domain/SortSelect";
import { Input } from "@/components/ui/field";
import { money } from "@/lib/format";

import { sortRows, useSort } from "../month/sorting";

type Key = "amount" | "name" | "project" | "created";
type Item = { employee: EmployeeBrief; bonus: ProjectBonus };
const VALUES: Record<Key, (item: Item) => number | string> = {
  amount: (item) => Number(item.bonus.amount),
  name: (item) => item.employee.short_name,
  project: (item) => item.bonus.title,
  created: (item) => new Date(item.bonus.created_at).getTime(),
};
const OPTIONS: SortOption<Key>[] = [
  { key: "amount", dir: "desc", label: "Сумма: больше → меньше" },
  { key: "amount", dir: "asc", label: "Сумма: меньше → больше" },
  { key: "created", dir: "desc", label: "Сначала новые" },
  { key: "created", dir: "asc", label: "Сначала старые" },
  { key: "name", dir: "asc", label: "Сотрудник: А–Я" },
  { key: "name", dir: "desc", label: "Сотрудник: Я–А" },
  { key: "project", dir: "asc", label: "Проект: А–Я" },
  { key: "project", dir: "desc", label: "Проект: Я–А" },
];

export function ProjectBonuses({ rows, onSelect }: { rows: FinanceRow[]; onSelect: (id: number) => void }) {
  const [query, setQuery] = useState("");
  const { sort, setSort } = useSort<Key>();
  const bonuses = rows.flatMap((row) => row.bonuses
    .filter((bonus) => !bonus.cancelled_at)
    .map((bonus) => ({ employee: row.employee, bonus })));
  const needle = query.trim().toLocaleLowerCase("ru-RU");
  const visible = sortRows(bonuses.filter(({ employee, bonus }) =>
    `${employee.full_name} ${employee.short_name} ${bonus.title} ${bonus.note}`
      .toLocaleLowerCase("ru-RU").includes(needle)), sort, VALUES);

  return (
    <section aria-label="Премии за проекты" className="rounded-lg border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Премии за проекты</h2>
        <span className="text-[12px] text-ink-3">За выбранный месяц и отбор · {visible.length} из {bonuses.length}</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-3">
        <div className="relative min-w-0 basis-full sm:max-w-96 sm:flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-2 size-4 text-ink-3" />
          <Input className="pl-8" aria-label="Найти премию" placeholder="Проект, сотрудник или комментарий" value={query} onChange={(event) => setQuery(event.target.value)} />
        </div>
        <SortSelect label="Сортировка проектных премий" options={OPTIONS} sort={sort} onChange={setSort} />
      </div>
      {visible.length ? (
        <ul aria-label="Список проектных премий" className="mt-3 max-h-80 overflow-y-auto divide-y divide-line">
          {visible.map(({ employee, bonus }) => (
            <li key={bonus.id}>
              <button onClick={() => onSelect(employee.id)} className="flex w-full items-center justify-between gap-4 rounded px-1 py-3 text-left hover:bg-surface-2">
                <span className="min-w-0"><span className="block truncate text-[13px] font-medium">{bonus.title}</span><span className="text-[12px] text-ink-3">{employee.short_name}</span></span>
                <span className="whitespace-nowrap text-[14px] font-semibold tnum">{money(bonus.amount)}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-[13px] text-ink-3">{query.trim() ? "Премии не найдены. Измените поиск или отбор сотрудников." : "Премий по этому отбору пока нет. Администратор может добавить сумму за закрытый проект."}</p>
      )}
    </section>
  );
}
