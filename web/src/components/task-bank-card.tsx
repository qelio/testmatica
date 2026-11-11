"use client";

import Link from "next/link";
import { useState } from "react";

import { STATUS_LABELS } from "@/components/course-view";
import { ExamChips } from "@/components/exams";
import { Markdown } from "@/components/markdown";
import { TaskNumber } from "@/components/task-number";
import { topicLabel } from "@/components/topics";
import { Badge } from "@/components/ui";
import type { TaskFull } from "@/lib/api";
import { DIFFICULTY_LABELS, TASK_TYPE_LABELS } from "@/lib/format";

/** Задача в банке — сразу с полным условием; решение (верный ответ и разбор) — по ссылке «Показать решение».
 *  Название ведёт на страницу задачи. */
export function TaskBankCard({ task, scope }: { task: TaskFull; scope: "public" | "mine" }) {
  const [open, setOpen] = useState(false);
  const answers = task.answers?.length ? task.answers.map((a) => (a.mode === "regex" ? `/${a.value}/` : a.value)).join(", ") : null;
  const hasSolution = !!task.explanation || !!answers || task.options.some((o) => o.is_correct) || !!task.tests?.length;
  return (
    <article className="space-y-3 rounded-2xl border border-line bg-surface p-5">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Link href={`/dashboard/tasks/${task.id}`} className="min-w-0 basis-full font-medium hover:text-brand-text hover:underline">
          <TaskNumber n={task.number} />
          {task.title}
        </Link>
        <ExamChips labels={task.exam_items} />
        <Badge tone="brand">{TASK_TYPE_LABELS[task.type]}</Badge>
        <Badge>{DIFFICULTY_LABELS[task.difficulty]}</Badge>
        {scope === "mine" && task.status !== "private" && (
          <Badge tone={STATUS_LABELS[task.status].tone}>{STATUS_LABELS[task.status].text}</Badge>
        )}
        <span className="w-full text-xs text-fg-soft">
          {[task.topic_path.length ? topicLabel(task.topic_path, task.subject_name) : "без темы", scope === "public" ? task.author_name : null, task.tags.join(", ")]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </header>

      <div className="text-[15px]">
        <Markdown text={task.statement} />
      </div>
      {task.type === "choice" && (
        <ul className="space-y-1 text-sm">
          {task.options.map((o) => {
            const right = open && o.is_correct;
            return (
              <li key={o.id} className={`flex items-start gap-2 rounded-lg px-2 py-1 ${right ? "bg-ok/10" : ""}`}>
                <span className={`w-4 shrink-0 ${right ? "text-ok" : "text-fg-soft"}`}>{right ? "✓" : "•"}</span>
                <span className="min-w-0 flex-1">
                  <Markdown text={o.text} />
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {hasSolution && (
        <div className="space-y-2">
          <button type="button" onClick={() => setOpen(!open)} className="text-sm text-brand-text hover:underline" aria-expanded={open}>
            {open ? "Скрыть решение" : "Показать решение"}
          </button>
          {open && (
            <div className="space-y-2 rounded-xl border border-ok/30 bg-ok/5 px-4 py-3 text-sm">
              {answers && (
                <p>
                  <span className="font-medium">Ответ:</span> {answers}
                </p>
              )}
              {task.type === "choice" && <p className="text-fg-soft">Верные варианты отмечены ✓ выше.</p>}
              {task.type === "code" && !!task.tests?.length && (
                <p className="text-fg-soft">Проверяется тестами: {task.tests.length}. Пример — на входе «{task.tests[0].input}», ответ «{task.tests[0].expected}».</p>
              )}
              {task.explanation ? (
                <div>
                  <p className="font-medium">Разбор</p>
                  <Markdown text={task.explanation} />
                </div>
              ) : (
                !answers && task.type !== "choice" && <p className="text-fg-soft">Разбора к задаче нет.</p>
              )}
            </div>
          )}
        </div>
      )}
    </article>
  );
}
