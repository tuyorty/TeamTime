import { useState } from "react";

import type { EmployeeBrief } from "@/api/types";
import { cn } from "@/lib/cn";
import { employeeColor, initials } from "@/lib/colors";
import { useTheme } from "@/lib/theme";

export function Avatar({
  employee,
  size = 24,
  className,
}: {
  employee: EmployeeBrief;
  size?: number;
  className?: string;
}) {
  const { isDark } = useTheme();
  const color = employeeColor(employee.color, employee.id, isDark);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const photo = employee.avatar_url && employee.avatar_url !== failedUrl ? employee.avatar_url : null;
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full font-semibold text-ink",
        className,
      )}
      style={{
        width: size,
        height: size,
        fontSize: size * 0.42,
        background: `color-mix(in oklab, ${color} 22%, var(--surface))`,
        boxShadow: `inset 0 0 0 1.5px ${color}`,
      }}
    >
      {photo ? (
        <img src={photo} alt="" className="size-full object-cover" onError={() => setFailedUrl(photo)} />
      ) : (
        initials(employee.short_name)
      )}
    </span>
  );
}
