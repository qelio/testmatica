"use client";

import Link from "next/link";
import { useState } from "react";

import { TaskNumber } from "@/components/task-number";
import { PreviewToggle, TaskPreview } from "@/components/task-preview";
import { Badge } from "@/components/ui";
import type { Quiz } from "@/lib/api";
import { fmtLimit } from "@/lib/assignments";
import { TASK_TYPE_LABELS } from "@/lib/format";

/** Чужой тест — автора курса (решение №46) или коллеги (№58): только просмотр — состав, условия и ответы; назначить можно. */
export function TestView({ test }: { test: Quiz }) {
  const [opened, setOpened] = useState<Set<string>>(new Set());
  const toggle = (id: string) =>
    setOpened((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const limit = fmtLimit(test);
  return (
    <div className="space-y-5">
      <section className="space-y-2 rounded-2xl border border-line bg-surface p-5">
        <div className="flex flex-wrap items-center gap-2">
          {test.shared_with_me ? (
            <Badge tone="brand">тест коллеги · {test.owner_name}</Badge>
          ) : (
            <Badge tone={test.visibility === "public" ? "ok" : "brand"}>{test.visibility === "public" ? "публичный" : "для педагогов"}</Badge>
          )}
          {test.grade_level && <span className="text-sm text-fg-soft">{test.grade_level} класс</span>}
        </div>
        {test.module && (
          <p className="text-sm">
            Модуль курса:{" "}
            <Link href={`/dashboard/library/module/${test.module.id}`} className="text-brand hover:underline">
              {test.module.course_title ? `${test.module.course_title} → ` : ""}
              {test.module.title}
            </Link>
          </p>
        )}
        {test.description && <p className="whitespace-pre-line text-sm">{test.description}</p>}
        <p className="text-sm text-fg-soft">
          {test.shared_with_me
            ? "Тестом поделился коллега — его можно посмотреть, назначить своим ученикам и классам и поделиться дальше, но не изменить."
            : "Тест автора курса — его можно посмотреть и назначить своим ученикам, но не изменить."}
          {limit && ` Время: ${limit}.`}
        </p>
        {test.items.length > 0 && (
          <Link
            href={`/dashboard/assignments/new?test=${test.id}`}
            className="inline-block rounded-xl bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-strong"
          >
            Назначить
          </Link>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-lg font-semibold">Задания</h2>
          <span className="text-sm text-fg-soft">
            {test.items.length} · всего баллов: {test.max_score}
          </span>
        </div>
        {test.items.length > 0 && (
          <ol className="divide-y divide-line rounded-2xl border border-line bg-surface">
            {test.items.map((item, i) => (
              <li key={item.task_id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
                <span className="w-6 text-right text-sm text-fg-soft tabular-nums">{i + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">
                    <TaskNumber n={item.task.number} />
                    {item.task.title}
                  </span>
                  <span className="block text-xs text-fg-soft">
                    {TASK_TYPE_LABELS[item.task.type]}
                    {item.solution_file && " · файл с решением"}
                  </span>
                </span>
                <span className="text-sm text-fg-soft">баллы: {item.points}</span>
                <PreviewToggle open={opened.has(item.task_id)} onToggle={() => toggle(item.task_id)} />
                {opened.has(item.task_id) && (
                  <div className="w-full">
                    <TaskPreview taskId={item.task_id} />
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
