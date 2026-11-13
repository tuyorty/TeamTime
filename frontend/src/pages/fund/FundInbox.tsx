import { useState } from "react";
import { useFundOverview, useTeamSession } from "@/api/fund";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/domain/feedback";
import { money } from "@/lib/format";
import { FundForm } from "./FundForm";
import { decisionForm, type FormSpec } from "./formTypes";
import { FundReviews } from "./FundReviews";
import { Card, Empty } from "./shared";

export function FundInbox() {
  const session = useTeamSession();
  const data = useFundOverview(!!session.data?.actor?.leader);
  const [form, setForm] = useState<FormSpec>();
  if (!session.data?.actor?.leader)
    return <Empty>Для согласования нужен вход руководителя фонда</Empty>;
  if (data.error)
    return (
      <ErrorState error={data.error} onRetry={() => void data.refetch()} />
    );
  if (!data.data) return <Empty>Загрузка заявок…</Empty>;
  const pending = data.data.claims.filter((c) => c.state === "pending");
  return (
    <div className="grid gap-4">
      <Card>
        <h2 className="font-semibold">Расходы на согласовании</h2>
        {pending.map((c) => (
          <div
            key={c.id}
            className="mt-4 flex flex-wrap justify-between gap-3 border-b border-line pb-4"
          >
            <div>
              <strong className="text-sm">
                {
                  data.data!.members.find((m) => m.id === c.employee_id)
                    ?.short_name
                }{" "}
                · {money(c.amount)}
              </strong>
              <p className="mt-1 text-sm text-ink-2">{c.title}</p>
            </div>
            <div className="flex gap-2">
              <Button
                onClick={() =>
                  setForm(
                    decisionForm(
                      `/fund/claims/${c.id}/decide`,
                      "Одобрить компенсацию",
                      true,
                    ),
                  )
                }
              >
                Одобрить
              </Button>
              <Button
                onClick={() =>
                  setForm(
                    decisionForm(
                      `/fund/claims/${c.id}/decide`,
                      "Отклонить компенсацию",
                      false,
                    ),
                  )
                }
              >
                Отклонить
              </Button>
            </div>
          </div>
        ))}
        {!pending.length && <Empty>Новых расходов нет</Empty>}
      </Card>
      <FundReviews
        data={{
          ...data.data,
          requests: data.data.requests.filter((r) => r.state === "pending"),
          adjustments: data.data.adjustments.filter(
            (a) => a.state === "pending",
          ),
        }}
        actor={session.data.actor}
        onForm={setForm}
      />
      {form && <FundForm spec={form} onClose={() => setForm(undefined)} />}
    </div>
  );
}
