import { useQueryClient } from "@tanstack/react-query";
import { Lock, LockOpen } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/api/client";
import { useMeta } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/field";
import { Tooltip } from "@/components/ui/tooltip";

export function AdminButton() {
  const meta = useMeta().data;
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!meta?.admin_enabled) return null;

  async function login(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/login", { password });
      await qc.invalidateQueries();
      setOpen(false);
      setPassword("");
      toast.success("Режим админа включён. Правки пишутся в журнал.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось войти");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    await api.post("/auth/logout");
    await qc.invalidateQueries();
    toast("Режим админа выключен");
  }

  if (meta.is_admin) {
    return (
      <Tooltip content="Выключить режим админа">
        <Button variant="ghost" size="sm" onClick={logout} className="text-accent-ink">
          <LockOpen /> <span className="hidden sm:inline">Админ</span>
        </Button>
      </Tooltip>
    );
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Tooltip content="Режим админа: правки и настройки">
        <Button variant="ghost" size="icon" aria-label="Войти в режим админа" onClick={() => setOpen(true)}>
          <Lock />
        </Button>
      </Tooltip>
      <DialogContent
        title="Режим админа"
        description="Смотреть табель можно без входа. Пароль нужен для правок и настроек, все правки пишутся в журнал."
      >
        <form onSubmit={login} className="grid gap-4">
          <Field label="Пароль" error={error} hint={meta.demo ? "В демо пароль: demo" : "Задаётся в ADMIN_PASSWORD"}>
            <Input
              type="password"
              autoFocus
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Отмена
            </Button>
            <Button variant="primary" type="submit" disabled={busy || !password}>
              Войти
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
