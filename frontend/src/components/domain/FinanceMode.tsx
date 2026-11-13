import { Settings2 } from "lucide-react";
import { useState } from "react";
import { api } from "@/api/client";
import { useTeamSession } from "@/api/fund";
import { useAdminMutation } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Panel } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { cn } from "@/lib/cn";
import { ErrorState } from "./feedback";

export function FinanceModePanel() {
  const session = useTeamSession();
  const [choice, setChoice] = useState<boolean | null>(null);
  const current = session.data?.module_enabled ?? false;
  const selected = choice ?? current;
  const save = useAdminMutation(
    () => api.put("/admin/finance-module", { module_enabled: selected, expected_enabled: current }),
    { success: () => selected ? "Модуль фонда включён" : "Включены обычные финансы" },
  );
  if (session.error) return <ErrorState error={session.error} onRetry={() => void session.refetch()} />;
  if (!session.data) return <Skeleton className="h-48" />;
  if (!session.data.module_available) return (
    <Panel title="Режим финансов" description="Обычные финансы активны для всей команды">
      <p className="mt-2 text-sm font-semibold">Модуль фонда — в разработке</p>
      <p className="mt-2 text-sm leading-relaxed text-ink-2">
        Пока используются оклад, переработки и проектные премии. Расчёты, операции и напоминания
        фонда недоступны до завершения доработок. Ранее введённые данные фонда сохранены.
      </p>
    </Panel>
  );
  return (
    <Panel title="Режим финансов" description="Общая настройка для всей команды">
      <div role="radiogroup" aria-label="Режим финансов" className="mt-2 grid gap-3 sm:grid-cols-2">
        {[
          { value: false, title: "Обычные финансы", text: "Оклад по норме и часовой ставке, переработки, проектные премии и графики начислений." },
          { value: true, title: "Модуль фонда", text: "Целевые суммы, источники выплат, счета фонда, расходы, компенсации, займы и закрытие месяцев." },
        ].map((option) => (
          <button key={String(option.value)} type="button" role="radio" aria-checked={selected === option.value}
            disabled={save.isPending} onClick={() => setChoice(option.value)}
            className={cn("rounded-lg border p-4 text-left", selected === option.value ? "border-accent bg-accent-soft" : "border-line hover:bg-surface-2")}>
            <span className="block text-sm font-semibold">{option.title}</span>
            <span className="mt-1 block text-xs leading-relaxed text-ink-2">{option.text}</span>
          </button>
        ))}
      </div>
      <p className="mt-3 text-xs leading-relaxed text-ink-2">
        При отключении фонда его данные и закрытые месяцы сохраняются. Действия и напоминания фонда в боте отключаются.
        Уже включённый именной вход и резервное копирование продолжают работать.
      </p>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <span className="text-xs text-ink-2">Сейчас: {current ? "модуль фонда" : "обычные финансы"}</span>
        <Button variant="primary" disabled={save.isPending || selected === current} onClick={() => save.mutate(undefined)}>
          {save.isPending ? "Сохраняем…" : "Применить режим"}
        </Button>
      </div>
    </Panel>
  );
}

export function FinanceModeButton() {
  const admin = useIsAdmin();
  const available = useTeamSession().data?.module_available;
  const [open, setOpen] = useState(false);
  if (!admin || !available) return null;
  return <>
    <Button onClick={() => setOpen(true)}><Settings2 /> Режим финансов</Button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent title="Выбор финансового модуля" className="max-h-[80vh] overflow-y-auto sm:w-[min(92vw,42rem)]"><FinanceModePanel /></DialogContent>
    </Dialog>
  </>;
}
