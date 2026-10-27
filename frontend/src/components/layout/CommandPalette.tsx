import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { CalendarSearch, ListChecks, Moon, Search, Sun, User } from "lucide-react";
import { Dialog as D } from "radix-ui";
import { useState } from "react";
import { useNavigate } from "react-router";

import { api } from "@/api/client";
import { keys, useMeta } from "@/api/queries";
import type { SearchHit } from "@/api/types";
import { useDebounced } from "@/hooks/useDebounced";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { useTheme } from "@/lib/theme";

import { NAV } from "./nav";

const HIT_ICON = { employee: User, day: CalendarSearch, task: ListChecks, page: Search } as const;

const itemClass =
  "flex cursor-default items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] text-ink data-[selected=true]:bg-surface-2 [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-ink-3";

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const navigate = useNavigate();
  const { setPref, isDark } = useTheme();
  const demo = useMeta().data?.demo ?? false;
  const admin = useIsAdmin();
  const [query, setQuery] = useState("");
  const q = useDebounced(query.trim(), 180);
  const search = useQuery({
    queryKey: keys.search(q),
    queryFn: () => api.get<{ hits: SearchHit[] }>(`/search?q=${encodeURIComponent(q)}`),
    enabled: open && q.length >= 2,
    staleTime: 30_000,
  });

  function go(to: string) {
    onOpenChange(false);
    setQuery("");
    navigate(to);
  }

  const hits = search.data?.hits ?? [];
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-50 bg-black/40" />
        <D.Content className="fixed left-1/2 top-[14vh] z-50 w-[min(94vw,36rem)] -translate-x-1/2 overflow-hidden rounded-lg border border-line bg-surface shadow-panel">
          <D.Title className="sr-only">Поиск и команды</D.Title>
          <D.Description className="sr-only">Люди, дни, задачи и разделы сайта</D.Description>
          <Command shouldFilter={false} label="Поиск и команды" loop>
            <div className="flex items-center gap-2 border-b border-line px-3">
              <Search className="size-4 text-ink-3" />
              <Command.Input
                value={query}
                onValueChange={setQuery}
                placeholder="Человек, дата (23.10), задача или раздел…"
                className="h-11 w-full bg-transparent text-[14px] text-ink outline-none placeholder:text-ink-3"
              />
              <kbd className="hidden rounded border border-line px-1.5 text-[11px] text-ink-3 sm:block">Esc</kbd>
            </div>
            <Command.List className="max-h-[min(60vh,26rem)] overflow-y-auto p-1.5">
              <Command.Empty className="px-3 py-8 text-center text-[13px] text-ink-2">
                {q.length < 2 ? "Начните вводить" : search.isFetching ? "Ищем…" : "Ничего не нашлось"}
              </Command.Empty>
              {hits.length ? (
                <Command.Group heading="Найдено" className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[12px] [&_[cmdk-group-heading]]:text-ink-3">
                  {hits.map((h, i) => {
                    const Icon = HIT_ICON[h.kind];
                    return (
                      <Command.Item key={`${h.href}-${i}`} value={`${h.href}-${i}`} onSelect={() => go(h.href)} className={itemClass}>
                        <Icon />
                        <span className="min-w-0 flex-1 truncate">{h.title}</span>
                        <span className="truncate text-[12px] text-ink-3">{h.subtitle}</span>
                      </Command.Item>
                    );
                  })}
                </Command.Group>
              ) : null}
              {q.length < 2 ? (
                <>
                  <Command.Group heading="Разделы" className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[12px] [&_[cmdk-group-heading]]:text-ink-3">
                    {NAV.filter((n) => (!n.demoOnly || demo) && (!n.adminOnly || admin)).map((n) => (
                      <Command.Item key={n.to} value={n.to} onSelect={() => go(n.to)} className={itemClass}>
                        <n.icon /> {n.label}
                      </Command.Item>
                    ))}
                  </Command.Group>
                  <Command.Group heading="Действия" className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[12px] [&_[cmdk-group-heading]]:text-ink-3">
                    <Command.Item
                      value="theme"
                      onSelect={() => {
                        setPref(isDark ? "light" : "dark");
                        onOpenChange(false);
                      }}
                      className={itemClass}
                    >
                      {isDark ? <Sun /> : <Moon />} {isDark ? "Светлая тема" : "Тёмная тема"}
                    </Command.Item>
                  </Command.Group>
                </>
              ) : null}
            </Command.List>
          </Command>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
