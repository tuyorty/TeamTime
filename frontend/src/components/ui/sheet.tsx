import { X } from "lucide-react";
import { Dialog as D } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/cn";

/** Боковая панель для подробностей ячейки и правок. На телефоне выезжает снизу на всю ширину. */
export const Sheet = D.Root;

export function SheetContent({
  className,
  children,
  title,
  subtitle,
  ...props
}: Omit<React.ComponentProps<typeof D.Content>, "title"> & { title: React.ReactNode; subtitle?: React.ReactNode }) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-40 bg-black/30" />
      <D.Content
        className={cn(
          "fixed z-50 flex flex-col border-line bg-surface shadow-panel",
          "inset-x-0 bottom-0 max-h-[88dvh] rounded-t-xl border-t",
          "md:inset-y-0 md:right-0 md:left-auto md:max-h-none md:w-[min(34rem,92vw)] md:rounded-none md:border-l md:border-t-0",
          "transition-transform data-[state=closed]:translate-y-full md:data-[state=closed]:translate-x-full md:data-[state=closed]:translate-y-0",
          className,
        )}
        {...props}
      >
        <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <D.Title className="font-display text-[17px] font-semibold leading-tight">{title}</D.Title>
            <D.Description className={subtitle ? "mt-0.5 text-[13px] text-ink-2" : "sr-only"}>
              {subtitle ?? "Подробности"}
            </D.Description>
          </div>
          <D.Close className="rounded-md p-1 text-ink-3 hover:bg-surface-2 hover:text-ink" aria-label="Закрыть">
            <X className="size-4" />
          </D.Close>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
          {children}
        </div>
      </D.Content>
    </D.Portal>
  );
}
