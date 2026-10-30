import { Lock } from "lucide-react";
import { useNavigate, useParams } from "react-router";

import { EmptyState } from "@/components/domain/feedback";
import { PageHeader } from "@/components/layout/PageHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useIsAdmin } from "@/hooks/useIsAdmin";

import { AuditTab } from "./admin/AuditTab";
import { EmployeesTab } from "./admin/EmployeesTab";
import { ImportTab } from "./admin/ImportTab";
import { SettingsTab } from "./admin/SettingsTab";
import { TelegramTab } from "./admin/TelegramTab";
import { SystemTab } from "./admin/SystemTab";

const TABS = [
  { value: "employees", label: "Сотрудники", admin: true },
  { value: "telegram", label: "Telegram", admin: true },
  { value: "settings", label: "Настройки", admin: true },
  { value: "system", label: "Состояние системы", admin: true },
  { value: "import", label: "Импорт", admin: true },
  { value: "audit", label: "Журнал правок", admin: false },
] as const;

export default function AdminPage() {
  const admin = useIsAdmin();
  const navigate = useNavigate();
  const tab = useParams().tab ?? (admin ? "employees" : "audit");

  return (
    <div className="grid min-w-0 grid-cols-1 gap-5">
      <PageHeader
        title="Админка"
        subtitle="Справочник, привязки Telegram, настройки расчётов, импорт истории и журнал правок"
      />
      <Tabs value={tab} onValueChange={(v) => navigate(`/admin/${v}`)}>
        <TabsList className="max-w-full overflow-x-auto">
          {TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {TABS.map((t) => (
          <TabsContent key={t.value} value={t.value} className="pt-5">
            {t.admin && !admin ? (
              <EmptyState icon={Lock} title="Нужен режим админа">
                Смотреть таблицу можно всем, а менять справочник и настройки — только в режиме админа. Нажмите на замок
                в меню и введите пароль из ADMIN_PASSWORD.
              </EmptyState>
            ) : t.value === "employees" ? (
              <EmployeesTab />
            ) : t.value === "telegram" ? (
              <TelegramTab />
            ) : t.value === "settings" ? (
              <SettingsTab />
            ) : t.value === "system" ? (
              <SystemTab />
            ) : t.value === "import" ? (
              <ImportTab />
            ) : (
              <AuditTab />
            )}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
