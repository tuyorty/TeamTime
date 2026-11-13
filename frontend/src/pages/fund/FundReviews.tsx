import type { FundOverview, TeamActor } from "@/api/fund";
import { Button } from "@/components/ui/button";
import { money } from "@/lib/format";
import { decisionForm, reasonField, type FormSpec } from "./formTypes";
import { correctionNames, dateLabel, timeNames } from "./format";
import { Card, Empty, State } from "./shared";
import { FundClosedChanges } from "./FundClosedChanges";

export function FundReviews({
  data,
  actor,
  onForm,
}: {
  data: FundOverview;
  actor: TeamActor;
  onForm: (s: FormSpec) => void;
}) {
  const name = (id: number) => data.members.find((m) => m.id === id)?.full_name;
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <FundClosedChanges data={data} actor={actor} onForm={onForm} />
      <Card>
        <h2 className="font-semibold">Отсутствия и исключения</h2>
        <p className="mt-1 text-xs text-ink-3">
          Отпуска, больничные, командировки и решения по опозданиям
        </p>
        <div className="mt-4 max-h-[32rem] space-y-4 overflow-y-auto">
          {data.requests.map((r) => (
            <div key={r.id} className="border-b border-line pb-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <strong className="text-sm">{name(r.employee_id)}</strong>
                <State value={r.state} />
              </div>
              <p className="mt-2 text-sm">
                {timeNames[r.kind]} · {r.days.map(dateLabel).join(", ")}
              </p>
              <p className="mt-1 text-xs text-ink-2">{r.reason}</p>
              {r.decision_reason && (
                <p className="mt-1 text-xs text-ink-3">
                  Решение: {r.decision_reason}
                </p>
              )}
              {actor.leader && r.state === "pending" && (
                <div className="mt-3 flex gap-2">
                  <Button
                    size="sm"
                    onClick={() =>
                      onForm(
                        decisionForm(
                          `/fund/time-requests/${r.id}/decide`,
                          "Подтвердить запрос",
                          true,
                        ),
                      )
                    }
                  >
                    Подтвердить
                  </Button>
                  <Button
                    size="sm"
                    onClick={() =>
                      onForm(
                        decisionForm(
                          `/fund/time-requests/${r.id}/decide`,
                          "Отклонить запрос",
                          false,
                        ),
                      )
                    }
                  >
                    Отклонить
                  </Button>
                </div>
              )}
              {actor.leader && r.state === "approved" && (
                <Button
                  className="mt-2"
                  size="sm"
                  onClick={() =>
                    onForm({
                      title: "Отменить решение",
                      path: `/fund/time-requests/${r.id}/cancel`,
                      fields: [reasonField],
                      body: (v) => ({ reason: v.reason }),
                    })
                  }
                >
                  Отменить решение
                </Button>
              )}
            </div>
          ))}
          {!data.requests.length && <Empty>Запросов пока нет</Empty>}
        </div>
      </Card>
      <Card>
        <h2 className="font-semibold">Корректировки и премии</h2>
        <p className="mt-1 text-xs text-ink-3">
          Закрытая история сохраняется. Разница учитывается в открытом месяце.
        </p>
        <div className="mt-4 max-h-[32rem] space-y-4 overflow-y-auto">
          {data.adjustments.map((a) => (
            <div key={a.id} className="border-b border-line pb-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <strong className="text-sm">{name(a.employee_id)}</strong>
                <State value={a.state} />
              </div>
              <p className="mt-2 flex justify-between gap-2 text-sm">
                <span>{correctionNames[a.kind]}</span>
                <strong className="tnum">{money(a.amount)}</strong>
              </p>
              <p className="mt-1 text-xs text-ink-3">
                За {a.origin_month.slice(0, 7)} → расчёт{" "}
                {a.applied_month.slice(0, 7)}
              </p>
              <p className="mt-2 text-sm text-ink-2">{a.reason}</p>
              {typeof a.before.amount === "string" &&
                typeof a.after.amount === "string" && (
                  <p className="mt-2 text-sm">
                    Было: {money(a.before.amount)} → станет:{" "}
                    {money(a.after.amount)}
                  </p>
                )}
              {actor.leader && a.state === "pending" && (
                <div className="mt-3 flex gap-2">
                  <Button
                    size="sm"
                    onClick={() =>
                      onForm(
                        decisionForm(
                          `/fund/corrections/${a.id}/decide`,
                          "Подтвердить корректировку",
                          true,
                        ),
                      )
                    }
                  >
                    Подтвердить
                  </Button>
                  <Button
                    size="sm"
                    onClick={() =>
                      onForm(
                        decisionForm(
                          `/fund/corrections/${a.id}/decide`,
                          "Отклонить корректировку",
                          false,
                        ),
                      )
                    }
                  >
                    Отклонить
                  </Button>
                </div>
              )}
            </div>
          ))}
          {!data.adjustments.length && (
            <Empty>Корректировок и премий пока нет</Empty>
          )}
        </div>
      </Card>
    </div>
  );
}
