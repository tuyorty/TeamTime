import { Select } from "@/components/ui/field";
import type { SortState } from "@/pages/month/sorting";

export interface SortOption<K extends string> extends SortState<K> {
  label: string;
}

/** Явный выбор порядка для таблиц и карточек, синхронизированный с заголовками колонок. */
export function SortSelect<K extends string>({ label, options, sort, onChange }: {
  label: string;
  options: readonly SortOption<K>[];
  sort: SortState<K> | null;
  onChange: (value: SortState<K> | null) => void;
}) {
  return (
    <Select
      className="w-auto max-w-full"
      aria-label={label}
      value={sort ? `${sort.key}:${sort.dir}` : ""}
      onChange={(event) => {
        const option = options.find((item) => `${item.key}:${item.dir}` === event.target.value);
        onChange(option ? { key: option.key, dir: option.dir } : null);
      }}
    >
      <option value="">По умолчанию · по фамилии</option>
      {options.map((option) => (
        <option key={`${option.key}:${option.dir}`} value={`${option.key}:${option.dir}`}>
          {option.label}
        </option>
      ))}
    </Select>
  );
}
