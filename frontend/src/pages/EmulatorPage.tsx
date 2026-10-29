import { Bot, CornerDownLeft, PencilLine, Wand2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";

import { api, ApiError } from "@/api/client";
import { useIdentities, useMeta } from "@/api/queries";
import type { Issue } from "@/api/types";
import { EmptyState } from "@/components/domain/feedback";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, Textarea } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import { Segmented } from "@/components/ui/segmented";
import { cn } from "@/lib/cn";
import { dayMonth, ddmm, parseDate, timeOf } from "@/lib/format";

type Topic = "schedule" | "daily";

interface Sent {
  key: number;
  rawId: number | null;
  author: string;
  authorId: number;
  topic: Topic;
  text: string;
  edited: boolean;
  reaction: string | null;
  reply: string | null;
  status: string | null;
  employee: string | null;
  issues: Issue[];
  at: string;
}

interface Result {
  raw_message_id: number | null;
  reaction: string | null;
  reply: string | null;
  status: string | null;
  kind: string;
  employee: string | null;
  issues: Issue[];
}

function templates(today: string, shortName: string): Record<Topic, string> {
  const d = parseDate(today);
  const monday = new Date(d);
  monday.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  const sat = new Date(monday);
  sat.setDate(monday.getDate() + 5);
  const iso = (x: Date) => `${String(x.getDate()).padStart(2, "0")}.${String(x.getMonth() + 1).padStart(2, "0")}`;
  return {
    schedule: `Спринт ${iso(monday)} - ${iso(sat)}\n${shortName}\n\nПн: 10:00 - 18:00\nВт: 10:00 - 18:00\nСр: по вайбу с 16:30 до вечера\nЧт: 12:00 - 20:00\nПт: 10:00 - 18:00\nСб: ——————\n\n- задача один\n- задача два\n\n#расписание`,
    daily: `${ddmm(today)}.${d.getFullYear()}\n10:20 - 13:00; 14:00 - 18:40\nЭффективность: 85%\n\n- разобрал инбокс\n- починил экспорт\n\n#дейли`,
  };
}

const ENTITIES: Record<string, string> = { "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#x27;": "'", "&amp;": "&" };

