import { AlertTriangle, RotateCw } from "lucide-react";
import type * as React from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
  className,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center gap-2 px-6 py-12 text-center", className)}>
      {Icon ? <Icon className="mb-1 size-6 text-ink-3" /> : null}
      <p className="font-display text-[15px] font-semibold">{title}</p>
      {children ? <p className="max-w-sm text-[13px] text-ink-2">{children}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message =
    error instanceof ApiError || error instanceof Error ? error.message : "Не удалось загрузить данные";
  return (
    <div role="alert" className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      <AlertTriangle className="mb-1 size-6 text-late" />
      <p className="font-display text-[15px] font-semibold">Данные не загрузились</p>
      <p className="max-w-sm text-[13px] text-ink-2">{message}</p>
      {onRetry ? (
        <Button className="mt-2" onClick={onRetry}>
          <RotateCw /> Повторить
        </Button>
      ) : null}
    </div>
  );
}

/** Подпись про усечение — рядом с итогами, как обещает README. */
export function TruncationNote({ className }: { className?: string }) {
  return <p className={cn("text-[12px] text-ink-3", className)}>Значения усечены до минут.</p>;
}
