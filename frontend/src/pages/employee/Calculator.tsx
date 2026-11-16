import { Calculator, CalendarDays, Clock3 } from "lucide-react";
import { useState } from "react";

import type { DayCell, EmployeeDetail } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { DayCalculator } from "./calculator/DayCalculator";
import { MonthCalculator } from "./calculator/MonthCalculator";

/** Личная прикидка: расчёты не меняют дейлики, условия сотрудника и начисления. */
export function EmployeeCalculator({ data, today, day }: { data: EmployeeDetail; today: string; day?: DayCell }) {
  const [open, setOpen] = useState(false);
  return <Dialog open={open} onOpenChange={setOpen}>
    <DialogTrigger asChild><Button><Calculator />Калькулятор эффективности</Button></DialogTrigger>
    {open ? <DialogContent title="Калькулятор эффективности" description={data.employee.short_name}
      className="top-[4dvh] max-h-[92dvh] w-[min(94vw,60rem)] overflow-y-auto overscroll-contain p-4 sm:p-6">
      <CalculatorBody data={data} today={today} day={day} />
    </DialogContent> : null}
  </Dialog>;
}

function CalculatorBody({ data, today, day }: { data: EmployeeDetail; today: string; day?: DayCell }) {
  const [tab, setTab] = useState("day");
  const [monthVisited, setMonthVisited] = useState(false);
  const [efficiency, setEfficiency] = useState<number | undefined>();
  const [suggestionId, setSuggestionId] = useState(0);
  const openMonth = (value?: number) => {
    if (value !== undefined) { setEfficiency(value); setSuggestionId((id) => id + 1); }
    setMonthVisited(true);
    setTab("month");
  };
  return <Tabs value={tab} onValueChange={(value) => value === "month" ? openMonth() : setTab(value)}>
    <TabsList className="mb-5 grid w-full grid-cols-2" aria-label="Режим калькулятора">
      <TabsTrigger value="day" className="flex justify-center gap-2 px-1 text-[12px] sm:text-[13px]"><Clock3 className="size-4 shrink-0" />Эффективность дня</TabsTrigger>
      <TabsTrigger value="month" className="flex justify-center gap-2 px-1 text-[12px] sm:text-[13px]"><CalendarDays className="size-4 shrink-0" />Доход за месяц</TabsTrigger>
    </TabsList>
    <TabsContent value="day" forceMount hidden={tab !== "day"}><DayCalculator day={day} onMonth={openMonth} /></TabsContent>
    <TabsContent value="month" forceMount hidden={tab !== "month"}>
      {monthVisited ? <MonthCalculator data={data} today={today} suggestedEfficiency={efficiency} suggestionId={suggestionId} /> : null}
    </TabsContent>
    <p className="mt-5 border-t border-line pt-3 text-[12px] text-ink-3">Расчёт для себя. Дейлики, расписание и начисления остаются без изменений.</p>
  </Tabs>;
}
