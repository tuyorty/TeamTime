import { Check, CheckCheck, EyeOff, Inbox, Link2, Pencil, RotateCw } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { api } from "@/api/client";
import { useAdminMutation, useEmployees, useIdentities, useInbox } from "@/api/queries";
import type { InboxItem, Issue } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { EmptyState, ErrorState } from "@/components/domain/feedback";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/field";
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

const RESOLUTION = { accepted: "принято как есть", fixed: "исправлено", ignored: "не учитывается", auto: "разобрано", pending: "ждёт" };

export default function InboxPage() {
  const [search, setSearch] = useSearchParams();
  const view = search.get("view") ?? "pending";
  const { data, error, refetch } = useInbox(view);
  const counts = useInbox("pending").data?.counts;

  return (
    <div className="grid gap-5">
      <PageHeader
        title="Инбокс"
        subtitle="Сообщения, в которых бот сомневается: непонятные строки, не найден сотрудник, нет эффективности"
      />
      <Tabs value={view} onValueChange={(v) => setSearch({ view: v })}>
        <TabsList>
          {VIEWS.map((v) => (
            <TabsTrigger key={v.value} value={v.value}>
              {v.label}
              {counts ? <span className="ml-1.5 text-ink-3 tnum">{counts[v.value] ?? 0}</span> : null}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      {error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : !data ? (
        <div className="grid gap-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      ) : !data.items.length ? (
        <EmptyState icon={view === "pending" ? CheckCheck : Inbox} title={view === "pending" ? "Всё разобрано" : "Пусто"}>
          {view === "pending"
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
        <dd>{intervals.map(([a, b]) => `${hm(a)}–${hm(b)}`).join("; ")} ({hm(d.worked_sec as number)})</dd>
        <dt className="text-ink-3">Эффективность</dt>
        <dd>{d.efficiency !== null ? `${d.efficiency as number}%` : <span className="text-deviation-ink">не указана</span>}</dd>
      </dl>
    );
  }
  const person = d.person as { raw: string } | null;
  return (
    <dl className="grid grid-cols-[8.5rem_1fr] gap-x-3 gap-y-1 text-[13px] tnum">
      <dt className="text-ink-3">Неделя</dt>
      <dd>{d.iso_week as number}-я, {dayMonth(d.sprint_start as string)} – {dayMonth(d.sprint_end as string)}</dd>
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
        <pre className="overflow-x-auto rounded-md border border-line bg-bg p-3 font-sans text-[13px] leading-[1.55] whitespace-pre-wrap">
          {text.split("\n").map((line, n) => {
            const issues = lineIssues.get(n + 1);
            const bad = issues?.some((i) => i.severity !== "info");
            return (
              <span key={n} className={cn("-mx-1 block rounded-sm px-1", issues && (bad ? "bg-late-soft" : "bg-deviation-soft"))}>
                {line || " "}
                {issues ? <span className="ml-2 text-[11px] text-ink-2">← {issues.map((i) => i.message).join("; ")}</span> : null}
              </span>
            );
          })}
        </pre>
        <span className="text-[12px] text-ink-3">
          Отправитель в Telegram: {m.author_name || "неизвестен"}
          {p.resolution !== "pending" ? `, ${RESOLUTION[p.resolution]}` : ""}
        </span>
      </div>
      <div className="grid content-start gap-3">
        {general.length ? (
          <ul className="grid gap-1.5">
            {general.map((i, n) => (
              <li key={n} className="flex items-start gap-2 text-[13px]">
                <Badge tone={issueTone(i)}>{i.severity === "error" ? "ошибка" : i.severity === "warning" ? "вопрос" : "заметка"}</Badge>
                <span className="text-ink-2">{i.message}</span>
              </li>
            ))}
          </ul>
        ) : null}
        <Summary item={item} />
        {p.employee_unresolved ? <LinkIdentity item={item} /> : null}
        {admin ? (
          <div className="mt-1 flex flex-wrap gap-2">
            {fixHref ? (
              <Button asChild size="sm" variant="primary">
                <Link to={fixHref} title="Открыть этот день в табеле и вручную поправить время и e%. Правка пишется в аудит.">
                  <Pencil /> Исправить в табеле
                </Link>
              </Button>
            ) : null}
            {p.resolution === "pending" && d && !p.employee_unresolved ? (
              <Button
                size="sm"
                title="Данные уже учтены. Убрать запись из инбокса, ничего не меняя."
                onClick={() => resolve.mutate("accepted")}
                disabled={resolve.isPending}
              >
                <Check /> Принять как есть
              </Button>
            ) : null}
            {p.resolution === "pending" ? (
              <Button
                size="sm"
                variant="ghost"
                title="Это не дейлик и не расписание. Убрать из инбокса; данные из сообщения не учитываются."
                onClick={() => resolve.mutate("ignored")}
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
              «Исправить в табеле» — поправить цифры дня вручную. «Принять как есть» — данные верны, убрать из инбокса.
              «Переразобрать» — прочитать сообщение заново, если бот обновился или в справочнике появился сотрудник.
            </p>
          </div>
        ) : (
          <p className="text-[12px] text-ink-3">Исправить, принять или игнорировать можно в режиме админа.</p>
        )}
      </div>
    </li>
  );
}

function LinkIdentity({ item }: { item: InboxItem }) {
  const admin = useIsAdmin();
  const person = item.parse.kind === "schedule" ? ((item.parse.data as { person?: { raw: string } | null } | null)?.person ?? null) : null;
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
          <Select className="w-56" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)} aria-label="Сотрудник для привязки">
            <option value="">Выберите сотрудника</option>
            {employees.map((e) => (
              <option key={e.id} value={e.id}>
                {e.short_name}
              </option>
            ))}
          </Select>
          <Button size="sm" variant="primary" disabled={!employeeId || link.isPending} onClick={() => link.mutate(undefined)}>
            Привязать аккаунт
          </Button>
        </div>
      ) : (
        <p className="text-ink-3">После привязки аккаунта бот переразберёт все его сообщения.</p>
      )}
    </div>
  );
}
