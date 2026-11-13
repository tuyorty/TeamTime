import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export interface TeamActor {
  employee_id: number;
  name: string;
  leader: boolean;
  technical: boolean;
}
export interface TeamSession {
  enabled: boolean;
  module_enabled: boolean;
  module_available: boolean;
  demo: boolean;
  actor: TeamActor | null;
}
export interface FundMember {
  id: number;
  full_name: string;
  short_name: string;
  department: "software" | "laboratory";
  avatar_url: string;
  active: boolean;
  leader: boolean;
  joined_on: string;
  left_on: string | null;
  overpayment: string;
  unallocated: string;
  opening: { month: string; amount: string; reason: string } | null;
}
export interface FundAmounts {
  salary: string;
  bonus: string;
  correction: string;
  received: string;
  overpayment_in: string;
  difference: string;
  offset: string;
  overpayment_new: string;
  overpayment_out: string;
  supplement_before_rounding: string;
  supplement: string;
  rounding: string;
  compensation: string;
  accrued: string;
  paid: string;
  due: string;
}
export interface FundProblem {
  code: string;
  message: string;
  day?: string;
}
export interface FundSource {
  name: string;
  amount: string;
  state: "unknown" | "partial" | "complete";
  version: number;
}
export interface FundReceipt {
  id: number;
  source: string;
  origin_month: string;
  received_on: string;
  amount: string;
}
export interface SalaryPart {
  key: string;
  target: string;
  norm: string;
  effective: string;
  penalty: string;
  credited: string;
  salary: string;
}
export interface FundRow {
  employee: {
    id: number;
    name: string;
    short_name: string;
    department: "software" | "laboratory";
    avatar_url: string;
  };
  no_other_income: boolean;
  norm_sec: number;
  effective_sec: number;
  penalty_sec: number;
  credited_sec: number;
  parts: SalaryPart[];
  amounts: FundAmounts | null;
  sources: FundSource[];
  receipts: FundReceipt[];
  blockers: FundProblem[];
  unallocated: string;
  inputs: {
    conditions: {
      key: string;
      target: string;
      share: string;
      start: string;
      end: string;
    }[];
  } | null;
}
export interface FundReport {
  month: string;
  ruleset: string;
  closed: boolean;
  closed_at: string | null;
  rows: FundRow[];
  blockers: FundProblem[];
  can_close: boolean;
  fingerprint: string;
}
export interface Basket {
  id: number;
  name: string;
  owner_id: number;
  balance: string;
  reconciled_on: string | null;
  actual: string | null;
  difference: string | null;
}
export interface Obligation {
  id: number;
  employee_id: number;
  month: string;
  kind: "salary" | "compensation";
  amount: string;
  due: string;
  paid: string;
  title: string;
}
export interface FundOperation {
  id: number;
  kind: string;
  state: "draft" | "posted" | "cancelled";
  occurred_on: string;
  amount: string;
  basket_id: number | null;
  target_basket_id: number | null;
  employee_id: number | null;
  reason: string;
  created_by: number;
  confirmed_by: number | null;
  confirmed_at: string | null;
  consented_at: string | null;
  reverses_id: number | null;
  details: Record<string, unknown>;
}
export interface Claim {
  id: number;
  employee_id: number;
  month: string;
  spent_on: string;
  amount: string;
  title: string;
  state: "pending" | "approved" | "rejected" | "cancelled";
  decision_reason: string;
}
export interface Loan {
  id: number;
  employee_id: number;
  amount: string;
  issued_on: string;
  due_on: string;
  reason: string;
  issued: boolean;
  outstanding: string;
  overdue: boolean;
}
export interface TimeRequest {
  id: number;
  employee_id: number;
  kind: string;
  days: string[];
  seconds: number;
  state: string;
  reason: string;
  decision_reason: string;
}
export interface Adjustment {
  id: number;
  employee_id: number;
  kind: string;
  origin_month: string;
  applied_month: string;
  amount: string;
  reason: string;
  state: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
}
export interface Terms {
  id: number;
  employee_id: number;
  effective_from: string;
  revision: number;
  target: string;
  share: string;
  sources: string[];
  no_other_income: boolean;
  reason: string;
}
export interface FundCalendar {
  id: number;
  month: string;
  version: number;
  source: string;
  source_version: string;
  days: Record<string, number>;
  holidays: string[];
  reason: string;
}
export interface FundOverview {
  baskets: Basket[];
  cash: string;
  due: string;
  free: string;
  runway: string | null;
  runway_months_used: number;
  members: FundMember[];
  operations: FundOperation[];
  claims: Claim[];
  loans: Loan[];
  obligations: Obligation[];
  requests: TimeRequest[];
  adjustments: Adjustment[];
  closed_changes: {
    event_id: number;
    employee_id: number;
    month: string;
    created_at: string;
  }[];
  calendars: FundCalendar[];
  terms: Terms[];
  history: {
    id: number;
    actor_id: number;
    action: string;
    data: Record<string, unknown>;
    created_at: string;
  }[];
  periods: { month: string; closed_at: string | null }[];
  config: {
    enabled: boolean;
    module_enabled: boolean;
    first_month: string;
    notification_hour: number;
    notification_minute: number;
    reminders_enabled: boolean;
    technical_employee_ids: number[];
  };
}

export const useTeamSession = () =>
  useQuery({
    queryKey: ["team-session"],
    queryFn: () => api.get<TeamSession>("/team/session"),
    staleTime: 30_000,
    refetchInterval: 30_000,
    retry: false,
  });
export const useFundOverview = (enabled = true) =>
  useQuery({
    queryKey: ["fund", "overview"],
    queryFn: () => api.get<FundOverview>("/fund/overview"),
    enabled,
    refetchInterval: 30_000,
    retry: false,
  });
export const useFundReport = (month: string, enabled = true) =>
  useQuery({
    queryKey: ["fund", "month", month],
    queryFn: () => api.get<FundReport>(`/fund/months/${month}`),
    enabled,
    refetchInterval: 30_000,
    retry: false,
  });

export function useFundAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) =>
      api.post<Record<string, unknown>>(path, body),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["fund"] }),
        queryClient.invalidateQueries({ queryKey: ["team-session"] }),
      ]);
    },
  });
}
