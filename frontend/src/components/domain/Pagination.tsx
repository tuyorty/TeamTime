import { Button } from "@/components/ui/button";

export function Pagination({
  offset,
  total,
  limit = 25,
  onChange,
}: {
  offset: number;
  total: number;
  limit?: number;
  onChange: (offset: number) => void;
}) {
  if (total <= limit && offset === 0) return null;
  return (
    <nav
      aria-label="Страницы"
      className="flex flex-wrap items-center justify-between gap-3 text-[12px] text-ink-3"
    >
      <span className="tnum">
        {offset >= total && total > 0
          ? `На этой странице записей нет · всего ${total}`
          : total
            ? `${Math.min(offset + 1, total)}–${Math.min(offset + limit, total)} из ${total}`
            : "Записей нет"}
      </span>
      <div className="flex items-center gap-2">
        <Button size="sm" disabled={!offset} onClick={() => onChange(Math.max(0, offset - limit))}>
          ← Назад
        </Button>
        <Button size="sm" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
          Далее →
        </Button>
      </div>
    </nav>
  );
}
