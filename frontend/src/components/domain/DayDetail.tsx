import { AlarmClock, Pencil } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { api } from "@/api/client";
import { useAdminMutation } from "@/api/queries";
import type { DayCell, EmployeeBrief, StatusKind } from "@/api/types";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/field";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { cn } from "@/lib/cn";
import { clock, hm, humanDay, span } from "@/lib/format";
import { formatIntervals, parseIntervals, totalSeconds } from "@/lib/intervals";

import { Avatar } from "./Avatar";
import { axisFor } from "@/lib/axis";

import { AxisTicks, DayStrip } from "./DayStrip";
import { SourceMessage } from "./SourceMessage";
import { DEVIATION, STATUS } from "./states";

export interface DayRef {
  employee: EmployeeBrief;
  cell: DayCell;
}

export function DayDetailSheet({ value, onClose }: { value: DayRef | null; onClose: () => void }) {
  return (
    <Sheet open={!!value} onOpenChange={(o) => !o && onClose()}>
      {value ? (
        <SheetContent
          title={
            <span className="flex items-center gap-2">
              <Avatar employee={value.employee} size={22} />
              {value.employee.short_name}
            </span>
          }
          subtitle={humanDay(value.cell.date)}
        >
          <DayDetail employee={value.employee} cell={value.cell} />
        </SheetContent>
      ) : null}
    </Sheet>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] gap-3 py-1.5 text-[13px]">
      <dt className="text-ink-3">{label}</dt>
      <dd className="min-w-0 tnum">{children}</dd>
    </div>
  );
}

