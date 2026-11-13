import { stateNames } from "./format";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { money } from "@/lib/format";

export function State({ value }: { value: string }) {
  return (
    <Badge
      tone={
        ["posted", "approved", "complete"].includes(value)
          ? "accent"
          : ["pending", "draft", "partial", "unknown"].includes(value)
            ? "deviation"
            : "neutral"
      }
    >
      {stateNames[value] ?? value}
    </Badge>
  );
}
export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`min-w-0 rounded-xl border border-line bg-surface p-4 md:p-5 ${className}`}
    >
      {children}
    </section>
  );
}
export function Stat({
  label,
  amount,
  hint,
  accent = false,
}: {
  label: string;
  amount: string;
  hint?: string;
  accent?: boolean;
}) {
  return (
    <Card>
      <p className="text-xs text-ink-2">{label}</p>
      <p
        className={`tnum mt-2 text-[25px] font-semibold tracking-tight ${accent ? "text-accent" : ""}`}
      >
        {money(amount)}
      </p>
      {hint && <p className="mt-2 text-xs text-ink-3">{hint}</p>}
    </Card>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-8 text-center text-sm text-ink-3">{children}</p>;
}
