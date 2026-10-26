import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";

import { cn } from "@/lib/cn";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-sm px-1.5 py-px text-[12px] font-medium leading-5 whitespace-nowrap [&_svg]:size-3.5",
  {
    variants: {
      tone: {
        neutral: "bg-surface-2 text-ink-2",
        accent: "bg-accent-soft text-accent-ink",
        late: "bg-late-soft text-late-ink",
        absence: "bg-absence-soft text-absence-ink",
        deviation: "bg-deviation-soft text-deviation-ink",
        outline: "border border-line text-ink-2",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({
  className,
  tone,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
