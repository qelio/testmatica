"use client";

import Link from "next/link";
import { Suspense, useState } from "react";

import { GradeFilter } from "@/components/grade-filter";
import { Badge, EmptyState, Spinner, Alert } from "@/components/ui";
import { type Assignment, assessment } from "@/lib/api";
import { attemptsText, fmtLimit, gradeLevelLabel, KIND_LABELS, matchesGrade, studentStatus, summary } from "@/lib/assignments";
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

function Given() {
  const list = useLoad(() => assessment.assignments("teacher"), []);
  const [grade, setGrade] = useState("");
  const [target, setTarget] = useState("");
  if (list.error) return <Alert>{list.error}</Alert>;
  if (!list.data) return <Spinner />;
  if (!list.data.length)
    return (
      <EmptyState
        title="Вы ещё не назначали тесты"
        text="Соберите тест из задач банка в разделе «Тесты» и назначьте его: просто тестом, домашним заданием к уроку или тестом на уроке."
      />
    );
  // Кому назначали: группы и ученики — из самих назначений.
  const targets = [...new Map(list.data.map((a) => [a.target_id, a])).values()].sort(
    (x, y) => x.target_type.localeCompare(y.target_type) || x.target_title.localeCompare(y.target_title, "ru"),
  );
  const shown = list.data.filter((a) => matchesGrade(a.grade_level, grade) && (!target || a.target_id === target));
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <GradeFilter value={grade} onChange={setGrade} withNone={list.data.some((a) => !a.grade_level)} />
        <select
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          aria-label="Кому назначен"
          className="h-10 max-w-full rounded-xl border border-line bg-surface px-3 text-sm outline-none focus:border-brand"
        >
          <option value="">Все группы и ученики</option>
          {["group", "student"].map((type) => {
            const items = targets.filter((t) => t.target_type === type);
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
        {(grade || target) && <span className="text-sm text-fg-soft">Найдено: {shown.length}</span>}
      </div>
      {!shown.length && <p className="rounded-2xl border border-line bg-surface px-5 py-4 text-sm text-fg-soft">Ничего не найдено.</p>}
      <ul className="space-y-2">
        {shown.map((a) => (
          <li key={a.id}>
            <GivenCard a={a} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function GivenCard({ a }: { a: Assignment }) {
  const s = summary(a);
  const live = a.kind === "live" && !a.closed && !a.not_open_yet;
  return (
    <Link href={`/dashboard/assignments/${a.id}`} className="block rounded-2xl border border-line bg-surface px-5 py-4 hover:border-brand/50">
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 flex-1">
          <span className="font-medium">{a.title}</span>
          {a.test_title !== a.title && <span className="ml-2 text-sm text-fg-soft">по тесту «{a.test_title}»</span>}
        </span>
        {live && <Badge tone="brand">идёт сейчас</Badge>}
        <Badge tone={a.kind === "live" ? "brand" : "neutral"}>{KIND_LABELS[a.kind]}</Badge>
      </div>
      <p className="mt-1 text-sm text-fg-soft">
        {[
          a.target_title,
          gradeLevelLabel(a.grade_level),
          a.not_open_yet && a.opens_at ? `откроется ${fmtDateTime(a.opens_at)}` : null,
          a.deadline ? `до ${fmtDateTime(a.deadline)}` : null,
          attemptsText(a),
          a.closed ? "завершён" : null,
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <span>
          Сдали: <b>{s.submitted}</b> из {s.total}
        </span>
        {s.inProgress > 0 && <span className="text-brand">решают: {s.inProgress}</span>}
        {s.toReview > 0 && <span className="text-tutor">ждут проверки: {s.toReview}</span>}
        {s.avg !== null && <span className="text-fg-soft">средний результат {s.avg}%</span>}
      </p>
    </Link>
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
