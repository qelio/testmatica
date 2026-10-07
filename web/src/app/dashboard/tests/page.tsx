"use client";

import Link from "next/link";
import { useState } from "react";

import { GradeFilter } from "@/components/grade-filter";
import { Alert, EmptyState, Spinner } from "@/components/ui";
import { assessment } from "@/lib/api";
import { fmtLimit, gradeLevelLabel, matchesGrade } from "@/lib/assignments";
import { useAuth } from "@/lib/auth";
import { useLoad } from "@/lib/hooks";

/** Мои тесты: наборы задач из банка с настройками. Назначают их в разделе «Назначение тестов». */
export default function TestsPage() {
  const tests = useLoad(() => assessment.tests(), []);
  // Назначают педагоги; штатные редакторы готовят тесты к курсам библиотеки.
  const canAssign = !!useAuth().user?.roles.includes("teacher");
  const [grade, setGrade] = useState("");
  const shown = tests.data?.filter((t) => matchesGrade(t.grade_level, grade)) ?? [];
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Тесты</h1>
        <div className="flex gap-2">
          <Link href="/dashboard/tasks" className="rounded-xl border border-line px-4 py-2.5 text-sm font-medium hover:bg-muted">
            Банк задач
          </Link>
          <Link href="/dashboard/tests/new" className="rounded-xl bg-brand px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-strong">
            Новый тест
          </Link>
        </div>
      </div>
      {tests.error && <Alert>{tests.error}</Alert>}
      {!!tests.data?.length && (
        <div className="flex flex-wrap items-center gap-3">
          <GradeFilter value={grade} onChange={setGrade} withNone={tests.data.some((t) => !t.grade_level)} />
          {grade && <span className="text-sm text-fg-soft">Найдено: {shown.length}</span>}
        </div>
      )}
      {!tests.data ? (
        !tests.error && <Spinner />
      ) : !tests.data.length ? (
        <EmptyState title="Тестов пока нет" text="Тест — это набор задач из банка с настройками: порядок, таймер, баллы." />
      ) : (
        <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
          {!shown.length && <li className="px-5 py-4 text-sm text-fg-soft">Тестов для этого класса нет.</li>}
          {shown.map((t) => (
            <li key={t.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-5 py-3 hover:bg-muted">
              <Link href={`/dashboard/tests/${t.id}`} className="min-w-0 flex-1">
                <span className="font-medium">{t.title}</span>
                <span className="block text-sm text-fg-soft">
                  {[gradeLevelLabel(t.grade_level), `заданий: ${t.tasks_count}`, `баллов: ${t.max_score}`, fmtLimit(t), t.assignments_count ? `назначен ${t.assignments_count} раз` : null]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
                {t.module && (
                  <span className="block truncate text-sm text-brand">
                    {t.module.course_title} → {t.module.title}
                    {t.shared ? " · для всех" : " · только ваш"}
                  </span>
                )}
              </Link>
              {canAssign && t.tasks_count > 0 && (
                <Link href={`/dashboard/assignments/new?test=${t.id}`} className="text-sm font-medium text-brand hover:underline">
                  Назначить
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
