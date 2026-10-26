import { ToggleGroup as TG } from "radix-ui";

import { cn } from "@/lib/cn";

/** Переключатель режимов: «компактно / подробно», «день / неделя». */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  className,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: React.ReactNode; title?: string }[];
  label: string;
  className?: string;
}) {
  return (
    <TG.Root
      type="single"
      value={value}
      onValueChange={(v) => v && onChange(v as T)}
      aria-label={label}
      className={cn("inline-flex rounded-md border border-line bg-surface p-0.5", className)}
    >
      {options.map((o) => (
        <TG.Item
          key={o.value}
          value={o.value}
          title={o.title}
          className="inline-flex h-6 items-center gap-1 rounded-[4px] px-2 text-[12px] font-medium text-ink-2 transition-colors hover:text-ink data-[state=on]:bg-surface-3 data-[state=on]:text-ink [&_svg]:size-3.5"
        >
          {o.label}
        </TG.Item>
      ))}
    </TG.Root>
  );
}
