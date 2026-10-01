"use client";

import { useState } from "react";

import { ExamChips } from "@/components/exams";
import { TaskEditor } from "@/components/task-editor";
import { buildRubric, topicFilter, topicLabel, TopicSelect } from "@/components/topics";
import { Badge, Button, Modal, Spinner } from "@/components/ui";
import { assessment, type TaskType } from "@/lib/api";
import { DIFFICULTY_LABELS, TASK_TYPE_LABELS } from "@/lib/format";
import { useLoad } from "@/lib/hooks";

/** Выбор задачи для курса: свои задачи или публичный банк; в курсы — только с автопроверкой. */
export function TaskPicker({
  selected,
  onSelect,
  autoOnly = true,
  exclude = [],
}: {
  selected: string | null;
  onSelect: (id: string, title: string, type: TaskType) => void;
  autoOnly?: boolean;
  exclude?: string[];
}) {
  const [scope, setScope] = useState<"mine" | "public">("mine");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [topic, setTopic] = useState("");
  const topics = useLoad(() => assessment.topics(), []);
  const tasks = useLoad(
    () => assessment.search({ scope, q: search, auto_only: autoOnly, ...topicFilter(topic), limit: 30 }),
    [scope, search, topic, autoOnly],
  );

  return (
    <div className="space-y-3 rounded-xl border border-line p-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-lg bg-muted p-0.5 text-sm">
          {(["mine", "public"] as const).map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={scope === s}
              onClick={() => setScope(s)}
              className={`rounded-md px-3 py-1 font-medium ${scope === s ? "bg-surface shadow-sm" : "text-fg-soft"}`}
            >
              {s === "mine" ? "Мои задачи" : "Банк задач"}
            </button>
          ))}
        </div>
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              setSearch(q.trim());
            }
          }}
          placeholder="Поиск по задачам…"
          aria-label="Поиск по задачам"
          className="h-9 min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 text-sm outline-none focus:border-brand"
        />
        <Button type="button" variant="secondary" className="h-9" onClick={() => setCreating(true)}>
          + Новая задача
        </Button>
      </div>
      <TopicSelect rubric={buildRubric(topics.data ?? [])} value={topic} onChange={setTopic} label="Раздел или тема" empty="Все разделы" />
      {autoOnly && (
        <p className="text-xs text-fg-soft">В курсы добавляются только задачи с автопроверкой: выбор ответа, короткий ответ, код.</p>
      )}
      {!tasks.data ? (
        <Spinner />
      ) : tasks.data.items.length === 0 ? (
        <p className="py-3 text-center text-sm text-fg-soft">{scope === "mine" ? "У вас пока нет задач — создайте первую." : "Ничего не найдено."}</p>
      ) : (
        <ul className="max-h-64 divide-y divide-line overflow-y-auto">
          {tasks.data.items.filter((t) => !exclude.includes(t.id)).map((t) => (
            <li key={t.id}>
              <button
                type="button"
                onClick={() => onSelect(t.id, t.title, t.type)}
                aria-pressed={selected === t.id}
                className={`flex w-full items-center gap-2 px-2 py-2 text-left text-sm ${selected === t.id ? "bg-brand/10" : "hover:bg-muted"}`}
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{t.title}</span>
                  {t.topic_path.length > 0 && <span className="block truncate text-xs text-fg-soft">{topicLabel(t.topic_path)}</span>}
                </span>
                <ExamChips labels={t.exam_items} />
                <Badge>{TASK_TYPE_LABELS[t.type]}</Badge>
                <span className="hidden text-xs text-fg-soft sm:inline">{DIFFICULTY_LABELS[t.difficulty]}</span>
                {scope === "public" && <span className="hidden max-w-32 truncate text-xs text-fg-soft sm:inline">{t.author_name}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
      <Modal open={creating} onClose={() => setCreating(false)} title="Новая задача">
        <TaskEditor
          types={autoOnly ? ["choice", "short", "code"] : undefined}
          onCancel={() => setCreating(false)}
          onSaved={(t) => {
            setCreating(false);
            setScope("mine");
            tasks.reload();
            onSelect(t.id, t.title, t.type);
          }}
        />
      </Modal>
    </div>
  );
}
