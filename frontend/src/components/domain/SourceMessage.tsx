import { ExternalLink, History } from "lucide-react";
import { useState } from "react";

import { useMessage } from "@/api/queries";
import type { Issue, Message } from "@/api/types";
import { ErrorState } from "@/components/domain/feedback";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { dateTime } from "@/lib/format";

const SOURCE_LABEL = { telegram: "Telegram", import: "импорт истории", demo: "демо-чат", manual: "ручная правка" } as const;
const RESOLUTION: Record<Message["parses"][number]["resolution"], string> = {
  auto: "разобрано автоматически", pending: "ждёт решения", accepted: "принято администратором",
  fixed: "исправлено администратором", ignored: "игнорируется",
};

/** «Показать источник»: исходный текст сообщения, все его правки и что из него понял парсер. */
export function SourceMessage({ rawId, title, messageVersionId }: {
  rawId: number | null | undefined;
  title: string;
  messageVersionId?: number | null;
}) {
  const { data, isLoading, error, refetch } = useMessage(rawId);
  const [selection, setSelection] = useState<{ rawId: number; versionId: number } | null>(null);
  if (!rawId) return null;
  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />;
  if (isLoading || !data) return <Skeleton className="h-28 w-full" />;

  const versions = [...data.versions].sort((a, b) => a.version - b.version);
  const selectedId = messageVersionId ?? (selection?.rawId === rawId ? selection.versionId : null);
  const current = selectedId == null ? versions.at(-1) : versions.find((v) => v.id === selectedId);
  if (!current) return <p className="text-[13px] text-ink-2">Исходная версия сообщения недоступна.</p>;
  const parses = data.parses.filter((p) => p.message_version_id === current.id).sort((a, b) => b.id - a.id);
  const parse = parses[0];
  const lineIssues = new Map<number, Issue[]>();
  for (const i of parse?.issues ?? []) {
    if (i.line_no) lineIssues.set(i.line_no, [...(lineIssues.get(i.line_no) ?? []), i]);
  }
  const lines = current.text.split("\n");

  return (
    <section aria-label={title} className="grid gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[13px] font-semibold">{title}</h3>
        <div className="flex items-center gap-1.5 text-[12px] text-ink-3">
          {data.author_name}
          {data.telegram_link ? (
            <a href={data.telegram_link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-accent-ink hover:underline">
              в Telegram <ExternalLink className="size-3" />
            </a>
          ) : (
            <span>({SOURCE_LABEL[data.source]})</span>
          )}
        </div>
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-ink-3">
        <span>Отправлено: {dateTime(data.sent_at)}</span>
        {current.edited_at ? <span>Изменено: {dateTime(current.edited_at)}</span> : null}
        <span>{current.version === 1 ? "Исходное сообщение" : `Правка сообщения ${current.version - 1}`}</span>
      </div>
      {versions.length > 1 && messageVersionId == null ? (
        <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Версии сообщения">
          <History className="size-3.5 text-ink-3" />
          {versions.map((v) => (
            <button
              key={v.id}
              type="button"
              aria-pressed={v.id === current.id}
              onClick={() => setSelection({ rawId, versionId: v.id })}
              className={cn(
                "rounded-sm px-1.5 text-[12px] leading-5 text-ink-2 hover:bg-surface-2",
                v.id === current.id && "bg-surface-3 text-ink",
              )}
            >
              {v.version === 1 ? "исходное" : `правка ${v.version - 1}`}
            </button>
          ))}
        </div>
      ) : null}
      {parse ? <div className="flex flex-wrap items-center gap-2 text-[12px] text-ink-3">
        <Badge tone={parse.resolution === "pending" ? "deviation" : "neutral"}>{RESOLUTION[parse.resolution]}</Badge>
        <span>Разобрано: {dateTime(parse.created_at)}</span>
      </div> : null}
      <pre className="max-h-80 overflow-auto rounded-md border border-line bg-bg p-3 font-sans text-[13px] leading-[1.55] whitespace-pre-wrap [overflow-wrap:anywhere]">
        {lines.map((line, n) => {
          const issues = lineIssues.get(n + 1);
          const bad = issues?.some((i) => i.severity !== "info");
          return (
            <span
              key={n}
              className={cn(
                "block rounded-sm px-1 -mx-1",
                issues && (bad ? "bg-late-soft" : "bg-deviation-soft"),
              )}
              title={issues?.map((i) => i.message).join("\n")}
            >
              {line || " "}
            </span>
          );
        })}
      </pre>
      {parse && parse.issues.length ? (
        <ul className="grid gap-1 text-[12px]">
          {parse.issues.map((i, n) => (
            <li key={n} className="flex gap-2">
              <Badge tone={i.severity === "error" ? "late" : i.severity === "warning" ? "deviation" : "neutral"}>
                {i.line_no ? `стр. ${i.line_no}` : i.severity === "info" ? "заметка" : "внимание"}
              </Badge>
              <span className="text-ink-2">{i.message}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
