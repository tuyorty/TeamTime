import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";

export function MonthNavigation({ value, current, onChange }: { value: string; current: string; onChange: (value: string) => void }) {
  const shift = (delta: number) => {
    const [year, month] = value.split("-").map(Number);
    const date = new Date(year!, month! - 1 + delta, 1);
    onChange(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`);
  };
  return <div className="flex flex-wrap items-center gap-1">
    <Button variant="ghost" size="icon" aria-label="Предыдущий месяц" disabled={value <= "2000-01"} onClick={() => shift(-1)}><ChevronLeft /></Button>
    <Input type="month" className="w-40" aria-label="Месяц статистики" value={value} min="2000-01" max="2100-12" onChange={(event) => {
      if (/^\d{4}-(0[1-9]|1[0-2])$/.test(event.target.value) && event.target.value >= "2000-01" && event.target.value <= "2100-12") onChange(event.target.value);
    }} />
    <Button variant="ghost" size="icon" aria-label="Следующий месяц" disabled={value >= "2100-12"} onClick={() => shift(1)}><ChevronRight /></Button>
    <Button size="sm" onClick={() => onChange(current)} disabled={current === value}>Текущий</Button>
  </div>;
}
