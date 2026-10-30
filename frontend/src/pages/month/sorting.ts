import { useState } from "react";

export type SortDir = "asc" | "desc";
export interface SortState<K extends string> {
  key: K;
  dir: SortDir;
}

/** Клик по колонке: сначала «больше — выше» (имя — по алфавиту), потом наоборот, потом без сортировки. */
export function useSort<K extends string>() {
  const [sort, setSort] = useState<SortState<K> | null>(null);
  const toggle = (key: K) =>
    setSort((cur) => {
      const first: SortDir = key === "name" ? "asc" : "desc";
      if (!cur || cur.key !== key) return { key, dir: first };
      if (cur.dir === first) return { key, dir: first === "asc" ? "desc" : "asc" };
      return null;
    });
  return { sort, toggle, setSort };
}

/** Стабильная сортировка; без выбранной колонки — исходный порядок (по фамилии). */
export function sortRows<T, K extends string>(
  rows: readonly T[],
  sort: SortState<K> | null,
  get: Record<K, (row: T) => number | string>,
): T[] {
  if (!sort) return [...rows];
  const value = get[sort.key];
  const sign = sort.dir === "asc" ? 1 : -1;
  return rows
    .map((row, i) => ({ row, i, v: value(row) }))
    .sort((a, b) => {
      const c = typeof a.v === "string" ? a.v.localeCompare(String(b.v), "ru") : a.v - Number(b.v);
      return c !== 0 ? c * sign : a.i - b.i;
    })
    .map((x) => x.row);
}

/** Подпись строки итогов: вся команда или только показанные. */
export function footLabel(shown: number, total: number, all: string): string {
  return shown === total ? all : `Показанные, ${shown} из ${total}`;
}
