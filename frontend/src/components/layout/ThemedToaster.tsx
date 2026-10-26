import { Toaster } from "sonner";

import { useTheme } from "@/lib/theme";

export function ThemedToaster() {
  const { isDark } = useTheme();
  return (
    <Toaster
      theme={isDark ? "dark" : "light"}
      position="bottom-right"
      containerAriaLabel="Уведомления"
      offset={{ bottom: 24, right: 24 }}
      mobileOffset={{ bottom: 80 }}
      toastOptions={{
        classNames: {
          toast: "!bg-surface !text-ink !border-line !shadow-panel !font-sans",
          description: "!text-ink-2",
        },
      }}
    />
  );
}
