import { DropdownMenu as M } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/cn";

export const Dropdown = M.Root;
export const DropdownTrigger = M.Trigger;

export function DropdownContent({ className, ...props }: React.ComponentProps<typeof M.Content>) {
  return (
    <M.Portal>
      <M.Content
        sideOffset={6}
        align="end"
        className={cn("z-50 min-w-44 rounded-md border border-line bg-surface p-1 shadow-panel", className)}
        {...props}
      />
    </M.Portal>
  );
}

export function DropdownItem({ className, ...props }: React.ComponentProps<typeof M.Item>) {
  return (
    <M.Item
      className={cn(
        "flex cursor-default items-center gap-2 rounded-[4px] px-2 py-1.5 text-[13px] text-ink outline-none data-[highlighted]:bg-surface-2 [&_svg]:size-4 [&_svg]:text-ink-3",
        className,
      )}
      {...props}
    />
  );
}

export const DropdownSeparator = () => <M.Separator className="my-1 h-px bg-line" />;
export const DropdownRadioGroup = M.RadioGroup;

export function DropdownRadioItem({ className, children, ...props }: React.ComponentProps<typeof M.RadioItem>) {
  return (
    <M.RadioItem
      className={cn(
        "flex cursor-default items-center gap-2 rounded-[4px] px-2 py-1.5 text-[13px] text-ink outline-none data-[highlighted]:bg-surface-2 data-[state=checked]:font-medium [&_svg]:size-4 [&_svg]:text-ink-3",
        className,
      )}
      {...props}
    >
      {children}
      <M.ItemIndicator className="ml-auto text-accent-ink">•</M.ItemIndicator>
    </M.RadioItem>
  );
}
