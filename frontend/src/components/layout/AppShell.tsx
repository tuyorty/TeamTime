import { MoreHorizontal, Search } from "lucide-react";
import { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";

import { useInbox, useMeta } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { useConnection, useRealtime } from "@/lib/realtime";

import { AdminButton } from "./AdminButton";
import { useCommandPalette } from "@/hooks/useCommandPalette";
import { useIsAdmin } from "@/hooks/useIsAdmin";

import { CommandPalette } from "./CommandPalette";
import { NAV, type NavItem } from "./nav";
import { ThemeMenu } from "./ThemeMenu";

/** Логотип ведёт на «Сегодня», как во всех приложениях. */
function Logo() {
  return (
    <Link
      to="/"
      aria-label="xTime — на главную, «Сегодня»"
      className="-mx-1 -my-0.5 flex w-fit items-center gap-2 rounded-md px-1 py-0.5 font-display text-[16px] font-semibold tracking-tight hover:opacity-80"
    >
      {/* Знак: полоса дня — контур плана и заливка факта. */}
      <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden>
        <rect x="1.5" y="6.5" width="19" height="9" rx="2.5" fill="none" stroke="var(--ink-3)" />
        <rect x="6" y="8.5" width="12.5" height="5" rx="1.5" fill="var(--accent)" />
        <rect x="1.5" y="6.5" width="4.5" height="9" rx="2.5" fill="var(--late)" />
      </svg>
      xTime
    </Link>
  );
}

function ConnectionDot() {
  const c = useConnection();
  const label = { live: "Обновления в реальном времени", connecting: "Подключаемся…", offline: "Нет связи с сервером" }[c];
  return (
    <span className="flex items-center gap-1.5 text-[12px] text-ink-3" title={label}>
      <span
        className={cn(
          "size-1.5 rounded-full",
          c === "live" ? "bg-accent" : c === "connecting" ? "bg-deviation" : "bg-late",
        )}
      />
      {c === "live" ? "Онлайн" : c === "connecting" ? "Подключение" : "Офлайн"}
    </span>
  );
}

function useNav(): NavItem[] {
  const demo = useMeta().data?.demo ?? false;
  const admin = useIsAdmin();
  return NAV.filter((n) => (!n.demoOnly || demo) && (!n.adminOnly || admin));
}

function InboxCount() {
  const n = useInbox("pending").data?.counts.pending ?? 0;
  if (!n) return null;
  return (
    <span className="ml-auto rounded-full bg-late-soft px-1.5 text-[11px] font-semibold leading-5 text-late-ink tnum" aria-label={`${n} ждут решения`}>
      {n}
    </span>
  );
}

function SideNav() {
  const nav = useNav();
  return (
    <nav aria-label="Разделы" className="grid gap-0.5">
      {nav.map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          end={n.to === "/"}
          className={({ isActive }) =>
            cn(
              "flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] font-medium text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink [&_svg]:size-4",
              isActive && "bg-surface-2 text-ink [&_svg]:text-accent-ink",
            )
          }
        >
          <n.icon />
          {n.label}
          {n.to === "/inbox" ? <InboxCount /> : null}
        </NavLink>
      ))}
    </nav>
  );
}

function MobileNav() {
  const nav = useNav();
  const [more, setMore] = useState(false);
  const location = useLocation();
  const main = nav.filter((n) => n.mobile);
  const rest = nav.filter((n) => !n.mobile);
  const restActive = rest.some((n) => location.pathname.startsWith(n.to));
  return (
    <>
      {more ? (
        <div className="fixed inset-x-2 bottom-[calc(4rem+env(safe-area-inset-bottom))] z-40 grid gap-0.5 rounded-lg border border-line bg-surface p-1.5 shadow-panel lg:hidden">
          {rest.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              onClick={() => setMore(false)}
              className="flex h-10 items-center gap-3 rounded-md px-3 text-[14px] text-ink hover:bg-surface-2 [&_svg]:size-4 [&_svg]:text-ink-3"
            >
              <n.icon /> {n.label}
              {n.to === "/inbox" ? <InboxCount /> : null}
            </NavLink>
          ))}
        </div>
      ) : null}
      <nav
        aria-label="Разделы"
        className="no-print fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
      >
        {main.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === "/"}
            onClick={() => setMore(false)}
            className={({ isActive }) =>
              cn(
                "flex h-14 flex-col items-center justify-center gap-0.5 text-[11px] text-ink-3 [&_svg]:size-5",
                isActive && "text-accent-ink",
              )
            }
          >
            <n.icon />
            {n.label}
          </NavLink>
        ))}
        <button
          type="button"
          onClick={() => setMore((v) => !v)}
          aria-expanded={more}
          className={cn(
            "flex h-14 flex-col items-center justify-center gap-0.5 text-[11px] text-ink-3 [&_svg]:size-5",
            (more || restActive) && "text-accent-ink",
          )}
        >
          <MoreHorizontal />
          Ещё
        </button>
      </nav>
    </>
  );
}

export function AppShell() {
  useRealtime();
  const palette = useCommandPalette();
  const meta = useMeta().data;
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[232px_1fr]">
      <aside className="no-print hidden border-r border-line bg-surface lg:block">
        <div className="sticky top-0 flex h-dvh flex-col px-3 py-4">
        <div className="mb-5 px-2.5">
          <Logo />
        </div>
        <button
          type="button"
          onClick={() => palette.setOpen(true)}
          className="mb-4 flex h-8 items-center gap-2 rounded-md border border-line bg-bg px-2.5 text-[13px] text-ink-3 hover:border-line-strong"
        >
          <Search className="size-4" /> Поиск
          <kbd className="ml-auto text-[11px]">⌘K</kbd>
        </button>
        <SideNav />
        <div className="mt-auto flex items-center justify-between gap-2 border-t border-line px-1 pt-3">
          <ConnectionDot />
          <div className="flex items-center">
            <ThemeMenu />
            <AdminButton />
          </div>
        </div>
        {meta ? (
          <p className="mt-2 px-1 text-[11px] text-ink-3 tnum" title="Версия xTime на сервере">
            xTime {meta.version}
          </p>
        ) : null}
        {meta?.demo ? (
          <p className="mt-3 rounded-md bg-surface-2 px-2.5 py-2 text-[12px] leading-4 text-ink-2">
            Демо: вымышленная команда, данные сгенерированы.
          </p>
        ) : null}
        </div>
      </aside>

      <div className="min-w-0">
        <header className="no-print sticky top-0 z-30 flex h-12 items-center justify-between border-b border-line bg-surface/95 px-4 backdrop-blur lg:hidden">
          <Logo />
          <div className="flex items-center">
            <Button variant="ghost" size="icon" aria-label="Поиск" onClick={() => palette.setOpen(true)}>
              <Search />
            </Button>
            <ThemeMenu />
            <AdminButton />
          </div>
        </header>
        <main className="px-4 pb-24 pt-5 sm:px-6 lg:px-8 lg:pb-10 lg:pt-7">
          <Outlet />
        </main>
      </div>
      <MobileNav />
      <CommandPalette open={palette.open} onOpenChange={palette.setOpen} />
    </div>
  );
}
