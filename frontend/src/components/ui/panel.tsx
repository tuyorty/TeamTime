import type * as React from "react";

import { cn } from "@/lib/cn";

/** Панель с заголовком: каждая отвечает на один вопрос (принцип Grafana). */
export function Panel({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn("rounded-lg border border-line bg-surface", className)}>
      {title || actions ? (
        <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-4 pt-3.5 pb-2">
          <div className="min-w-0">
            {title ? <h2 className="text-[15px] font-semibold">{title}</h2> : null}
            {description ? <p className="mt-0.5 text-[12px] text-ink-3">{description}</p> : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        </header>
      ) : null}
      <div className={cn("px-4 pb-4", !title && !actions && "pt-4", bodyClassName)}>{children}</div>
    </section>
  );
}
