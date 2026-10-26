import { Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/field";
import { Segmented } from "@/components/ui/segmented";

import { QUICK, type useMonthFilter } from "./useMonthFilter";

export function MonthFilters({
  state,
  total,
}: {
  state: ReturnType<typeof useMonthFilter>;
  total: number;
}) {
  const { filter, setFilter, positions, visible, active, reset } = state;
  return (
    <div className="no-print flex flex-wrap items-center gap-2">
      <label className="relative w-full sm:w-56">
        <span className="sr-only">Поиск по имени или должности</span>
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-3" aria-hidden />
        <Input
          value={filter.query}
          onChange={(e) => setFilter({ ...filter, query: e.target.value })}
          placeholder="Имя или должность"
          className="pl-8"
        />
      </label>
      {positions.length > 1 ? (
        <Select
          aria-label="Должность"
          className="w-full sm:w-52"
          value={filter.position}
          onChange={(e) => setFilter({ ...filter, position: e.target.value })}
        >
          <option value="">Все должности</option>
          {positions.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </Select>
      ) : null}
      <Segmented
        label="Быстрый фильтр"
        value={filter.quick}
        onChange={(quick) => setFilter({ ...filter, quick })}
        options={QUICK.map(({ value, label, title }) => ({ value, label, title }))}
      />
      {active ? (
        <span className="flex items-center gap-1 text-[12px] text-ink-3 tnum">
          Показано {visible.length} из {total}
          <Button size="sm" variant="ghost" onClick={reset}>
            <X /> Сбросить
          </Button>
        </span>
      ) : null}
    </div>
  );
}
