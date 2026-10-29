import { lazy, Suspense } from "react";
import { createBrowserRouter, RouterProvider } from "react-router";

import { AppShell } from "@/components/layout/AppShell";
import { Skeleton } from "@/components/ui/skeleton";

import NotFound from "./pages/NotFound";

const TodayPage = lazy(() => import("./pages/TodayPage"));
const DaySummaryPage = lazy(() => import("./pages/DaySummaryPage"));
const WeekPage = lazy(() => import("./pages/WeekPage"));
const MonthPage = lazy(() => import("./pages/MonthPage"));
const PeoplePage = lazy(() => import("./pages/PeoplePage"));
const EmployeePage = lazy(() => import("./pages/EmployeePage"));
const PlansPage = lazy(() => import("./pages/PlansPage"));
const CalendarPage = lazy(() => import("./pages/CalendarPage"));
const InboxPage = lazy(() => import("./pages/InboxPage"));
const AdminPage = lazy(() => import("./pages/AdminPage"));
const EmulatorPage = lazy(() => import("./pages/EmulatorPage"));

function PageFallback() {
  return (
    <div className="grid gap-4" aria-busy>
      <Skeleton className="h-9 w-56" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

const page = (el: React.ReactNode) => <Suspense fallback={<PageFallback />}>{el}</Suspense>;

const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { index: true, element: page(<TodayPage />) },
      { path: "day", element: page(<DaySummaryPage />) },
      { path: "week", element: page(<WeekPage />) },
      { path: "week/:year/:week", element: page(<WeekPage />) },
      { path: "month", element: page(<MonthPage />) },
      { path: "month/:year/:month", element: page(<MonthPage />) },
      { path: "people", element: page(<PeoplePage />) },
      { path: "people/:id", element: page(<EmployeePage />) },
      { path: "plans", element: page(<PlansPage />) },
      { path: "plans/:year/:week", element: page(<PlansPage />) },
      { path: "calendar", element: page(<CalendarPage />) },
      { path: "inbox", element: page(<InboxPage />) },
      { path: "admin", element: page(<AdminPage />) },
      { path: "admin/:tab", element: page(<AdminPage />) },
      { path: "demo", element: page(<EmulatorPage />) },
      { path: "*", element: <NotFound /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
