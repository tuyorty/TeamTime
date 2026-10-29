/**
 * Realtime (ADR 0003): один EventSource на вкладку. Событие несёт только идентификаторы —
 * мы инвалидируем затронутые запросы, подсвечиваем ячейки и показываем ненавязчивый тост.
 */
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";
import { toast } from "sonner";

import { dayMonth } from "./format";

export type Connection = "connecting" | "live" | "offline";

interface RealtimeEvent {
  id: number;
  type: string;
  employee_id?: number | null;
  employee?: string | null;
  dates?: string[];
  kind?: string;
  status?: string;
  edited?: boolean;
}

const FLASH_MS = 2600;
const listeners = new Set<() => void>();
let connection: Connection = "connecting";
let flashed = new Set<string>();

function emit() {
  for (const l of listeners) l();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export const flashKey = (employeeId: number, date: string) => `${employeeId}:${date}`;

export function useConnection(): Connection {
  return useSyncExternalStore(subscribe, () => connection);
}

/** Подсвечена ли ячейка после недавнего события. */
export function useFlashed(employeeId: number, date: string): boolean {
  return useSyncExternalStore(subscribe, () => flashed.has(flashKey(employeeId, date)));
}

function flash(event: RealtimeEvent) {
  if (!event.employee_id || !event.dates?.length) return;
  const added = event.dates.map((d) => flashKey(event.employee_id!, d));
  flashed = new Set([...flashed, ...added]);
  emit();
  setTimeout(() => {
    flashed = new Set([...flashed].filter((k) => !added.includes(k)));
    emit();
  }, FLASH_MS);
}

const INVALIDATE: Record<string, string[]> = {
  "message.ingested": ["today", "day-summary", "week", "month", "plans", "employee", "calendar", "inbox", "search"],
  "daily.changed": ["today", "day-summary", "week", "month", "employee", "calendar", "inbox", "audit"],
  "plan.changed": ["today", "day-summary", "week", "month", "plans", "employee", "calendar", "audit"],
  "status.changed": ["today", "day-summary", "week", "month", "employee", "calendar", "audit"],
  "employee.changed": ["employees", "employee", "week", "month", "today", "day-summary", "audit"],
  "identity.changed": ["identities", "employee", "inbox", "audit"],
  "inbox.changed": ["inbox", "today", "day-summary", "week", "month", "plans", "employee", "calendar", "audit"],
  "settings.changed": ["meta", "settings", "week", "month", "today", "day-summary", "audit"],
};

function describe(event: RealtimeEvent): string | null {
  if (event.type !== "message.ingested") return null;
  const who = event.employee ?? "Кто-то";
  const when = event.dates?.length === 1 ? ` за ${dayMonth(event.dates[0]!)}` : "";
  const what = event.kind === "schedule" ? "расписание" : "дейлик";
  const verb = event.edited ? "исправил" : "прислал";
  return `${who} ${verb} ${what}${event.kind === "daily" ? when : ""}`;
}

export function handleEvent(qc: QueryClient, event: RealtimeEvent) {
  if (event.type === "resync") {
    void qc.invalidateQueries();
    return;
  }
  for (const root of INVALIDATE[event.type] ?? []) void qc.invalidateQueries({ queryKey: [root] });
  flash(event);
  const text = describe(event);
  if (text) {
    const problem = event.status && event.status !== "ok";
    toast(text, {
      description: problem ? "Есть вопросы к разбору: загляните в инбокс" : undefined,
      duration: 4000,
    });
  }
}

export function useRealtime() {
  const qc = useQueryClient();
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource("/api/v1/events");
    const set = (c: Connection) => {
      connection = c;
      emit();
    };
    source.onopen = () => set("live");
    source.onerror = () => set(source.readyState === EventSource.CLOSED ? "offline" : "connecting");
    const onMessage = (e: MessageEvent<string>) => {
      try {
        handleEvent(qc, JSON.parse(e.data) as RealtimeEvent);
      } catch {
        /* битое событие — пропускаем */
      }
    };
    for (const type of [...Object.keys(INVALIDATE), "resync"]) source.addEventListener(type, onMessage);
    return () => source.close();
  }, [qc]);
}
