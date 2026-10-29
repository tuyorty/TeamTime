import { Plus, Trash2, UserPen } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router";

import { api } from "@/api/client";
import { keys, useAdminMutation, useEmployees } from "@/api/queries";
import type { Employee, EmployeeIn } from "@/api/types";
import { Avatar } from "@/components/domain/Avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input, Select, Switch, Textarea } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { employeeColor } from "@/lib/colors";
import { hm } from "@/lib/format";
import { useTheme } from "@/lib/theme";
import { prepareAvatar } from "@/lib/avatar";

const COLORS = ["blue", "orange", "aqua", "yellow", "magenta", "green", "violet", "red"];
const COLOR_NAMES: Record<string, string> = {
  blue: "синий",
  orange: "оранжевый",
  aqua: "бирюзовый",
  yellow: "жёлтый",
  magenta: "розовый",
  green: "зелёный",
  violet: "фиолетовый",
  red: "красный",
};
const SHORT_NAME = /^[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ]\.\s?(?:[А-ЯЁ]\.)?$/;

export function EmployeesTab() {
  const { data } = useEmployees(true);
  const [search, setSearch] = useSearchParams();
  const prefill = search.get("new");
  const editId = search.get("edit");
  const [editing, setEditing] = useState<Employee | "new" | null>(prefill !== null ? "new" : null);
  const currentEditing = editing ?? data?.find((employee) => String(employee.id) === editId) ?? null;
  const close = () => {
    setEditing(null);
    if (prefill !== null || editId !== null) setSearch({}, { replace: true });
  };
  if (!data) return <Skeleton className="h-80" />;
  return (
    <div className="grid gap-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] text-ink-2">
          Краткое имя должно совпадать со строкой в расписании: по ней бот находит сотрудника.
        </p>
        <Button variant="primary" onClick={() => setEditing("new")}>
          <Plus /> Добавить
        </Button>
      </div>
      <div className="overflow-x-auto rounded-lg border border-line bg-surface">
        <table className="w-full min-w-[760px] border-collapse text-[13px]">
          <thead className="border-b border-line bg-surface-2/60 text-left text-[12px] text-ink-3">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">
                Сотрудник
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                В расписании
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Должность
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Норма в месяц
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Ставка, ₽/ч
              </th>
              <th scope="col" className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {data.map((e) => (
              <tr key={e.id} className={cn("border-b border-line last:border-b-0", !e.is_active && "text-ink-3")}>
                <td className="px-3 py-2">
                  <span className="flex items-center gap-2">
                    <Avatar employee={e} size={24} />
                    <span className="font-medium">{e.full_name}</span>
                    {!e.is_active ? <Badge>не активен</Badge> : null}
                  </span>
                </td>
                <td className="px-3 py-2">{e.short_name}</td>
                <td className="px-3 py-2 text-ink-2">{e.position}</td>
                <td className="px-3 py-2 text-right tnum">{hm(e.monthly_norm_minutes * 60)}</td>
                <td className="px-3 py-2 text-right tnum">{Number(e.hourly_rate).toLocaleString("ru-RU")}</td>
                <td className="px-3 py-2 text-right">
                  <Button size="sm" variant="ghost" onClick={() => setEditing(e)}>
                    <UserPen /> Изменить
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Dialog open={!!currentEditing} onOpenChange={(o) => !o && close()}>
        {currentEditing ? (
          <DialogContent
            className="max-h-[80dvh] overflow-y-auto"
            title={currentEditing === "new" ? "Новый сотрудник" : currentEditing.full_name}
            description="Изменения попадут в журнал правок."
          >
            <EmployeeForm
              employee={currentEditing === "new" ? null : currentEditing}
              prefillShortName={prefill ?? ""}
              onDone={close}
            />
          </DialogContent>
        ) : null}
      </Dialog>
    </div>
  );
}

function EmployeeForm({
  employee,
  prefillShortName = "",
  onDone,
}: {
  employee: Employee | null;
  prefillShortName?: string;
  onDone: () => void;
}) {
  const { isDark } = useTheme();
  const [form, setForm] = useState({
    full_name: employee?.full_name ?? "",
    short_name: employee?.short_name ?? prefillShortName,
    position: employee?.position ?? "",
    phone: employee?.phone ?? "",
    about: employee?.about ?? "",
    avatar_url: employee?.avatar_url ?? "",
    norm: employee ? String(employee.monthly_norm_minutes / 60) : "160",
    rate: employee ? String(Number(employee.hourly_rate)) : "0",
    color: employee?.color || COLORS[0]!,
    is_active: employee?.is_active ?? true,
  });
  const set = (k: keyof typeof form) => (v: string | boolean) => setForm((f) => ({ ...f, [k]: v }));
  const shortError =
    form.short_name && !SHORT_NAME.test(form.short_name.trim()) ? "Как в расписании: «Иванов И.И.»" : null;
  const normError = !(Number(form.norm) >= 0 && Number(form.norm) <= 400) ? "От 0 до 400 часов" : null;
  const rateError = !(Number(form.rate) >= 0) ? "Не меньше нуля" : null;
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [photoLoading, setPhotoLoading] = useState(false);

  const save = useAdminMutation(
    () => {
      const body: EmployeeIn = {
        full_name: form.full_name.trim(),
        short_name: form.short_name.trim(),
        position: form.position.trim(),
        phone: form.phone.trim(),
        about: form.about.trim(),
        avatar_url: form.avatar_url,
        monthly_norm_minutes: Math.round(Number(form.norm) * 60),
        hourly_rate: form.rate.replace(",", "."),
        color: form.color,
        is_active: form.is_active,
      };
      return employee ? api.put(`/admin/employees/${employee.id}`, body) : api.post("/admin/employees", body);
    },
    {
      success: employee ? "Сотрудник сохранён" : "Сотрудник добавлен",
      invalidate: [["employees"], ["employee"], ["today"], ["day-summary"], ["week"], ["month"], ["plans"]],
    },
  );

  const [confirmDelete, setConfirmDelete] = useState(false);
  const remove = useAdminMutation(() => api.delete<{ detail: string }>(`/admin/employees/${employee!.id}`), {
    success: (r) => `Сотрудник удалён. ${r.detail}`,
    invalidate: [
      [...keys.employees(true)],
      ["employees"],
      ["week"],
      ["month"],
      ["today"],
      ["plans"],
      ["inbox"],
      [...keys.identities],
    ],
  });

  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined, { onSuccess: onDone });
      }}
    >
      <Field label="ФИО полностью">
        <Input
          value={form.full_name}
          onChange={(e) => set("full_name")(e.target.value)}
          placeholder="Иванов Иван Иванович"
        />
      </Field>
      <Field label="Как в расписании" error={shortError} hint="По этой строке бот узнаёт сотрудника">
        <Input value={form.short_name} onChange={(e) => set("short_name")(e.target.value)} placeholder="Иванов И.И." />
      </Field>
      <Field label="Должность" hint="Видна в карточке и отчётах">
        <Input value={form.position} onChange={(e) => set("position")(e.target.value)} />
      </Field>
      <Field label="Фотография" error={photoError} hint="JPEG, PNG или WebP, до 10 МБ. Сохраняется уменьшенная копия.">
        <Input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          disabled={photoLoading}
          className="h-auto py-1.5"
          onChange={async (event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (!file) return;
            setPhotoError(null);
            setPhotoLoading(true);
            try {
              set("avatar_url")(await prepareAvatar(file));
            } catch (error) {
              setPhotoError(error instanceof Error ? error.message : "Не удалось прочитать фотографию.");
            } finally {
              setPhotoLoading(false);
            }
          }}
        />
      </Field>
      {form.avatar_url ? (
        <div className="flex items-center gap-3">
          <img src={form.avatar_url} alt="Фотография сотрудника" className="size-14 rounded-full object-cover" />
          <Button size="sm" variant="ghost" onClick={() => set("avatar_url")("")}>
            Убрать фото
          </Button>
        </div>
      ) : null}
      <Field label="Телефон" hint="Для связи с сотрудником, необязательно">
        <Input type="tel" maxLength={40} value={form.phone} onChange={(e) => set("phone")(e.target.value)} />
      </Field>
      <Field label="О сотруднике" hint="Специализация, интересы, с какими вопросами обращаться">
        <Textarea maxLength={500} value={form.about} onChange={(e) => set("about")(e.target.value)} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Норма в месяц, ч" error={normError} hint="Не уменьшается из-за отпусков">
          <Input inputMode="decimal" value={form.norm} onChange={(e) => set("norm")(e.target.value)} />
        </Field>
        <Field label="Ставка, ₽/ч" error={rateError} hint="Для премии за переработку">
          <Input inputMode="decimal" value={form.rate} onChange={(e) => set("rate")(e.target.value)} />
        </Field>
      </div>
      <Field label="Цвет на графиках">
        <Select value={form.color} onChange={(e) => set("color")(e.target.value)}>
          {COLORS.map((c) => (
            <option key={c} value={c}>
              {COLOR_NAMES[c]}
            </option>
          ))}
        </Select>
      </Field>
      <div className="flex items-center gap-2">
        <span
          className="size-4 rounded-full"
          style={{ background: employeeColor(form.color, employee?.id ?? 1, isDark) }}
        />
        <Switch checked={form.is_active} onChange={set("is_active")} label="Активен (показывается в таблице)" />
      </div>
      {employee && confirmDelete ? (
        <div role="alert" className="grid gap-2 rounded-md border border-late/40 bg-late-soft/60 p-3 text-[13px]">
          <p className="font-medium text-late-ink">Удалить {employee.short_name}?</p>
          <p className="text-ink-2">
            Вместе с сотрудником удалятся его планы, дейлики и статусы дней. Исходные сообщения останутся, а привязанный
            аккаунт Telegram отвяжется. Отменить удаление нельзя. Если человек просто ушёл из команды, лучше выключить
            «Активен»: история сохранится.
          </p>
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(false)}>
              Не удалять
            </Button>
            <Button
              size="sm"
              variant="danger"
              disabled={remove.isPending}
              onClick={() => remove.mutate(undefined, { onSuccess: onDone })}
            >
              <Trash2 /> Удалить навсегда
            </Button>
          </div>
        </div>
      ) : null}
      <div className="mt-2 flex justify-end gap-2">
        {employee && !confirmDelete ? (
          <Button variant="danger" className="mr-auto" onClick={() => setConfirmDelete(true)}>
            <Trash2 /> Удалить
          </Button>
        ) : null}
        <Button variant="ghost" onClick={onDone}>
          Отмена
        </Button>
        <Button
          type="submit"
          variant="primary"
          disabled={
            !form.full_name.trim() ||
            !form.short_name.trim() ||
            !!shortError ||
            !!normError ||
            !!rateError ||
            photoLoading ||
            save.isPending
          }
        >
          {employee ? "Сохранить" : "Добавить сотрудника"}
        </Button>
      </div>
    </form>
  );
}