export function DayDetail({ employee, cell }: { employee: EmployeeBrief; cell: DayCell }) {
  const admin = useIsAdmin();
  const [editing, setEditing] = useState<null | "fact" | "plan" | "status">(null);
  const axis = axisFor([cell]);
  const f = cell.fact;
  const p = cell.plan;

  return (
    <div className="grid gap-6">
      <div className="grid gap-1.5">
        <AxisTicks axis={axis} />
        <DayStrip cell={cell} axis={axis} height={22} />
      </div>

      <dl className="divide-y divide-line">
        <Row label="План">
          {p?.kind === "work" ? (
            <>
              {p.intervals.map(([a, b]) => span(a, b)).join("; ")}{" "}
              <span className="text-ink-3">({hm(p.planned_sec)})</span>
            </>
          ) : p?.kind === "off" ? (
            "выходной"
          ) : p?.kind === "note" ? (
            <span className={cn(p.note_has_time && "rounded-sm bg-deviation-soft px-1 text-deviation-ink")}>
              «{p.note}» <span className="text-ink-3">без плана по времени</span>
            </span>
          ) : (
            <span className="text-ink-3">не указан</span>
          )}
          {cell.flags.includes("plan_late_edit") ? (
            <p className="mt-1 text-[12px] text-deviation-ink">
              Расписание поправили слишком поздно — действует прежний план. Чтобы учесть правку, примите её
              в инбоксе или измените план вручную.
            </p>
          ) : null}
        </Row>
        <Row label="Факт">
          {f ? (
            <>
              {f.intervals.map(([a, b]) => span(a, b)).join("; ")}
              {f.edited ? <Badge className="ml-2">отредактирован</Badge> : null}
              {f.source === "manual" ? <Badge className="ml-2" tone="outline">правка вручную</Badge> : null}
            </>
          ) : cell.state === "pending" ? (
            <span className="text-ink-3">дейлик ещё не пришёл</span>
          ) : cell.state === "missing" ? (
            <span className="text-ink-2">нет дейлика</span>
          ) : (
            <span className="text-ink-3">—</span>
          )}
        </Row>
        {f ? (
          <>
            <Row label="Пришёл / ушёл">
              {clock(f.start)} / {clock(f.end)}
            </Row>
            <Row label="Итог">
              <span className="font-medium">
                {hm(f.worked_sec)} × {f.efficiency ?? "?"}% = {hm(f.result_sec)}
              </span>
              {f.efficiency === null || f.efficiency === undefined ? (
                <span className="ml-2 text-deviation-ink">эффективность не указана</span>
              ) : null}
            </Row>
          </>
        ) : null}
        {cell.status ? (
          <Row label="Статус">
            <Badge tone={STATUS[cell.status].tone === "absence" ? "absence" : "neutral"}>
              {(() => {
                const I = STATUS[cell.status].icon;
                return <I />;
              })()}
              {STATUS[cell.status].label}
            </Badge>
            {cell.status_note ? <span className="ml-2 text-ink-2">{cell.status_note}</span> : null}
          </Row>
        ) : null}
      </dl>

      <Deviations cell={cell} />

      {f?.tasks.length ? (
        <section>
          <h3 className="mb-1.5 text-[13px] font-semibold">Сделано</h3>
          <ul className="grid list-disc gap-1 pl-5 text-[13px] text-ink-2 marker:text-ink-3">
            {f.tasks.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {admin ? (
        <section className="grid gap-3 rounded-lg border border-line p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Pencil className="size-4 text-ink-3" />
            <span className="text-[13px] font-semibold">Правка</span>
            <div className="ml-auto flex flex-wrap gap-1">
              {(["fact", "plan", "status"] as const).map((k) => (
                <Button key={k} size="sm" variant={editing === k ? "primary" : "secondary"} onClick={() => setEditing(editing === k ? null : k)}>
                  {{ fact: "Факт", plan: "План", status: "Статус" }[k]}
                </Button>
              ))}
            </div>
          </div>
          {editing === "fact" ? <FactForm employee={employee} cell={cell} onDone={() => setEditing(null)} /> : null}
          {editing === "plan" ? <PlanForm employee={employee} cell={cell} onDone={() => setEditing(null)} /> : null}
          {editing === "status" ? <StatusForm employee={employee} cell={cell} onDone={() => setEditing(null)} /> : null}
          {!editing ? (
            <p className="text-[12px] text-ink-3">
              Правка создаёт новую версию, исходное сообщение не меняется. Всё пишется в журнал.
            </p>
          ) : null}
        </section>
      ) : null}

      <SourceMessage rawId={cell.source.daily_raw_message_id} title="Дейлик" />
      <SourceMessage rawId={cell.source.plan_raw_message_id} title={`Расписание, версия ${cell.source.plan_version ?? 1}`} />

      <Link to={`/people/${employee.id}`} className="text-[13px] text-accent-ink hover:underline">
        Карточка сотрудника
      </Link>
    </div>
  );
}

function Deviations({ cell }: { cell: DayCell }) {
  const items: { key: keyof typeof DEVIATION; value?: string }[] = [];
  if (cell.late_sec) items.push({ key: "late", value: hm(cell.late_sec) });
  if (cell.early_leave_sec) items.push({ key: "early_leave", value: hm(cell.early_leave_sec) });
  if (cell.undertime_sec) items.push({ key: "undertime", value: hm(cell.undertime_sec) });
  if (cell.state === "missing") items.push({ key: "missing" });
  if (cell.no_plan) items.push({ key: "no_plan" });
  if (!items.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map(({ key, value }) => {
        const d = DEVIATION[key];
        return (
          <Badge key={key} tone={d.tone}>
            <d.icon />
            {d.label}
            {value ? <span className="tnum">{value}</span> : null}
          </Badge>
        );
      })}
      {cell.no_plan ? (
        <p className="w-full text-[12px] text-ink-3">
          Плана со временем не было, поэтому опоздание и недоработка за этот день не считаются.
        </p>
      ) : null}
    </div>
  );
}

function Reason({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <Field label="Причина" hint="Попадёт в журнал правок">
      <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder="Например: согласовано с руководителем" />
    </Field>
  );
}

function path(employee: EmployeeBrief, cell: DayCell, what: string) {
  return `/admin/days/${employee.id}/${cell.date}/${what}`;
}

function FactForm({ employee, cell, onDone }: { employee: EmployeeBrief; cell: DayCell; onDone: () => void }) {
  const [text, setText] = useState(cell.fact ? formatIntervals(cell.fact.intervals) : "");
  const [eff, setEff] = useState(cell.fact?.efficiency?.toString() ?? "");
  const [reason, setReason] = useState("");
  const parsed = parseIntervals(text);
  const save = useAdminMutation(
    () =>
      api.put(path(employee, cell, "fact"), {
        intervals: parsed.intervals,
        efficiency: eff === "" ? null : Number(eff),
        reason,
      }),
    { success: "Факт сохранён новой версией" },
  );
  const clear = useAdminMutation(() => api.delete(`${path(employee, cell, "fact")}?reason=${encodeURIComponent(reason)}`), {
    success: "Дейлик отозван",
  });
  const effError = eff !== "" && (Number(eff) < 0 || Number(eff) > 100 || !Number.isInteger(Number(eff))) ? "От 0 до 100" : null;
  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined, { onSuccess: onDone });
      }}
    >
      <Field
        label="Интервалы"
        error={text && parsed.error ? parsed.error : null}
        hint={!parsed.error ? `Часы: ${hm(totalSeconds(parsed.intervals))}` : "Как в дейлике: 10:00 - 13:00; 14:00 - 18:30"}
      >
        <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="10:00 - 18:00" />
      </Field>
      <Field label="Эффективность, %" error={effError}>
        <Input inputMode="numeric" value={eff} onChange={(e) => setEff(e.target.value)} placeholder="не указана" />
      </Field>
      <Reason value={reason} onChange={setReason} />
      <div className="flex flex-wrap justify-between gap-2">
        {cell.fact ? (
          <Button variant="danger" onClick={() => clear.mutate(undefined, { onSuccess: onDone })} disabled={clear.isPending}>
            Убрать факт
          </Button>
        ) : (
          <span />
        )}
        <Button type="submit" variant="primary" disabled={!!parsed.error || !!effError || save.isPending}>
          Сохранить факт
        </Button>
      </div>
    </form>
  );
}

