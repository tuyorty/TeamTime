import { ChevronDown, ChevronUp } from "lucide-react";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

/** Короткое превью, а полный список прокручивается внутри ограниченного по высоте блока. */
export function TaskList({
  tasks,
  columns = 1,
  numbered = false,
  previewCount = 4,
  label = "Задачи",
}: {
  tasks: string[];
  columns?: 1 | 2;
  numbered?: boolean;
  previewCount?: number;
  label?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const id = useId();
  const canExpand = tasks.length > previewCount || tasks.some((task) => task.length > 40 || task.includes("\n"));
  const visible = expanded ? tasks : tasks.slice(0, previewCount);
  if (!tasks.length) return null;
  return (
    <div className="grid min-w-0 gap-2">
      <div
        id={id}
        role="region"
        aria-label={label}
        tabIndex={expanded ? 0 : undefined}
        className={cn(
          "min-w-0",
          expanded &&
            "max-h-72 overflow-y-auto rounded-md border border-line bg-surface-2/30 p-3 [scrollbar-gutter:stable]",
        )}
      >
        <ul className={cn("grid min-w-0 gap-x-5 gap-y-2 text-[13px]", columns === 2 && "sm:grid-cols-2")}>
          {visible.map((task, index) => (
            <li key={index} className="flex min-w-0 items-start gap-2">
              {numbered ? (
                <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded bg-accent/8 text-[11px] text-accent-ink tnum">
                  {index + 1}
                </span>
              ) : (
                <span className="mt-2 size-1.5 shrink-0 rounded-full bg-accent/60" />
              )}
              <span
                className={cn(
                  "min-w-0 whitespace-pre-wrap leading-relaxed text-ink-2 [overflow-wrap:anywhere]",
                  !expanded && canExpand && "line-clamp-2",
                )}
              >
                {task}
              </span>
            </li>
          ))}
        </ul>
      </div>
      {canExpand ? (
        <Button
          size="sm"
          variant="ghost"
          className="w-fit text-accent-ink"
          aria-expanded={expanded}
          aria-controls={id}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? <ChevronUp /> : <ChevronDown />}
          {expanded ? "Свернуть задачи" : `Показать все задачи (${tasks.length})`}
        </Button>
      ) : null}
    </div>
  );
}
