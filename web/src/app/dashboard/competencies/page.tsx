"use client";

import { useState } from "react";

import { Alert, Button, Select, Spinner } from "@/components/ui";
import { type Competency, content, marketplace } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorText, useLoad } from "@/lib/hooks";

const INPUT = "h-9 min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 text-sm outline-none focus:border-brand";

/** Справочник компетенций для заявок учеников — ведут модераторы (ТЗ, раздел 4). */
export default function CompetenciesPage() {
  const { user } = useAuth();
  const staff = !!user?.roles.some((r) => r === "moderator" || r === "admin");
  const subjects = useLoad(() => content.subjects(), []);
  const [subjectId, setSubjectId] = useState("");
  const current = subjectId || subjects.data?.[0]?.id || "";
  const list = useLoad(async () => (current ? marketplace.competencies(current) : []), [current]);
  const [title, setTitle] = useState("");
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
  if (!subjects.data) return <Spinner />;
  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Компетенции</h1>
        <p className="mt-1 text-sm text-fg-soft">Из этого списка ученик выбирает в заявке «Что уже знаю» и «Что хочу получить».</p>
      </div>
      <Select label="Предмет" value={current} onChange={(e) => setSubjectId(e.target.value)}>
        {subjects.data.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </Select>
      {error && <Alert>{error}</Alert>}
      <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
        {list.data?.map((c) => <Row key={c.id} c={c} act={act} />)}
        <li className="px-4 py-3">
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (title.trim()) act(async () => {
                await marketplace.createCompetency(current, title.trim());
                setTitle("");
              });
            }}
          >
            <input value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} placeholder="Новая компетенция" aria-label="Новая компетенция" className={INPUT} />
            <Button type="submit" variant="secondary" className="h-9" disabled={!title.trim()}>
              Добавить
            </Button>
          </form>
        </li>
      </ul>
    </div>
  );
}

function Row({ c, act }: { c: Competency; act: (a: () => Promise<unknown>) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(c.title);
  return (
    <li className="flex items-center gap-2 px-4 py-2.5 text-sm">
      {editing ? (
        <form
          className="flex flex-1 gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            act(() => marketplace.updateCompetency(c.id, { title })).then(() => setEditing(false));
          }}
        >
          <input autoFocus value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} className={INPUT} aria-label="Название" />
          <Button type="submit" className="h-9">
            Сохранить
          </Button>
        </form>
      ) : (
        <>
          <span className="min-w-0 flex-1">{c.title}</span>
          <button className="text-fg-soft hover:text-fg" onClick={() => setEditing(true)}>
            Переименовать
          </button>
          <button className="text-fg-soft hover:text-danger" onClick={() => act(() => marketplace.deleteCompetency(c.id))} aria-label={`Удалить «${c.title}»`}>
            ✕
          </button>
        </>
      )}
    </li>
  );
}
