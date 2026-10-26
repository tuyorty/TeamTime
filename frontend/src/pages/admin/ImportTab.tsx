import { useQueryClient } from "@tanstack/react-query";
import { FileJson, Upload } from "lucide-react";
import { useRef, useState } from "react";

import type { components } from "@/api/schema";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";

type Report = components["schemas"]["ImportOut"];

export function ImportTab() {
  const input = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function upload() {
    if (!file) return;
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.append("file", file);
    try {
      const r = await fetch("/api/v1/admin/import/telegram", {
        method: "POST",
        body,
        credentials: "same-origin",
        headers: { "X-Requested-With": "teamtime" },
      });
      const data = await r.json();
      if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Импорт не удался");
      setReport(data as Report);
      void qc.invalidateQueries();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Импорт не удался");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Panel title="Импорт истории из Telegram" description="Тот же парсер, что у бота. Повторный импорт ничего не дублирует.">
        <ol className="mb-4 grid list-decimal gap-1 pl-5 text-[13px] text-ink-2">
          <li>Telegram Desktop → чат → ⋮ → «Экспорт истории чата».</li>
          <li>Формат — «Машиночитаемый JSON», медиа можно не выгружать.</li>
          <li>Загрузите получившийся result.json сюда или через CLI: teamtime import telegram result.json.</li>
        </ol>
        <div
          className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-line-strong px-4 py-8 text-center"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            setFile(e.dataTransfer.files[0] ?? null);
          }}
        >
          <FileJson className="size-6 text-ink-3" />
          <p className="text-[13px] text-ink-2">{file ? file.name : "Перетащите result.json или выберите файл"}</p>
          <input ref={input} type="file" accept=".json,application/json" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <div className="flex gap-2">
            <Button size="sm" onClick={() => input.current?.click()}>
              Выбрать файл
            </Button>
            <Button size="sm" variant="primary" disabled={!file || busy} onClick={upload}>
              <Upload /> {busy ? "Импортируем…" : "Импортировать"}
            </Button>
          </div>
        </div>
        {error ? <p role="alert" className="mt-3 text-[13px] text-late-ink">{error}</p> : null}
      </Panel>
      <Panel title="Результат" description={report ? report.chat_title : "Здесь появится отчёт об импорте"}>
        {report ? (
          <dl className="grid grid-cols-[10rem_1fr] gap-x-3 gap-y-1.5 text-[13px] tnum">
            <dt className="text-ink-3">Сообщений в файле</dt>
            <dd>{report.total}</dd>
            <dt className="text-ink-3">Импортировано</dt>
            <dd className="font-medium">{report.imported}</dd>
            <dt className="text-ink-3">Уже были</dt>
            <dd>{report.unchanged}</dd>
            <dt className="text-ink-3">Пропущено</dt>
            <dd>{report.skipped} <span className="text-ink-3">(не в темах и без шаблона)</span></dd>
            <dt className="text-ink-3">Разобрано</dt>
            <dd>
              {report.statuses.ok ?? 0} без вопросов, {report.statuses.partial ?? 0} с вопросами, {report.statuses.failed ?? 0} не разобрано
            </dd>
            <dt className="text-ink-3">Темы</dt>
            <dd>{Object.values(report.topics).join(", ") || "—"}</dd>
            {report.errors.length ? (
              <>
                <dt className="text-late-ink">Ошибки</dt>
                <dd className="text-late-ink">{report.errors.join("; ")}</dd>
              </>
            ) : null}
          </dl>
        ) : (
          <p className="text-[13px] text-ink-2">Сообщения с вопросами попадут в инбокс.</p>
        )}
      </Panel>
    </div>
  );
}