/** HTML ответа бота → обычный текст (выводится React как текст, без разметки). */
function strip(html: string): string {
  return html
    .replace(/<a [^>]*>(.*?)<\/a>/g, "$1")
    .replace(/<[^>]+>/g, "")
    .replace(/&(?:lt|gt|quot|#x27|amp);/g, (e) => ENTITIES[e] ?? e);
}

export default function EmulatorPage() {
  const meta = useMeta().data;
  const identities = useIdentities().data;
  const people = useMemo(() => (identities ?? []).filter((i) => i.employee || i.display_name), [identities]);
  const [authorId, setAuthorId] = useState<number | null>(null);
  const [topic, setTopic] = useState<Topic>("daily");
  const [text, setText] = useState("");
  const [log, setLog] = useState<Sent[]>([]);
  const [editing, setEditing] = useState<Sent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const author = people.find((p) => p.telegram_user_id === authorId) ?? people.find((p) => p.employee) ?? people[0];

  if (meta && !meta.demo) {
    return (
      <EmptyState icon={Bot} title="Эмулятор работает только в демо">
        Запустите стек с DEMO=1, чтобы писать сообщения без Telegram.
      </EmptyState>
    );
  }

  async function send() {
    if (!author || !text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<Result>("/demo/messages", {
        telegram_user_id: author.telegram_user_id,
        topic,
        text,
        edit_raw_message_id: editing?.rawId ?? null,
      });
      const entry: Sent = {
        key: Date.now(),
        rawId: r.raw_message_id,
        author: author.display_name,
        authorId: author.telegram_user_id,
        topic,
        text,
        edited: !!editing,
        reaction: r.reaction,
        reply: r.reply,
        status: r.status,
        employee: r.employee,
        issues: r.issues,
        at: new Date().toISOString(),
      };
      setLog((l) => (editing ? l.map((x) => (x.key === editing.key ? { ...entry, key: x.key } : x)) : [entry, ...l]));
      setEditing(null);
      setText("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не отправилось");
    } finally {
      setBusy(false);
    }
  }

  const tpl = meta && author ? templates(meta.today, author.employee?.short_name ?? "Иванов И.И.") : null;

  return (
    <div className="grid gap-5">
      <PageHeader
        title="Эмулятор чата"
        subtitle={`Напишите сообщение в тему так, как его написал бы сотрудник. Бот разберёт его тем же кодом, а таблица обновится сама. В демо сегодня ${meta ? dayMonth(meta.today) : "…"}.`}
      />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <Panel title="Новое сообщение">
          <div className="grid gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Select
                className="w-64"
                aria-label="Отправитель"
                value={author?.telegram_user_id ?? ""}
                onChange={(e) => setAuthorId(Number(e.target.value))}
              >
                {people.map((p) => (
                  <option key={p.id} value={p.telegram_user_id}>
                    {p.display_name} {p.employee ? `(${p.employee.short_name})` : "(не привязан)"}
                  </option>
                ))}
              </Select>
              <Segmented
                label="Тема"
                value={topic}
                onChange={setTopic}
                options={[
                  { value: "daily", label: "# дейлики" },
                  { value: "schedule", label: "# расписание" },
                ]}
              />
            </div>
            {editing ? (
              <div className="flex items-center justify-between rounded-md bg-deviation-soft px-3 py-1.5 text-[12px] text-deviation-ink">
                <span className="flex items-center gap-1.5">
                  <PencilLine className="size-3.5" /> Правка сообщения — бот разберёт новую версию
                </span>
                <button type="button" className="underline" onClick={() => { setEditing(null); setText(""); }}>
                  отменить
                </button>
              </div>
            ) : null}
            <Textarea
              rows={12}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void send();
              }}
              placeholder="Текст сообщения"
              className="font-sans text-[13px]"
              aria-label="Текст сообщения"
            />
            <div className="flex flex-wrap items-center justify-between gap-2">
              {tpl ? (
                <Button size="sm" variant="ghost" onClick={() => setText(tpl[topic])}>
                  <Wand2 /> Вставить шаблон
                </Button>
              ) : (
                <span />
              )}
              <Button variant="primary" onClick={send} disabled={busy || !text.trim() || !author}>
                <CornerDownLeft /> {editing ? "Сохранить правку" : "Отправить"}
              </Button>
            </div>
            {error ? <p role="alert" className="text-[13px] text-late-ink">{error}</p> : null}
            <p className="text-[12px] text-ink-3">
              Попробуйте убрать эффективность, написать «Чт: по вайбу» или отправить от «Никита 👋» — у него нет
              привязки. Ctrl/⌘ + Enter — отправить.
            </p>
          </div>
        </Panel>
        <Panel title="Тема в Telegram" description="Что увидят участники чата">
          {log.length ? (
            <ol className="grid gap-4">
              {log.map((m) => (
                <li key={m.key} className="grid gap-1.5">
                  <div className="flex items-baseline gap-2 text-[12px]">
                    <span className="font-semibold text-ink">{m.author}</span>
                    <span className="text-ink-3">в # {m.topic === "daily" ? "дейлики" : "расписание"}, {timeOf(m.at)}</span>
                    {m.edited ? <span className="text-ink-3">изменено</span> : null}
                  </div>
                  <div className="relative w-fit max-w-full rounded-lg rounded-tl-sm bg-surface-2 px-3 py-2 text-[13px] whitespace-pre-wrap">
                    {m.text}
                    {m.reaction ? (
                      <span className="absolute -bottom-3 right-2 rounded-full border border-line bg-surface px-1.5 text-[14px] leading-6 shadow-sm" aria-label={`Реакция бота ${m.reaction}`}>
                        {m.reaction}
                      </span>
                    ) : null}
                  </div>
                  {m.reply ? (
                    <div className="ml-6 mt-2 flex w-fit max-w-full items-start gap-2 rounded-lg bg-accent-soft px-3 py-2 text-[13px]">
                      <Bot className="mt-0.5 size-4 shrink-0 text-accent-ink" />
                      <span className="whitespace-pre-line">
                        {strip(m.reply)}{" "}
                        {m.reply.includes("исправить в боте") ? (
                          <span className="text-[12px] text-ink-3">(ссылка открывает личку бота)</span>
                        ) : null}
                      </span>
                    </div>
                  ) : null}
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-ink-3">
                    {m.status ? (
                      <Badge tone={m.status === "ok" ? "accent" : m.status === "partial" ? "deviation" : "late"}>
                        {m.status === "ok" ? "разобрано" : m.status === "partial" ? "с вопросами" : "не разобрано"}
                      </Badge>
                    ) : (
                      <Badge>бот промолчал: это не шаблон</Badge>
                    )}
                    {m.employee ? <span>сотрудник: {m.employee}</span> : null}
                    {m.status && m.status !== "ok" ? <Link to="/inbox" className="text-accent-ink hover:underline">в инбоксе</Link> : null}
                    <button
                      type="button"
                      className={cn("ml-auto inline-flex items-center gap-1 hover:text-ink", !m.rawId && "hidden")}
                      onClick={() => {
                        setEditing(m);
                        setTopic(m.topic);
                        setAuthorId(m.authorId);
                        setText(m.text);
                      }}
                    >
                      <PencilLine className="size-3.5" /> Редактировать
                    </button>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <p className="py-10 text-center text-[13px] text-ink-2">
              Сообщений пока нет. Отправьте дейлик слева и откройте «Сегодня» или «Неделю» в соседней вкладке — данные
              появятся без перезагрузки.
            </p>
          )}
        </Panel>
      </div>
    </div>
  );
}
