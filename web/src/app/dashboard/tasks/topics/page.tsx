"use client";

import Link from "next/link";
import { useState } from "react";

import { buildRubric, type TopicNode } from "@/components/topics";
import { Alert, Button, EmptyState, Select, Spinner } from "@/components/ui";
import { assessment, content } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorText, useLoad } from "@/lib/hooks";

const INPUT =
  "h-9 min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

/** Рубрикатор банка задач — ведут модераторы: разделы и темы по предметам. */
export default function TopicsPage() {
  const { user } = useAuth();
  const staff = !!user?.roles.some((r) => r === "moderator" || r === "admin");
  const subjects = useLoad(() => content.subjects(), []);
  const topics = useLoad(() => assessment.topics("public"), []);
  const [subjectId, setSubjectId] = useState("");
  const [error, setError] = useState<string>();

  if (!staff) return <Alert>Рубрикатор ведут модераторы.</Alert>;
  if (!subjects.data || !topics.data) return <Spinner />;

  const current = subjectId || subjects.data[0]?.id || "";
  const subject = subjects.data.find((s) => s.id === current);
  const sections = buildRubric(topics.data).find((s) => s.id === current)?.sections ?? [];

  async function act(action: () => Promise<unknown>) {
    setError(undefined);
    try {
      await action();
      topics.reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  /** Поменять местами соседние узлы. */
  const swap = (list: TopicNode[], i: number, j: number) =>
    act(async () => {
      if (j < 0 || j >= list.length) return;
      // Позиции могут совпадать (после удалений) — переписываем подряд.
      const order = list.map((t) => t.id);
      [order[i], order[j]] = [order[j], order[i]];
      await Promise.all(order.map((id, pos) => assessment.updateTopic(id, { position: pos })));
    });

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <Link href="/dashboard/tasks" className="text-sm text-fg-soft hover:text-fg">
        ← Банк задач
      </Link>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Рубрикатор</h1>
        <p className="mt-1 text-sm text-fg-soft">
          Разделы и темы, по которым авторы раскладывают задачи. Удалить можно только пустую тему — задачи сначала переносятся.
        </p>
      </div>
      <Select label="Предмет" value={current} onChange={(e) => setSubjectId(e.target.value)}>
        {subjects.data.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </Select>
      {error && <Alert>{error}</Alert>}

      {sections.length === 0 && <EmptyState title="Разделов пока нет" text="Добавьте первый раздел предмета." />}
      <ol className="space-y-3">
        {sections.map((sec, i) => (
          <li key={sec.id} className="rounded-2xl border border-line bg-surface">
            <div className="border-b border-line px-4 py-2.5">
              <TopicRow
                node={sec}
                strong
                onRename={(title) => act(() => assessment.updateTopic(sec.id, { title }))}
                onDelete={() => act(() => assessment.deleteTopic(sec.id))}
                onUp={i > 0 ? () => swap(sections, i, i - 1) : undefined}
                onDown={i < sections.length - 1 ? () => swap(sections, i, i + 1) : undefined}
              />
            </div>
            <ul className="divide-y divide-line">
              {sec.children.map((t, j) => (
                <li key={t.id} className="py-2 pr-4 pl-8">
                  <TopicRow
                    node={t}
                    onRename={(title) => act(() => assessment.updateTopic(t.id, { title }))}
                    onDelete={() => act(() => assessment.deleteTopic(t.id))}
                    onUp={j > 0 ? () => swap(sec.children, j, j - 1) : undefined}
                    onDown={j < sec.children.length - 1 ? () => swap(sec.children, j, j + 1) : undefined}
                  />
                </li>
              ))}
              <li className="py-2 pr-4 pl-8">
                <AddForm placeholder="Новая тема раздела" onAdd={(title) => act(() => assessment.createTopic({ title, parent_id: sec.id }))} />
              </li>
            </ul>
          </li>
        ))}
      </ol>
      {subject && (
        <div className="rounded-2xl border border-dashed border-line p-4">
          <AddForm
            placeholder={`Новый раздел: ${subject.name}`}
            onAdd={(title) => act(() => assessment.createTopic({ title, subject_id: subject.id, subject_name: subject.name }))}
          />
        </div>
      )}
    </div>
  );
}

function TopicRow({
  node,
  strong,
  onRename,
  onDelete,
  onUp,
  onDown,
}: {
  node: TopicNode;
  strong?: boolean;
  onRename: (title: string) => Promise<void>;
  onDelete: () => void;
  onUp?: () => void;
  onDown?: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(node.title);
  const btn = "px-1.5 text-sm text-fg-soft hover:text-fg disabled:opacity-30";

  if (editing) {
    return (
      <form
        className="flex items-center gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          if (title.trim()) await onRename(title.trim());
          setEditing(false);
        }}
      >
        <input autoFocus value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} className={INPUT} aria-label="Название" />
        <Button type="submit" className="h-9">
          Сохранить
        </Button>
        <Button type="button" variant="ghost" className="h-9" onClick={() => setEditing(false)}>
          Отмена
        </Button>
      </form>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <span className={`min-w-0 flex-1 truncate ${strong ? "font-medium" : "text-sm"}`}>{node.title}</span>
      <span className="text-xs text-fg-soft tabular-nums" title="Опубликованных задач">
        {node.total}
      </span>
      <button className={btn} onClick={onUp} disabled={!onUp} aria-label="Выше">
        ↑
      </button>
      <button className={btn} onClick={onDown} disabled={!onDown} aria-label="Ниже">
        ↓
      </button>
      <button className={btn} onClick={() => setEditing(true)}>
        Переименовать
      </button>
      <button className="px-1.5 text-sm text-fg-soft hover:text-danger" onClick={onDelete} aria-label={`Удалить «${node.title}»`}>
        ✕
      </button>
    </div>
  );
}

function AddForm({ placeholder, onAdd }: { placeholder: string; onAdd: (title: string) => Promise<void> }) {
  const [title, setTitle] = useState("");
  return (
    <form
      className="flex items-center gap-2"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!title.trim()) return;
        await onAdd(title.trim());
        setTitle("");
      }}
    >
      <input value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} placeholder={placeholder} aria-label={placeholder} className={INPUT} />
      <Button type="submit" variant="secondary" className="h-9" disabled={!title.trim()}>
        Добавить
      </Button>
    </form>
  );
}
