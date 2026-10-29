import { AtSign, BriefcaseBusiness, CalendarDays, Clock3, Pencil, Phone } from "lucide-react";
import { Link } from "react-router";

import { useMeta, useToday } from "@/api/queries";
import type { EmployeeDetail } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { TaskList } from "@/components/domain/TaskList";
import { STATUS } from "@/components/domain/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { clock, dayMonth, hm } from "@/lib/format";

export function EmployeeProfile({ data }: { data: EmployeeDetail }) {
  const { data: meta } = useMeta();
  const today = useToday().data;
  const employee = data.employee;
  const row = today?.rows.find((value) => value.employee.id === employee.id);
  const plan = row?.cell.plan;
  const status = row?.cell.status;
  const dayLabel = status
    ? STATUS[status].label
    : row?.presence === "off"
      ? "Выходной"
      : row?.presence === "no_plan"
        ? "Расписание не указано"
        : row?.presence === "expected_later"
          ? "Начнёт позже"
          : row?.presence === "left"
            ? "Рабочий день завершён"
            : row?.presence === "on_site"
              ? "В офисе по расписанию"
              : "";

  return (
    <section aria-label="Профиль сотрудника" className="overflow-hidden rounded-lg border border-line bg-surface">
      <div className="h-1.5 bg-accent/60" />
      <header className="flex flex-wrap items-center gap-4 p-5 sm:p-6">
        <Avatar employee={employee} size={80} />
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-[26px] font-semibold leading-tight tracking-tight sm:text-[30px]">
            {employee.full_name}
          </h1>
          <p className="mt-2 flex items-center gap-1.5 text-[13px] text-ink-2">
            <BriefcaseBusiness className="size-3.5" />
            {employee.position || "Должность не указана"}
          </p>
          {!employee.is_active ? <Badge className="mt-2">Неактивный сотрудник</Badge> : null}
        </div>
        {meta?.is_admin ? (
          <Button asChild size="sm">
            <Link to={`/admin/employees?edit=${employee.id}`}>
              <Pencil /> Редактировать профиль
            </Link>
          </Button>
        ) : null}
      </header>
      <div className="grid border-t border-line md:grid-cols-3">
        <div className="grid content-start gap-3 p-5 md:border-r md:border-line">
          <h2 className="text-[12px] font-medium text-ink-3">Контакты</h2>
          {data.identities.length ? (
            data.identities.map((identity) => (
              <a
                key={identity.id}
                href={
                  identity.username
                    ? `https://t.me/${encodeURIComponent(identity.username)}`
                    : `tg://user?id=${identity.telegram_user_id}`
                }
                target="_blank"
                rel="noreferrer"
                className="flex w-fit items-center gap-2 break-all text-[13px] text-accent-ink hover:underline"
              >
                <AtSign className="size-4 shrink-0" />
                {identity.username ? `@${identity.username}` : identity.display_name || "Написать в Telegram"}
              </a>
            ))
          ) : (
            <span className="flex items-center gap-2 text-[13px] text-ink-3">
              <AtSign className="size-4" /> Telegram не привязан
            </span>
          )}
          {employee.phone ? (
            <a
              href={`tel:${employee.phone.replace(/[^+\d]/g, "")}`}
              className="flex w-fit items-center gap-2 text-[13px] hover:text-accent-ink"
            >
              <Phone className="size-4 text-ink-3" />
              {employee.phone}
            </a>
          ) : (
            <span className="flex items-center gap-2 text-[13px] text-ink-3">
              <Phone className="size-4" /> Телефон не указан
            </span>
          )}
        </div>
        <div className="grid content-start gap-3 border-t border-line p-5 md:border-t-0 md:border-r">
          <h2 className="flex items-center gap-1.5 text-[12px] font-medium text-ink-3">
            <CalendarDays className="size-3.5" /> Сегодня{today ? `, ${dayMonth(today.date)}` : ""}
          </h2>
          <p className="text-[14px] font-medium">
            {!employee.is_active
              ? "Не участвует в текущем расписании"
              : dayLabel || (today ? "Нет расписания на сегодня" : "Загружаем расписание…")}
          </p>
          {plan?.kind === "work" && !["absent", "off"].includes(row!.presence) ? (
            <p className="flex items-center gap-1.5 text-[13px] tnum">
              <Clock3 className="size-3.5 text-ink-3" />
              {plan.intervals.map(([start, end]) => `${clock(start)}–${clock(end)}`).join(" · ")}
            </p>
          ) : null}
          {row?.cell.status_note || plan?.note ? (
            <p className="text-[12px] text-ink-2">{row?.cell.status_note || plan?.note}</p>
          ) : null}
        </div>
        <div className="grid content-start gap-3 border-t border-line p-5 md:border-t-0">
          <h2 className="text-[12px] font-medium text-ink-3">О сотруднике</h2>
          <p className="whitespace-pre-wrap break-words text-[13px] text-ink-2">
            {employee.about || "Описание не добавлено."}
          </p>
          <p className="text-[12px] text-ink-3">
            Норма: <span className="font-medium text-ink-2 tnum">{hm(employee.monthly_norm_minutes * 60)} в месяц</span>
          </p>
        </div>
      </div>
      {row?.tasks?.length ? (
        <div className="border-t border-line p-5">
          <h2 className="mb-3 text-[13px] font-semibold">Задачи из расписания на эту неделю</h2>
          <TaskList key={employee.id} tasks={row.tasks} columns={2} label="Задачи сотрудника на неделю" />
        </div>
      ) : null}
    </section>
  );
}
