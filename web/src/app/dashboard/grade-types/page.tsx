"use client";

import { useState } from "react";

import { Alert, Badge, Button, Field, Spinner } from "@/components/ui";
import { academic } from "@/lib/api";
import { errorText, useLoad } from "@/lib/hooks";

/** Справочник типов оценок — ведёт модератор (ТЗ, раздел 8). */
export default function GradeTypesPage() {
  const types = useLoad(() => academic.gradeTypes(true), []);
  const [name, setName] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(undefined);
    try {
      await action();
      types.reload();
      return true;
    } catch (e) {
      setError(errorText(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Типы оценок</h1>
        <p className="mt-1 text-fg-soft">Педагоги выбирают тип при выставлении оценки. Веса у типов нет.</p>
      </div>
      {(error || types.error) && <Alert>{error ?? types.error}</Alert>}
      <form
        className="flex items-end gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          const position = (types.data?.length ?? 0) + 1;
          if (await act(() => academic.createGradeType(name, position))) setName("");
        }}
      >
        <div className="flex-1">
          <Field label="Новый тип" required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <Button type="submit" loading={busy} disabled={!name.trim()}>
          Добавить
        </Button>
      </form>
      {!types.data ? (
        <Spinner />
      ) : (
        <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
          {types.data.map((t) => (
            <li key={t.id} className="flex items-center gap-3 px-5 py-3">
              <span className={`flex-1 ${t.is_active ? "" : "text-fg-soft line-through"}`}>{t.name}</span>
              {!t.is_active && <Badge>скрыт</Badge>}
              <Button
                variant="ghost"
                className="h-9"
                disabled={busy}
                onClick={() => act(() => academic.updateGradeType(t.id, { is_active: !t.is_active }))}
              >
                {t.is_active ? "Скрыть" : "Вернуть"}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
