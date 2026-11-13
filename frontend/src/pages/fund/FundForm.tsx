import { requestId } from "@/lib/request-id";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/field";

import type { FormSpec } from "./formTypes";

/** Один идентификатор на весь диалог: повтор запроса после ошибки не создаёт дубль. */
export function FundForm({
  spec,
  onClose,
}: {
  spec: FormSpec;
  onClose: () => void;
}) {
  const [id] = useState(requestId);
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      spec.fields.map((f) => [
        f.name,
        f.value ?? (f.type === "select" ? f.options?.[0]?.value : "") ?? "",
      ]),
    ),
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const cache = useQueryClient();
  return (
    <Dialog
      open
      onOpenChange={(v) => {
        if (!v && !busy) onClose();
      }}
    >
      <DialogContent
        title={spec.title}
        description={spec.description}
        className="top-[5vh] max-h-[90dvh] overflow-y-auto"
      >
        <form
          className="grid gap-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              const body = spec.body(values, id);
              const result = await api[spec.method ?? "post"]<
                Record<string, unknown>
              >(spec.path, body);
              await spec.after?.(result);
              await cache.invalidateQueries({ queryKey: ["fund"] });
              await cache.invalidateQueries({ queryKey: ["team-session"] });
              onClose();
            } catch (err) {
              setError((err as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {spec.fields
            .filter((f) => !f.when || f.when(values))
            .map((f) =>
              f.type === "checkbox" ? (
                <label key={f.name} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={values[f.name] === "true"}
                    onChange={(e) =>
                      setValues({
                        ...values,
                        [f.name]: String(e.target.checked),
                      })
                    }
                  />
                  {f.label}
                </label>
              ) : (
                <Field key={f.name} label={f.label} hint={f.hint}>
                  {f.type === "select" ? (
                    <Select
                      value={values[f.name]}
                      onChange={(e) =>
                        setValues({ ...values, [f.name]: e.target.value })
                      }
                    >
                      {f.options?.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </Select>
                  ) : f.type === "textarea" ? (
                    <Textarea
                      required={!f.optional}
                      value={values[f.name]}
                      onChange={(e) =>
                        setValues({ ...values, [f.name]: e.target.value })
                      }
                    />
                  ) : (
                    <Input
                      required={!f.optional}
                      type={f.type ?? "text"}
                      value={values[f.name]}
                      min={f.min}
                      max={f.max}
                      step={
                        f.step ?? (f.type === "number" ? "0.01" : undefined)
                      }
                      onChange={(e) =>
                        setValues({ ...values, [f.name]: e.target.value })
                      }
                    />
                  )}
                </Field>
              ),
            )}
          {error && (
            <p
              role="alert"
              className="rounded-lg bg-late-soft p-3 text-sm text-late-ink"
            >
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2 border-t border-line pt-4">
            <Button type="button" disabled={busy} onClick={onClose}>
              Отмена
            </Button>
            <Button type="submit" variant="primary" disabled={busy}>
              {busy ? "Сохраняем…" : (spec.submit ?? "Сохранить")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