function PlanForm({ employee, cell, onDone }: { employee: EmployeeBrief; cell: DayCell; onDone: () => void }) {
  const [kind, setKind] = useState<string>(cell.plan?.kind ?? "work");
  const [text, setText] = useState(cell.plan?.kind === "work" ? formatIntervals(cell.plan.intervals) : "");
  const [note, setNote] = useState(cell.plan?.note ?? "");
  const [reason, setReason] = useState("");
  const parsed = parseIntervals(text);
  const save = useAdminMutation(
    () =>
      api.put(path(employee, cell, "plan"), {
        kind: kind === "none" ? null : kind,
        intervals: kind === "work" ? parsed.intervals : null,
        note: kind === "note" ? note : null,
        reason,
      }),
    { success: "План сохранён новой версией" },
  );
  const invalid = kind === "work" && !!parsed.error;
  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined, { onSuccess: onDone });
      }}
    >
      <Field label="День в плане">
        <Select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="work">рабочий, со временем</option>
          <option value="note">заметка без времени</option>
          <option value="off">выходной</option>
          <option value="none">убрать из плана</option>
        </Select>
      </Field>
      {kind === "work" ? (
        <Field label="Плановое время" error={text && parsed.error ? parsed.error : null}>
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="10:00 - 18:00" />
        </Field>
      ) : null}
      {kind === "note" ? (
        <Field label="Заметка">
          <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="по вайбу" />
        </Field>
      ) : null}
      {cell.plan?.note_has_time && kind === "note" ? (
        <p className="flex items-center gap-1.5 text-[12px] text-deviation-ink">
          <AlarmClock className="size-3.5" /> В заметке есть время: если оно точное, сделайте день рабочим.
        </p>
      ) : null}
      <Reason value={reason} onChange={setReason} />
      <div className="flex justify-end">
        <Button type="submit" variant="primary" disabled={invalid || save.isPending}>
          Сохранить план
        </Button>
      </div>
    </form>
  );
}

function StatusForm({ employee, cell, onDone }: { employee: EmployeeBrief; cell: DayCell; onDone: () => void }) {
  const [kind, setKind] = useState<string>(cell.status ?? "vacation");
  const [end, setEnd] = useState(cell.date);
  const [note, setNote] = useState(cell.status_note ?? "");
  const [reason, setReason] = useState("");
  const save = useAdminMutation(
    () =>
      api.put(path(employee, cell, "status"), {
        kind: kind === "none" ? null : (kind as StatusKind),
        end,
        note,
        reason,
      }),
    { success: (r: unknown) => `Статус сохранён. ${(r as { detail?: string }).detail ?? ""}` },
  );
  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined, { onSuccess: onDone });
      }}
    >
      <Field label="Статус">
        <Select value={kind} onChange={(e) => setKind(e.target.value)}>
          {Object.entries(STATUS).map(([k, v]) => (
            <option key={k} value={k}>
              {v.label}
            </option>
          ))}
          <option value="none">снять статус</option>
        </Select>
      </Field>
      <Field label="По какое число" hint="Для периода отпуска или больничного">
        <Input type="date" min={cell.date} value={end} onChange={(e) => setEnd(e.target.value)} />
      </Field>
      <Field label="Комментарий">
        <Input value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <Reason value={reason} onChange={setReason} />
      <div className="flex justify-end">
        <Button type="submit" variant="primary" disabled={save.isPending || end < cell.date}>
          Сохранить статус
        </Button>
      </div>
    </form>
  );
}
