"use client";

import { useEffect, useState } from "react";

import { Markdown } from "@/components/markdown";
import { Spinner } from "@/components/ui";
import { assessment, type TaskFull } from "@/lib/api";
import { errorText } from "@/lib/hooks";

/** Кнопка «условие» — раскрыть задачу прямо в списке (выбор задач для теста), не уходя со страницы. */
export function PreviewToggle({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className="shrink-0 rounded-lg px-2 py-1 text-xs text-brand hover:bg-brand/10"
    >
      {open ? "скрыть условие" : "условие"}
    </button>
  );
}

const cache = new Map<string, TaskFull>();

/** Условие задачи и варианты ответа; загружается при первом раскрытии. */
export function TaskPreview({ taskId }: { taskId: string }) {
  const [task, setTask] = useState<TaskFull | undefined>(() => cache.get(taskId));
  const [error, setError] = useState<string>();
  useEffect(() => {
    if (cache.has(taskId)) return;
    let alive = true;
    assessment.task(taskId).then(
      (t) => {
        cache.set(taskId, t);
        if (alive) setTask(t);
      },
      (e) => alive && setError(errorText(e)),
    );
    return () => {
      alive = false;
    };
  }, [taskId]);
  if (error) return <p className="px-3 py-2 text-sm text-danger">{error}</p>;
  if (!task) return <Spinner />;
  return (
    <div className="space-y-2 rounded-xl border border-line bg-muted/40 px-4 py-3 text-sm">
      <Markdown text={task.statement} />
      {task.type === "choice" && (
        <ul className="space-y-1">
          {task.options.map((o) => (
            <li key={o.id} className="flex items-start gap-2">
              <span className={`w-4 shrink-0 ${o.is_correct ? "text-ok" : "text-fg-soft"}`}>{o.is_correct ? "✓" : "•"}</span>
              <span className="min-w-0 flex-1">
                <Markdown text={o.text} />
              </span>
            </li>
          ))}
        </ul>
      )}
      {task.type === "short" && task.answers?.length ? (
        <p className="text-fg-soft">Ответ: {task.answers.map((a) => (a.mode === "regex" ? `/${a.value}/` : a.value)).join(", ")}</p>
      ) : null}
    </div>
  );
}
