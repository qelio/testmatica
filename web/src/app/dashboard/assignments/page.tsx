"use client";

import Link from "next/link";
import { Suspense, useState } from "react";

import { AssignmentCard } from "@/components/assignment-card";
import { GradeFilter } from "@/components/grade-filter";
import { Pager } from "@/components/pager";
import { Badge, EmptyState, Spinner, Alert } from "@/components/ui";
import { assessment } from "@/lib/api";
import { attemptsText, fmtLimit, KIND_LABELS, studentStatus } from "@/lib/assignments";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/dates";
import { useLoad } from "@/lib/hooks";

export default function AssignmentsPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Assignments />
    </Suspense>
  );
}

function Assignments() {
  const { user } = useAuth();
  if (!user) return <Spinner />;
  const teacher = user.roles.some((r) => r === "teacher" || r === "moderator" || r === "admin");
  return teacher ? <TeacherView /> : <StudentView />;
}

function TeacherView() {
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Назначение тестов</h1>
        <div className="flex gap-2">
          <Link href="/dashboard/tests" className="rounded-xl border border-line px-4 py-2.5 text-sm font-medium hover:bg-muted">
            Мои тесты
          </Link>
          <Link href="/dashboard/assignments/new" className="rounded-xl bg-brand px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-strong">
            Назначить тест
          </Link>
        </div>
      </div>
      <Given />
    </div>
  );
}

const PAGE = 20;

function Given() {
  const [grade, setGrade] = useState("");
  const [target, setTarget] = useState("");
  const [page, setPage] = useState(0);
  // Постранично и с фильтрами на сервере: работ бывает много, а каждая — со сводкой по ученикам.
  const list = useLoad(
    () => assessment.assignments("teacher", { grade_level: grade, target_id: target, offset: page * PAGE, limit: PAGE + 1 }),
    [grade, target, page],
  );
  const targets = useLoad(() => assessment.assignmentTargets(), []);
  const filtered = !!(grade || target);
  if (list.error) return <Alert>{list.error}</Alert>;
  if (!list.data) return <Spinner />;
  if (!list.data.length && !filtered && page === 0)
    return (
      <EmptyState
        title="Вы ещё не назначали тесты"
        text="Соберите тест из задач банка в разделе «Тесты» и назначьте его: просто тестом, домашним заданием к уроку или тестом на уроке."
      />
    );
  const shown = list.data.slice(0, PAGE);
  const go = (p: number) => {
    setPage(p);
    window.scrollTo({ top: 0 });
  };
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <GradeFilter
          value={grade}
          onChange={(v) => {
            setGrade(v);
            setPage(0);
          }}
        />
        <select
          value={target}
          onChange={(e) => {
            setTarget(e.target.value);
            setPage(0);
          }}
          aria-label="Кому назначен"
          className="h-10 max-w-full rounded-xl border border-line bg-surface px-3 text-sm outline-none focus:border-brand"
        >
          <option value="">Все группы и ученики</option>
          {(["group", "student"] as const).map((type) => {
            const items = (targets.data ?? []).filter((t) => t.target_type === type);
            return items.length ? (
              <optgroup key={type} label={type === "group" ? "Группы" : "Ученики"}>
                {items.map((t) => (
                  <option key={t.target_id} value={t.target_id}>
                    {t.target_title}
                  </option>
                ))}
              </optgroup>
            ) : null;
          })}
        </select>
      </div>
      {!shown.length && <p className="rounded-2xl border border-line bg-surface px-5 py-4 text-sm text-fg-soft">Ничего не найдено.</p>}
      <ul className="space-y-2">
        {shown.map((a) => (
          <li key={a.id}>
            <AssignmentCard a={a} />
          </li>
        ))}
      </ul>
      <Pager page={page} hasNext={list.data.length > PAGE} onPage={go} />
    </div>
  );
}

function StudentView() {
  const list = useLoad(() => assessment.assignments("student"), []);
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <h1 className="text-2xl font-semibold tracking-tight">Назначенные тесты</h1>
      {list.error && <Alert>{list.error}</Alert>}
      {!list.data ? (
        !list.error && <Spinner />
      ) : !list.data.length ? (
        <EmptyState title="Тестов пока нет" text="Когда педагог назначит тест или ДЗ, он появится здесь." />
      ) : (
        <ul className="space-y-2">
          {list.data.map((a) => {
            const st = studentStatus(a, a.students[0]);
            return (
              <li key={a.id}>
                <Link href={`/dashboard/assignments/${a.id}`} className="block rounded-2xl border border-line bg-surface px-5 py-4 hover:border-brand/50">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="min-w-0 flex-1 font-medium">{a.title}</span>
                    <Badge tone={st.tone}>{st.text}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-fg-soft">
                    {[
                      KIND_LABELS[a.kind],
                      a.teacher_name,
                      a.not_open_yet && a.opens_at ? `откроется ${fmtDateTime(a.opens_at)}` : null,
                      a.deadline ? `сдать до ${fmtDateTime(a.deadline)}` : null,
                      a.max_attempts === 1 ? null : attemptsText(a),
                      fmtLimit(a.settings),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
