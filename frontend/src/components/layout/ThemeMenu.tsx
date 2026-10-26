import { Monitor, Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dropdown, DropdownContent, DropdownRadioGroup, DropdownRadioItem, DropdownTrigger,
} from "@/components/ui/dropdown";
import { useTheme, type ThemePref } from "@/lib/theme";

const OPTIONS: { value: ThemePref; label: string; icon: typeof Sun }[] = [
  { value: "system", label: "Как в системе", icon: Monitor },
  { value: "light", label: "Светлая", icon: Sun },
  { value: "dark", label: "Тёмная", icon: Moon },
];

export function ThemeMenu() {
  const { pref, setPref, isDark } = useTheme();
  const Icon = pref === "system" ? Monitor : isDark ? Moon : Sun;
  return (
    <Dropdown>
      <DropdownTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Тема оформления">
          <Icon />
        </Button>
      </DropdownTrigger>
      <DropdownContent>
        <DropdownRadioGroup value={pref} onValueChange={(v) => setPref(v as ThemePref)}>
          {OPTIONS.map((o) => (
            <DropdownRadioItem key={o.value} value={o.value}>
              <o.icon /> {o.label}
            </DropdownRadioItem>
          ))}
        </DropdownRadioGroup>
      </DropdownContent>
    </Dropdown>
  );
}
