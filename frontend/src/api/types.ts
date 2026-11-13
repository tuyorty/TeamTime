// Удобные имена для сгенерированных типов (npm run gen:api).
import type { components } from "./schema";

type S = components["schemas"];

export type Meta = S["MetaOut"];
export type EmployeeBrief = S["EmployeeBrief"];
export type Employee = S["EmployeeOut"];
export type EmployeeIn = S["EmployeeIn"];
export type EmployeeDetail = S["EmployeeDetailOut"];
export type Identity = S["IdentityOut"];
export type Topic = S["TopicOut"];
export type Chat = S["ChatOut"];
export type DayCell = S["DayCellOut"];
export type PlanDay = S["PlanOut"];
export type Fact = S["FactOut"];
export type Totals = S["Totals"];
export type DayTotals = S["DayTotals"];
export type PeriodHighlights = S["PeriodHighlights"];
export type HighlightRecord = S["HighlightRecord"];
export type ScheduleChangePreview = S["ScheduleChangePreview"];
export type Week = S["WeekOut"];
export type WeekRow = S["WeekRow"];
export type Month = S["MonthOut"];
export type MonthRow = S["MonthRow"];
export type MonthSummary = S["MonthSummaryOut"];
export type Finance = S["FinanceOut"];
export type FinanceRow = S["FinanceRow"];
export type FinanceAmounts = S["FinanceAmounts"];
export type ProjectBonus = S["ProjectBonusOut"];
export type PenaltyScale = S["PenaltyScaleOut"];
export type Today = S["TodayOut"];
export type TodayRow = S["TodayRow"];
/** /display/today отдаёт только план: без фактов, штрафов и источников сообщений. */
export type DisplayDayCell = Pick<DayCell, "date" | "plan" | "status" | "status_note">;
export type DisplayTodayRow = Pick<TodayRow, "presence"> & {
  employee: Pick<EmployeeBrief, "id" | "full_name" | "short_name" | "department" | "avatar_url" | "position" | "color">;
  cell: DisplayDayCell;
};
export type DisplayToday = Pick<Today, "date" | "now_sec" | "counts"> & { rows: DisplayTodayRow[] };
export type FeedItem = S["FeedItem"];
export type Plans = S["PlansOut"];
export type PlanRow = S["PlanRow"];
export type PlanVersion = S["PlanVersionOut"];
export type Message = S["MessageOut"];
export type ParseResult = S["ParseResultOut"];
export type Inbox = S["InboxOut"];
export type InboxItem = S["InboxItem"];
export type Issue = S["IssueOut"];
export type SearchHit = S["SearchHit"];
export type Audit = S["AuditOut"];
export type AppSettings = S["AppSettings"];
export type DayState = DayCell["state"];
export type StatusKind = NonNullable<DayCell["status"]>;
export type StatusRequest = S["StatusRequestOut"];
export type StatusRequests = S["StatusRequestsOut"];
export type SystemState = S["SystemOut"];
export type CalculationHistory = S["HistoryOut"];
