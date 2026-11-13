import { Link } from "react-router";
import type { FundOverview, TeamActor } from "@/api/fund";
import { Button } from "@/components/ui/button";
import { reasonField, type FormSpec } from "./formTypes";
import { dateLabel } from "./format";
import { Card } from "./shared";

export function FundClosedChanges({
  data,
  actor,
  onForm,
}: {
  data: FundOverview;
  actor: TeamActor;
  onForm: (spec: FormSpec) => void;
}) {
  if (!actor.leader || !data.closed_changes.length) return null;
  return (
    <Card className="xl:col-span-2">
      <h2 className="font-semibold">Изменились исходники закрытого месяца</h2>
      <p className="mt-1 text-sm text-ink-2">
        Дейлик, расписание или статус изменены после закрытия. Проверьте влияние
        на начисление: сохранённый расчёт остаётся прежним до согласования
        корректировки.
      </p>
      <div className="mt-4 max-h-80 space-y-3 overflow-y-auto">
        {data.closed_changes.map((change) => {
          const [year, month] = change.month.split("-");
          return (
            <div
              key={change.event_id}
              className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3"
            >
              <div>
                <strong className="text-sm">
                  {
                    data.members.find((m) => m.id === change.employee_id)
                      ?.full_name
                  }
                </strong>
                <p className="text-xs text-ink-3">
                  Месяц {month}.{year} · изменение{" "}
                  {dateLabel(change.created_at.slice(0, 10))}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Link
                  className="text-sm text-accent hover:underline"
                  to={`/finances/${year}/${Number(month)}?fund=1&employee=${change.employee_id}`}
                >
                  Открыть расчёт
                </Link>
                <Button
                  size="sm"
                  onClick={() =>
                    onForm({
                      title: "Завершить проверку исходников",
                      description:
                        "Укажите результат проверки. Если начисление меняется, сначала согласуйте корректировку в карточке расчёта. Эта отметка сама суммы не меняет.",
                      path: `/fund/closed-changes/${change.event_id}/review`,
                      fields: [reasonField],
                      body: (values) => ({ reason: values.reason }),
                    })
                  }
                >
                  Проверено
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
