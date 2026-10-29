import { Check, CheckCheck, EyeOff, Inbox, Link2, Pencil, RotateCw, X } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { api } from "@/api/client";
import { useAdminMutation, useEmployees, useIdentities, useInbox } from "@/api/queries";
import type { InboxItem, Issue } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { ScheduleComparison } from "@/components/domain/ScheduleComparison";
import { EmptyState, ErrorState } from "@/components/domain/feedback";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Select } from "@/components/ui/field";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { cn } from "@/lib/cn";
import { dayMonth, hm, isoWeek, parseDate, relative } from "@/lib/format";

const VIEWS = [
  { value: "pending", label: "Ждут решения" },
  { value: "resolved", label: "Решённые" },
  { value: "auto", label: "Разобраны сами" },
] as const;

const PROBLEMS = [
  { value: "", label: "Все" },
  { value: "failed", label: "Не разобрано" },
  { value: "partial", label: "С вопросами" },
  { value: "unlinked", label: "Без сотрудника" },
] as const;

const KINDS = [
  { value: "", label: "Все типы" },
  { value: "daily", label: "Дейлики" },
  { value: "schedule", label: "Расписания" },
] as const;

const FILTER_KEYS = ["employee", "problem", "kind"] as const;

const RESOLUTION = {
  accepted: "принято как есть",
  fixed: "исправлено",
  ignored: "не учитывается",
  auto: "разобрано",
  pending: "ждёт",
};

