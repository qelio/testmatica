"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Badge, EmptyState, Spinner, Alert } from "@/components/ui";
import { type Assignment, assessment } from "@/lib/api";
import { fmtLimit, KIND_LABELS, studentStatus, summary } from "@/lib/assignments";
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
  const router = useRouter();
  const params = useSearchParams();
  const tab = params.get("tab") === "tests" ? "tests" : "given";
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Задания и тесты</h1>
        <div className="flex gap-2">
          <Link href="/dashboard/tasks" className="rounded-xl border border-line px-4 py-2.5 text-sm font-medium hover:bg-muted">
            Банк задач
          </Link>
          <Link href="/dashboard/tests/new" className="rounded-xl bg-brand px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-strong">
            Новый тест
          </Link>
        </div>
      </div>
      <div className="flex rounded-xl border border-line bg-muted p-1 text-sm sm:w-fit" role="tablist">
        {(
          [
            ["given", "Выданные"],
            ["tests", "Мои тесты"],
          ] as const
        ).map(([key, title]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => router.replace(key === "tests" ? "/dashboard/assignments?tab=tests" : "/dashboard/assignments")}
            className={`flex-1 rounded-lg px-4 py-1.5 font-medium whitespace-nowrap ${tab === key ? "bg-surface shadow-sm" : "text-fg-soft hover:text-fg"}`}
          >
            {title}
          </button>
        ))}
      </div>
      {tab === "tests" ? <MyTests /> : <Given />}
    </div>
  );
}

function Given() {
  const list = useLoad(() => assessment.assignments("teacher"), []);
  if (list.error) return <Alert>{list.error}</Alert>;
  if (!list.data) return <Spinner />;
  if (!list.data.length)
    return (
      <EmptyState
        title="Вы ещё ничего не выдавали"
        text="Соберите тест из задач банка во вкладке «Мои тесты» и выдайте его как ДЗ или запустите на уроке."
      />
    );
  return (
    <ul className="space-y-2">
      {list.data.map((a) => (
        <li key={a.id}>
          <GivenCard a={a} />
        </li>
      ))}
    </ul>
  );
}

function GivenCard({ a }: { a: Assignment }) {
  const s = summary(a);
  const live = a.kind === "live" && !a.closed;
  return (
    <Link href={`/dashboard/assignments/${a.id}`} className="block rounded-2xl border border-line bg-surface px-5 py-4 hover:border-brand/50">
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 flex-1 font-medium">{a.title}</span>
        {live && <Badge tone="brand">идёт сейчас</Badge>}
        <Badge tone={a.kind === "live" ? "brand" : "neutral"}>{KIND_LABELS[a.kind]}</Badge>
      </div>
      <p className="mt-1 text-sm text-fg-soft">
        {[a.target_title, a.deadline ? `до ${fmtDateTime(a.deadline)}` : null, `выдано ${fmtDateTime(a.created_at)}`].filter(Boolean).join(" · ")}
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

function MyTests() {
  const tests = useLoad(() => assessment.tests(), []);
  if (tests.error) return <Alert>{tests.error}</Alert>;
  if (!tests.data) return <Spinner />;
  if (!tests.data.length)
    return <EmptyState title="Тестов пока нет" text="Тест — это набор задач из банка с настройками: порядок, таймер, баллы." />;
  return (
    <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
      {tests.data.map((t) => (
        <li key={t.id}>
          <Link href={`/dashboard/tests/${t.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-5 py-3 hover:bg-muted">
            <span className="min-w-0 flex-1 font-medium">{t.title}</span>
            <span className="text-sm text-fg-soft">
              {[`заданий: ${t.tasks_count}`, `баллов: ${t.max_score}`, fmtLimit(t), t.assignments_count ? `выдан ${t.assignments_count} раз` : null]
                .filter(Boolean)
                .join(" · ")}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function StudentView() {
  const list = useLoad(() => assessment.assignments("student"), []);
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <h1 className="text-2xl font-semibold tracking-tight">Задания</h1>
      {list.error && <Alert>{list.error}</Alert>}
      {!list.data ? (
        !list.error && <Spinner />
      ) : !list.data.length ? (
        <EmptyState title="Заданий пока нет" text="Когда педагог выдаст ДЗ или тест, он появится здесь." />
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
                      a.deadline ? `сдать до ${fmtDateTime(a.deadline)}` : null,
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
