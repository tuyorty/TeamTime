import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, ApiError } from "./client";
import type {
  AppSettings, Audit, EmployeeDetail, Employee, Identity, Inbox, Message, Meta, Month, Plans,
  Chat, Today, Topic, Week,
} from "./types";

export const keys = {
  meta: ["meta"] as const,
  today: ["today"] as const,
  week: (y: number, w: number) => ["week", y, w] as const,
  month: (y: number, m: number) => ["month", y, m] as const,
  plans: (y: number, w: number) => ["plans", y, w] as const,
  employees: (all = false) => ["employees", all] as const,
  employee: (id: number, start?: string, end?: string) => ["employee", id, start, end] as const,
  calendar: (start: string, end: string) => ["calendar", start, end] as const,
  message: (id: number) => ["message", id] as const,
  inbox: (view: string, filter = "") => ["inbox", view, filter] as const,
  identities: ["identities"] as const,
  topics: ["topics"] as const,
  chats: ["chats"] as const,
  settings: ["settings"] as const,
  audit: (employeeId?: number) => ["audit", employeeId] as const,
  search: (q: string) => ["search", q] as const,
};

export const useMeta = () =>
  useQuery({ queryKey: keys.meta, queryFn: () => api.get<Meta>("/meta"), staleTime: 60_000 });

export const useToday = () =>
  useQuery({ queryKey: keys.today, queryFn: () => api.get<Today>("/today"), refetchInterval: 60_000 });

export const useDaySummary = (day: string | undefined) =>
  useQuery({
    queryKey: ["day-summary", day],
    queryFn: () => api.get<Today>(`/today?day=${day}`),
    enabled: !!day,
    refetchInterval: 60_000,
  });

export const useWeek = (y: number, w: number) =>
  useQuery({
    queryKey: keys.week(y, w),
    queryFn: () => api.get<Week>(`/weeks/${y}/${w}`),
    placeholderData: keepPreviousData,
  });

export const useMonth = (y: number, m: number) =>
  useQuery({
    queryKey: keys.month(y, m),
    queryFn: () => api.get<Month>(`/months/${y}/${m}`),
    placeholderData: keepPreviousData,
  });

export const usePlans = (y: number, w: number) =>
  useQuery({
    queryKey: keys.plans(y, w),
    queryFn: () => api.get<Plans>(`/plans/${y}/${w}`),
    placeholderData: keepPreviousData,
  });

export const useEmployees = (includeInactive = false) =>
  useQuery({
    queryKey: keys.employees(includeInactive),
    queryFn: () => api.get<Employee[]>(`/employees${includeInactive ? "?include_inactive=true" : ""}`),
  });

export const useEmployee = (id: number, start?: string, end?: string) =>
  useQuery({
    queryKey: keys.employee(id, start, end),
    queryFn: () => {
      const q = new URLSearchParams();
      if (start) q.set("start", start);
      if (end) q.set("end", end);
      const qs = q.toString();
      return api.get<EmployeeDetail>(`/employees/${id}${qs ? `?${qs}` : ""}`);
    },
    placeholderData: keepPreviousData,
  });

export const useCalendar = (start: string, end: string) =>
  useQuery({
    queryKey: keys.calendar(start, end),
    queryFn: () => api.get<Record<string, import("./types").DayCell[]>>(`/calendar?start=${start}&end=${end}`),
    placeholderData: keepPreviousData,
  });

export const useMessage = (id: number | null | undefined) =>
  useQuery({
    queryKey: keys.message(id ?? 0),
    queryFn: () => api.get<Message>(`/messages/${id}`),
    enabled: !!id,
  });

/** ``filter`` — готовая строка параметров фильтров (employee, problem, kind) без «?». */
export const useInbox = (view: string, filter = "") =>
  useQuery({
    queryKey: keys.inbox(view, filter),
    queryFn: () => api.get<Inbox>(`/inbox?view=${view}${filter ? `&${filter}` : ""}`),
  });

export const useIdentities = () =>
  useQuery({ queryKey: keys.identities, queryFn: () => api.get<Identity[]>("/identities") });

export const useChats = () => useQuery({ queryKey: keys.chats, queryFn: () => api.get<Chat[]>("/admin/chats") });

export const useTopics = (enabled: boolean) =>
  useQuery({ queryKey: keys.topics, queryFn: () => api.get<Topic[]>("/admin/topics"), enabled });

export const useSettings = () =>
  useQuery({ queryKey: keys.settings, queryFn: () => api.get<AppSettings>("/admin/settings") });

export const useAudit = (employeeId?: number) =>
  useQuery({
    queryKey: keys.audit(employeeId),
    queryFn: () => api.get<Audit[]>(`/audit?limit=200${employeeId ? `&employee_id=${employeeId}` : ""}`),
  });

/** Мутация админа: тост об успехе или понятная ошибка, затем перезапрос затронутых данных. */
export function useAdminMutation<TVars, TResult = unknown>(
  fn: (vars: TVars) => Promise<TResult>,
  { success, invalidate = [] }: { success?: string | ((r: TResult) => string); invalidate?: readonly unknown[][] } = {},
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (result) => {
      if (success) toast.success(typeof success === "function" ? success(result) : success);
      if (invalidate.length === 0) void qc.invalidateQueries();
      for (const key of invalidate) void qc.invalidateQueries({ queryKey: key });
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 401) {
        toast.error("Нужен режим админа. Войдите заново.");
        void qc.invalidateQueries({ queryKey: keys.meta });
        return;
      }
      toast.error(err instanceof Error ? err.message : "Не удалось сохранить");
    },
  });
}
