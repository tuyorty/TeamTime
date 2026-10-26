import { Tooltip as T } from "radix-ui";
import type * as React from "react";

export const TooltipProvider = T.Provider;

export function Tooltip({
  content,
  children,
  side = "top",
}: {
  content: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "bottom" | "left" | "right";
}) {
  return (
    <T.Root>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content
          side={side}
          sideOffset={6}
          className="z-50 max-w-72 rounded-md border border-line bg-surface px-2.5 py-1.5 text-[12px] text-ink shadow-panel"
        >
          {content}
        </T.Content>
      </T.Portal>
    </T.Root>
  );
}
