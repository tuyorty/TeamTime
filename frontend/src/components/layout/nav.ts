import {
  CalendarDays, CalendarRange, ClipboardList, Inbox, LayoutGrid, MessagesSquare, Settings2,
  Sun, Users, Wallet, type LucideIcon,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Показывать в нижней панели на телефоне. */
  mobile?: boolean;
  demoOnly?: boolean;
  /** Только в режиме админа. */
  adminOnly?: boolean;
}

export const NAV: NavItem[] = [
  { to: "/", label: "Сегодня", icon: Sun, mobile: true },
  { to: "/week", label: "Неделя", icon: LayoutGrid, mobile: true },
  { to: "/month", label: "Месяц", icon: CalendarRange, mobile: true },
  { to: "/finances", label: "Финансы", icon: Wallet },
  { to: "/people", label: "Люди", icon: Users, mobile: true },
  { to: "/plans", label: "Планы", icon: ClipboardList },
  { to: "/calendar", label: "Календарь", icon: CalendarDays },
  { to: "/inbox", label: "Инбокс", icon: Inbox },
  { to: "/admin", label: "Админка", icon: Settings2, adminOnly: true },
  { to: "/demo", label: "Эмулятор чата", icon: MessagesSquare, demoOnly: true },
];