export default function InboxPage() {
  const [search, setSearch] = useSearchParams();
  const view = search.get("view") ?? "pending";
  const filter = new URLSearchParams(
    FILTER_KEYS.flatMap((k) => (search.get(k) ? [[k, search.get(k)!]] : [])),
  ).toString();
  const { data, error, refetch } = useInbox(view, filter);
  const counts = useInbox("pending").data?.counts;
  const admin = useIsAdmin();
  const employees = useEmployees().data ?? [];
  const reparseAll = useAdminMutation(() => api.post<{ detail: string }>("/admin/inbox/reparse"), {
    success: (r) => `Переразобрано, ушло из инбокса: ${r.detail}`,
  });

  function setParam(key: (typeof FILTER_KEYS)[number] | "view", value: string) {
    const next = new URLSearchParams(search);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearch(next, { replace: true });
  }

  return (
    <div className="grid gap-5">
      <PageHeader
        title="Инбокс"
        subtitle="Сообщения, в которых бот сомневается: непонятные строки, не найден сотрудник, нет эффективности"
      />
      <Tabs value={view} onValueChange={(v) => setParam("view", v)}>
        <TabsList>
          {VIEWS.map((v) => (
            <TabsTrigger key={v.value} value={v.value}>
              {v.label}
              {counts ? <span className="ml-1.5 text-ink-3 tnum">{counts[v.value] ?? 0}</span> : null}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      <div className="flex flex-wrap items-center gap-2">
        <Select
          aria-label="Сотрудник"
          className="w-full sm:w-52"
          value={search.get("employee") ?? ""}
          onChange={(e) => setParam("employee", e.target.value)}
        >
          <option value="">Все сотрудники</option>
          <option value="none">Сотрудник не определён</option>
          {employees.map((e) => (
            <option key={e.id} value={e.id}>
              {e.short_name}
            </option>
          ))}
        </Select>
        <Segmented
          label="Проблема"
          value={search.get("problem") ?? ""}
          onChange={(v) => setParam("problem", v)}
          options={PROBLEMS.map((p) => ({ value: p.value, label: p.label }))}
        />
        <Select
          aria-label="Тип сообщения"
          className="w-full sm:w-36"
          value={search.get("kind") ?? ""}
          onChange={(e) => setParam("kind", e.target.value)}
        >
          {KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </Select>
        {filter ? (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              const next = new URLSearchParams(search);
              FILTER_KEYS.forEach((k) => next.delete(k));
              setSearch(next, { replace: true });
            }}
          >
            <X /> Сбросить
          </Button>
        ) : null}
        <span className="text-[12px] text-ink-3 tnum">
          {data
            ? data.total > data.items.length
              ? `Показано ${data.items.length} из ${data.total}`
              : `Найдено: ${data.total}`
            : null}
        </span>
        {admin && view === "pending" ? (
          <Button
            size="sm"
            variant="ghost"
            className="sm:ml-auto"
            title="Прочитать заново все сообщения, которые ждут решения: после обновления бота, добавления сотрудников или привязки аккаунтов."
            onClick={() => reparseAll.mutate(undefined)}
            disabled={reparseAll.isPending}
          >
            <RotateCw className={cn(reparseAll.isPending && "animate-spin")} />{" "}
            {reparseAll.isPending ? "Переразбираем…" : "Переразобрать всё"}
          </Button>
        ) : null}
      </div>
      {error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : !data ? (
        <div className="grid gap-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      ) : !data.items.length ? (
        <EmptyState
          icon={view === "pending" && !filter ? CheckCheck : Inbox}
          title={filter ? "Ничего не найдено" : view === "pending" ? "Всё разобрано" : "Пусто"}
        >
          {filter
            ? "Под эти фильтры ничего не подходит."
            : view === "pending"
              ? "Бот понял все сообщения. Новые вопросы появятся здесь сами."
              : "Здесь будут записи, когда они появятся."}
        </EmptyState>
      ) : (
        <ul className="grid gap-3">
          {data.items.map((item) => (
            <InboxCard key={item.parse.id} item={item} />
          ))}
        </ul>
      )}
    </div>
  );
}

function issueTone(i: Issue) {
  return i.severity === "error" ? "late" : i.severity === "warning" ? "deviation" : "neutral";
}

function Summary({ item }: { item: InboxItem }) {
  const d = item.parse.data as Record<string, unknown> | null;
  if (!d) return <p className="text-[13px] text-ink-2">Ничего не удалось извлечь.</p>;
  if (item.parse.kind === "daily") {
    const intervals = d.intervals as [number, number][];
    return (
      <dl className="grid grid-cols-[8.5rem_1fr] gap-x-3 gap-y-1 text-[13px] tnum">
        <dt className="text-ink-3">Дата</dt>
        <dd>{dayMonth(d.work_date as string)}</dd>
        <dt className="text-ink-3">Время</dt>
        <dd>
          {intervals.map(([a, b]) => `${hm(a)}–${hm(b)}`).join("; ")} ({hm(d.worked_sec as number)})
        </dd>
        <dt className="text-ink-3">Эффективность</dt>
        <dd>
          {d.efficiency !== null ? (
            `${d.efficiency as number}%`
          ) : (
            <span className="text-deviation-ink">не указана</span>
          )}
        </dd>
      </dl>
    );
  }
  const person = d.person as { raw: string } | null;
  return (
    <dl className="grid grid-cols-[8.5rem_1fr] gap-x-3 gap-y-1 text-[13px] tnum">
      <dt className="text-ink-3">Неделя</dt>
      <dd>
        {d.iso_week as number}-я, {dayMonth(d.sprint_start as string)} – {dayMonth(d.sprint_end as string)}
      </dd>
      <dt className="text-ink-3">Сотрудник</dt>
      <dd>{person?.raw ?? <span className="text-deviation-ink">не указан</span>}</dd>
      <dt className="text-ink-3">Дней в плане</dt>
      <dd>{(d.days as unknown[]).length}</dd>
    </dl>
  );
}

function InboxCard({ item }: { item: InboxItem }) {
  const admin = useIsAdmin();
  const p = item.parse;
  const m = item.message;
  const [decision, setDecision] = useState<"approve" | "ignore" | null>(null);
  const lateSchedule = p.kind === "schedule" && p.issues.some((issue) => issue.code === "late_change");
  const text = m.versions.find((v) => v.id === p.message_version_id)?.text ?? m.versions.at(-1)!.text;
  const lineIssues = new Map<number, Issue[]>();
  for (const i of p.issues) if (i.line_no) lineIssues.set(i.line_no, [...(lineIssues.get(i.line_no) ?? []), i]);
  const general = p.issues.filter((i) => !i.line_no);

  const resolve = useAdminMutation((resolution: string) => api.post(`/admin/inbox/${p.id}/resolve`, { resolution }), {
    success: "Готово",
  });
  const reparse = useAdminMutation(() => api.post<{ detail: string }>(`/admin/inbox/${p.id}/reparse`), {
    success: "Переразобрано текущим парсером",
  });

  const d = p.data as Record<string, unknown> | null;
  const fixHref =
    p.kind === "daily" && d && p.employee
      ? (() => {
          const w = isoWeek(parseDate(d.work_date as string));
          return `/week/${w.year}/${w.week}?day=${d.work_date as string}&e=${p.employee.id}`;
        })()
      : null;

  return (
    <li className="grid gap-4 rounded-lg border border-line bg-surface p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="grid content-start gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {p.employee ? <Avatar employee={p.employee} size={22} /> : null}
          <span className="text-[14px] font-semibold">{p.employee?.short_name ?? m.author_name}</span>
          <Badge tone="outline">{p.kind === "daily" ? "дейлик" : "расписание"}</Badge>
          <Badge tone={p.status === "failed" ? "late" : p.status === "partial" ? "deviation" : "accent"}>
            {p.status === "failed" ? "не разобрано" : p.status === "partial" ? "с вопросами" : "разобрано"}
          </Badge>
          {p.version > 1 ? <Badge>правка {p.version - 1}</Badge> : null}
          <span className="ml-auto text-[12px] text-ink-3">{relative(m.versions.at(-1)!.edited_at ?? m.sent_at)}</span>
        </div>
        <pre className="max-h-[28rem] overflow-auto rounded-md border border-line bg-bg p-3 font-sans text-[13px] leading-[1.55] whitespace-pre-wrap [overflow-wrap:anywhere]">
          {text.split("\n").map((line, n) => {
            const issues = lineIssues.get(n + 1);
            const bad = issues?.some((i) => i.severity !== "info");
            return (
              <span
                key={n}
                className={cn("-mx-1 block rounded-sm px-1", issues && (bad ? "bg-late-soft" : "bg-deviation-soft"))}
              >
                {line || " "}
                {issues ? (
                  <span className="ml-2 text-[11px] text-ink-2">← {issues.map((i) => i.message).join("; ")}</span>
                ) : null}
              </span>
            );
          })}
        </pre>
        {p.resolution !== "pending" ? (
          <span className="text-[12px] text-ink-3">Решение: {RESOLUTION[p.resolution]}</span>
        ) : null}
      </div>
      <div className="grid content-start gap-3">
        {general.length ? (
          <ul className="grid gap-1.5">
            {general.map((i, n) => (
              <li key={n} className="flex items-start gap-2 text-[13px]">
                <Badge tone={issueTone(i)}>
                  {i.severity === "error" ? "ошибка" : i.severity === "warning" ? "вопрос" : "заметка"}
                </Badge>
                <span className="text-ink-2">{i.message}</span>
              </li>
            ))}
          </ul>
        ) : null}
        <Summary item={item} />
        {item.plan_change ? (
          <ScheduleComparison preview={item.plan_change} pending={p.resolution === "pending"} />
        ) : null}
        {lateSchedule && p.resolution === "pending" ? (
          <p className="rounded-md border border-deviation/30 bg-deviation-soft/40 p-3 text-[12px] leading-relaxed text-ink-2">
            Это предупреждение о позднем изменении расписания. Одобрение применит новый план и пересчитает опоздания и
            итоги. Фактическое время останется из дейлика.
          </p>
        ) : null}
        {p.employee_unresolved ? <LinkIdentity item={item} /> : null}
        {admin ? (
          <div className="mt-1 flex flex-wrap gap-2">
            {fixHref ? (
              <Button asChild size="sm" variant="primary">
                <Link
                  to={fixHref}
                  title="Открыть этот день в таблице и вручную поправить время и e%. Правка пишется в аудит, а запись закрывается как исправленная."
                >
                  <Pencil /> Исправить в таблице
                </Link>
              </Button>
            ) : null}
            {p.resolution === "pending" && d && !p.employee_unresolved ? (
              <Button
                size="sm"
                title={
                  lateSchedule
                    ? "Одобрить новый план после проверки изменений и пересчёта опозданий."
                    : "Подтвердить разбор сообщения и убрать запись из инбокса."
                }
                onClick={() => (lateSchedule ? setDecision("approve") : resolve.mutate("accepted"))}
                disabled={resolve.isPending}
              >
                <Check /> {lateSchedule ? "Одобрить новый план" : "Принять как есть"}
              </Button>
            ) : null}
            {p.resolution === "pending" ? (
              <Button
                size="sm"
                variant="ghost"
                title="Это не дейлик и не расписание. Убрать из инбокса; данные из сообщения не учитываются."
                onClick={() => setDecision("ignore")}
                disabled={resolve.isPending}
              >
                <EyeOff /> Игнорировать
              </Button>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => resolve.mutate("pending")} disabled={resolve.isPending}>
                Вернуть в инбокс
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              title="Разобрать исходное сообщение заново текущей версией бота: после обновления парсера, добавления сотрудника или привязки аккаунта."
              onClick={() => reparse.mutate()}
              disabled={reparse.isPending}
            >
              <RotateCw /> Переразобрать
            </Button>
            <p className="basis-full text-[12px] leading-snug text-ink-3">
              {lateSchedule
                ? "«Одобрить новый план» — применить показанные изменения и пересчитать таблицу. «Игнорировать» — исключить данные этого сообщения из расчётов."
                : "«Исправить в таблице» — поправить цифры дня вручную. «Принять как есть» — подтвердить разбор и закрыть вопрос."}{" "}
              «Переразобрать» — прочитать сообщение заново, если бот обновился или в справочнике появился сотрудник.
            </p>
          </div>
        ) : (
          <p className="text-[12px] text-ink-3">Исправить, принять или игнорировать можно в режиме админа.</p>
        )}
      </div>
      <Dialog open={decision !== null} onOpenChange={(open) => !open && setDecision(null)}>
        <DialogContent
          title={decision === "approve" ? "Одобрить новое расписание?" : "Исключить сообщение из расчётов?"}
          className="top-[5vh] max-h-[90dvh] w-[min(94vw,42rem)] overflow-y-auto"
        >
          {decision === "approve" ? (
            <>
              <p className="mb-4 text-[13px] leading-relaxed text-ink-2">
                Новый план будет применён к этой версии расписания. Опоздания и итоги пересчитаются — при переносе
                начала позже опоздание может уменьшиться или исчезнуть. Фактические интервалы берутся из дейлика.
              </p>
              {item.plan_change ? (
                <ScheduleComparison preview={item.plan_change} />
              ) : (
                <p className="text-[13px] text-deviation-ink">
                  Сравнение недоступно. Проверьте исходное сообщение и версии в разделе «Планы».
                </p>
              )}
            </>
          ) : (
            <p className="text-[13px] leading-relaxed text-ink-2">
              Производные планы или дейлики из этого сообщения будут отозваны. Предыдущая версия того же сообщения
              автоматически не восстанавливается. Для точечного изменения откройте день в таблице.
            </p>
          )}
          <div className="mt-5 flex flex-wrap justify-end gap-2">
            <Button variant="ghost" onClick={() => setDecision(null)}>
              Отмена
            </Button>
            <Button
              variant={decision === "approve" ? "primary" : "danger"}
              disabled={resolve.isPending || (decision === "approve" && !item.plan_change)}
              onClick={() =>
                resolve.mutate(decision === "approve" ? "accepted" : "ignored", { onSuccess: () => setDecision(null) })
              }
            >
              {decision === "approve" ? "Одобрить и пересчитать" : "Исключить сообщение"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </li>
  );
}

function LinkIdentity({ item }: { item: InboxItem }) {
  const admin = useIsAdmin();
  const person =
    item.parse.kind === "schedule"
      ? ((item.parse.data as { person?: { raw: string } | null } | null)?.person ?? null)
      : null;
  const identities = useIdentities().data ?? [];
  const employees = useEmployees().data ?? [];
  const identity = identities.find((i) => i.telegram_user_id === item.message.author_tg_id);
  const suggested = item.candidates[0]?.id ?? identity?.suggested_employee?.id;
  const [employeeId, setEmployeeId] = useState<string>(suggested ? String(suggested) : "");
  const link = useAdminMutation(
    () => api.put<{ detail: string }>(`/admin/identities/${identity!.id}`, { employee_id: Number(employeeId) }),
    { success: (r) => `Аккаунт привязан. ${r.detail}` },
  );
  return (
    <div className="grid gap-2 rounded-md bg-deviation-soft/60 p-3 text-[13px]">
      <p className="flex items-center gap-1.5 font-medium text-deviation-ink">
        <Link2 className="size-4" /> Сотрудник не определён
      </p>
      {item.candidates.length ? (
        <p className="text-ink-2">Похожие по фамилии: {item.candidates.map((c) => c.short_name).join(", ")}</p>
      ) : identity?.suggested_employee ? (
        <p className="text-ink-2">Бот предлагает: {identity.suggested_employee.short_name}</p>
      ) : null}
      {person && !item.candidates.length ? (
        <div className="grid gap-2">
          <p className="text-ink-2">
            «{person.raw}» нет в справочнике. Добавьте сотрудника, затем нажмите «Переразобрать».
          </p>
          {admin ? (
            <Button asChild size="sm" variant="primary" className="w-fit">
              <Link to={`/admin/employees?new=${encodeURIComponent(person.raw)}`}>Добавить в справочник</Link>
            </Button>
          ) : null}
        </div>
      ) : admin && identity ? (
        <div className="flex flex-wrap items-center gap-2">
          <Select
            className="w-56"
            value={employeeId}
            onChange={(e) => setEmployeeId(e.target.value)}
            aria-label="Сотрудник для привязки"
          >
            <option value="">Выберите сотрудника</option>
            {employees.map((e) => (
              <option key={e.id} value={e.id}>
                {e.short_name}
              </option>
            ))}
          </Select>
          <Button
            size="sm"
            variant="primary"
            disabled={!employeeId || link.isPending}
            onClick={() => link.mutate(undefined)}
          >
            Привязать аккаунт
          </Button>
        </div>
      ) : (
        <p className="text-ink-3">После привязки аккаунта бот переразберёт все его сообщения.</p>
      )}
    </div>
  );
}
