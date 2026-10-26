import type { EmployeeBrief } from "@/api/types";
import { cn } from "@/lib/cn";
import { employeeColor, initials } from "@/lib/colors";
import { useTheme } from "@/lib/theme";

export function Avatar({ employee, size = 24, className }: { employee: EmployeeBrief; size?: number; className?: string }) {
  const { isDark } = useTheme();
  const color = employeeColor(employee.color, employee.id, isDark);
  return (
    <span
      aria-hidden
      className={cn("inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-ink", className)}
      style={{
        width: size,
        height: size,
        fontSize: size * 0.42,
        background: `color-mix(in oklab, ${color} 22%, var(--surface))`,
        boxShadow: `inset 0 0 0 1.5px ${color}`,
      }}
    >
      {initials(employee.short_name)}
    </span>
  );
}
