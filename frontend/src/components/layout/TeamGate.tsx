import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LogIn, Copy, Check } from "lucide-react";
import { api } from "@/api/client";
import { useTeamSession } from "@/api/fund";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";

export function TeamLogin({ compact = false }: { compact?: boolean }) {
  const session = useTeamSession();
  const cache = useQueryClient();
  const demo = useQuery({
    queryKey: ["team-demo-users"],
    queryFn: () => api.get<{ id: number; name: string }[]>("/team/demo-users"),
    enabled: !!session.data?.demo,
  });
  const [selected, setSelected] = useState("");
  const [request, setRequest] = useState<{
    code: string;
    secret: string;
    command: string;
  }>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!request) return;
    let stopped = false;
    let polling = false;
    const timer = window.setInterval(async () => {
      if (polling) return;
      polling = true;
      try {
        const result = await api.post<{ ready: boolean }>("/team/login/poll", {
          code: request.code,
          secret: request.secret,
        });
        if (!stopped && result.ready) {
          window.clearInterval(timer);
          setRequest(undefined);
          await cache.invalidateQueries();
        }
      } catch (e) {
        if (!stopped) {
          window.clearInterval(timer);
          setError((e as Error).message);
          setRequest(undefined);
        }
      } finally {
        polling = false;
      }
    }, 2500);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [request, cache]);
  async function enter() {
    setBusy(true);
    setError("");
    try {
      if (session.data?.demo) {
        await api.post("/team/demo-login", {
          employee_id: Number(selected || demo.data?.[0]?.id),
        });
        await cache.invalidateQueries();
      } else setRequest(await api.post("/team/login"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className={`${compact ? "" : "mx-auto mt-[10vh] max-w-lg"} rounded-xl border border-line bg-surface p-7 shadow-panel`}
    >
      <div className="mb-4 flex size-11 items-center justify-center rounded-xl bg-accent/10 text-accent">
        <LogIn className="size-6" />
      </div>
      <h1 className="font-display text-2xl font-semibold">Войти в xTime</h1>
      <p className="mt-2 text-sm leading-relaxed text-ink-2">
        Рабочие и финансовые данные доступны участникам команды. Войдите под
        своим именем.
      </p>
      {session.data?.demo ? (
        <div className="mt-5 grid gap-2">
          <label className="text-sm" htmlFor="demo-person">
            Участник демо-команды
          </label>
          <Select
            id="demo-person"
            value={selected || String(demo.data?.[0]?.id ?? "")}
            onChange={(e) => setSelected(e.target.value)}
          >
            {demo.data?.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </Select>
          <p className="text-xs text-ink-3">
            Первый участник — руководитель. Другие роли можно проверить, сменив
            участника.
          </p>
        </div>
      ) : null}
      {request ? (
        <div className="mt-5 grid gap-3">
          <p className="text-sm">
            Отправьте эту команду боту в личные сообщения и подтвердите вход.
            Код действует 5 минут.
          </p>
          <div className="flex items-center gap-2 rounded-lg bg-surface-2 p-3">
            <code className="min-w-0 flex-1 break-all text-sm">
              {request.command}
            </code>
            <Button
              size="icon"
              aria-label="Скопировать команду"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(request.command);
                  setCopied(true);
                } catch {
                  setError("Выделите и скопируйте команду вручную");
                }
              }}
            >
              {copied ? <Check /> : <Copy />}
            </Button>
          </div>
          <p className="text-sm text-ink-2" role="status">
            Ждём подтверждения в Telegram…
          </p>
        </div>
      ) : (
        <Button
          className="mt-5"
          variant="primary"
          onClick={() => void enter()}
          disabled={busy || (!!session.data?.demo && !demo.data?.length)}
        >
          {busy
            ? "Подключение…"
            : session.data?.demo
              ? "Войти в демо"
              : "Получить команду входа"}
        </Button>
      )}
      {error ? (
        <p role="alert" className="mt-3 text-sm text-late">
          {error}
        </p>
      ) : null}
    </section>
  );
}

export function TeamGate({ children }: { children: React.ReactNode }) {
  const session = useTeamSession();
  if (session.isPending)
    return (
      <div className="p-8">
        <Skeleton className="h-56" />
      </div>
    );
  if (session.data?.enabled && !session.data.actor)
    return (
      <div className="min-h-dvh bg-bg p-4">
        <TeamLogin />
      </div>
    );
  return children;
}
