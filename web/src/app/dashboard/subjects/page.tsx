"use client";

import { useState } from "react";

import { Alert, Badge, Button, Spinner } from "@/components/ui";
import { content, type SubjectRef } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorText, useLoad } from "@/lib/hooks";

const INPUT = "h-9 min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 text-sm outline-none focus:border-brand";

/** Справочник предметов платформы. Удалить нельзя (на предмет ссылаются курсы, задачи, профили) — только скрыть. */
export default function SubjectsPage() {
  const { user } = useAuth();
  const staff = !!user?.roles.some((r) => r === "moderator" || r === "admin");
  const list = useLoad(() => content.allSubjects(), []);
  const [name, setName] = useState("");
  const [error, setError] = useState<string>();

  async function act(action: () => Promise<unknown>) {
    setError(undefined);
    try {
      await action();
      list.reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  if (!staff) return <Alert>Справочник ведут модераторы.</Alert>;
  if (!list.data) return list.error ? <Alert>{list.error}</Alert> : <Spinner />;
  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Предметы</h1>
        <p className="mt-1 text-sm text-fg-soft">
          Из этого списка выбирают предмет в группах, занятиях, курсах, банке задач и профилях репетиторов. Переименование обновит название везде;
          ненужный предмет можно скрыть из выбора.
        </p>
      </div>
      {error && <Alert>{error}</Alert>}
      <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
        {list.data.map((s) => (
          <Row key={s.id} s={s} act={act} />
        ))}
        <li className="px-4 py-3">
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim())
                act(async () => {
                  await content.createSubject(name.trim());
                  setName("");
                });
            }}
          >
            <input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} placeholder="Новый предмет" aria-label="Новый предмет" className={INPUT} />
            <Button type="submit" variant="secondary" className="h-9" disabled={!name.trim()}>
              Добавить
            </Button>
          </form>
        </li>
      </ul>
    </div>
  );
}

function Row({ s, act }: { s: SubjectRef; act: (a: () => Promise<unknown>) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(s.name);
  return (
    <li className="flex items-center gap-2 px-4 py-2.5 text-sm">
      {editing ? (
        <form
          className="flex flex-1 gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            act(() => content.updateSubject(s.id, { name })).then(() => setEditing(false));
          }}
        >
          <input autoFocus value={name} maxLength={80} onChange={(e) => setName(e.target.value)} className={INPUT} aria-label="Название" />
          <Button type="submit" className="h-9">
            Сохранить
          </Button>
          <Button type="button" variant="ghost" className="h-9" onClick={() => setEditing(false)}>
            Отмена
          </Button>
        </form>
      ) : (
        <>
          <span className={`min-w-0 flex-1 ${s.hidden ? "text-fg-soft" : ""}`}>{s.name}</span>
          {s.hidden && <Badge>скрыт</Badge>}
          <button className="text-fg-soft hover:text-fg" onClick={() => setEditing(true)}>
            Переименовать
          </button>
          <button className="text-fg-soft hover:text-fg" onClick={() => act(() => content.updateSubject(s.id, { hidden: !s.hidden }))}>
            {s.hidden ? "Показать" : "Скрыть"}
          </button>
        </>
      )}
    </li>
  );
}
