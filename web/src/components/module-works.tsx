"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Badge, Button } from "@/components/ui";
import { assessment, type CourseTest, type TestVisibility } from "@/lib/api";
import { lastAttempt, studentStatus } from "@/lib/assignments";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

const VISIBILITY: Record<TestVisibility, { label: string; tone: "ok" | "brand" | "neutral" }> = {
  public: { label: "публичный", tone: "ok" },
  teachers: { label: "для педагогов", tone: "brand" },
  private: { label: "личный", tone: "neutral" },
};
const ORDER: TestVisibility[] = ["public", "teachers", "private"];

/** Тесты под модулем курса (решения №43, 44, 46).
 *  Ученикам — публичные тесты автора курса (проходят сами) и работы по теме от их педагога.
 *  Педагогам — тесты автора курса, принятые с курсом (публичные и «для педагогов»), и свои личные — с кнопкой «Назначить». */
export function ModuleWorks({ moduleId, courseId }: { moduleId: string; courseId: string }) {
  const { status, user } = useAuth();
  const signedIn = status === "authenticated";
  // Тесты к модулю ведут педагоги и штатные редакторы библиотеки (модератор, администратор); назначают — педагоги.
  const teacher = !!user?.roles.some((r) => r === "teacher" || r === "moderator" || r === "admin");
  const canAssign = !!user?.roles.includes("teacher");
  const shared = useLoad(() => assessment.courseTests(moduleId, signedIn), [moduleId, signedIn]);
  const mine = useLoad(() => (signedIn && teacher ? assessment.tests(moduleId) : Promise.resolve([])), [moduleId, signedIn, teacher]);
  const works = useLoad(
    () => (signedIn && !teacher ? assessment.assignments("student", { module_id: moduleId }) : Promise.resolve([])),
    [moduleId, signedIn, teacher],
  );
  if (status === "loading") return null;

  if (teacher) {
    // Свои тесты — с состоянием проверки; тесты автора курса — только принятые.
    const ownIds = new Set(mine.data?.map((t) => t.id));
    const rows = [
      ...(mine.data ?? []).map((t) => ({
        id: t.id,
        title: t.title,
        tasks: t.tasks_count,
        own: true,
        visibility: t.visibility ?? "private",
        note:
          t.visibility === "private" || !t.visibility
            ? null
            : t.pending
              ? "изменения на проверке"
              : t.published
                ? null
                : "появится после проверки курса",
      })),
      ...(shared.data ?? [])
        .filter((t) => !ownIds.has(t.id))
        .map((t) => ({ id: t.id, title: t.title, tasks: t.tasks_count, own: false, visibility: t.visibility as TestVisibility, note: null })),
    ].sort((a, b) => ORDER.indexOf(a.visibility) - ORDER.indexOf(b.visibility));
    return (
      <section className="tm-card space-y-3 rounded-2xl border border-line bg-surface p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">Тесты по теме</h2>
          <Link
            href={`/dashboard/tests/new?course=${courseId}&module=${moduleId}`}
            className="tm-btn tm-btn-secondary inline-flex h-9 items-center rounded-xl border border-line px-3 text-sm font-medium hover:bg-muted"
          >
            + Новый тест к теме
          </Link>
        </div>
        {!rows.length ? (
          <p className="text-sm text-fg-soft">
            Привяжите тест к этому модулю в его настройках. У автора курса тест публичный (ученики проходят его сами) или «для
            педагогов» (его назначают все педагоги); тест любого другого педагога — личный, виден только ему.
          </p>
        ) : (
          <ul className="divide-y divide-line">
            {rows.map((t) => (
              <TeacherRow key={t.id} {...t} assign={canAssign} />
            ))}
          </ul>
        )}
      </section>
    );
  }

  const assigned = works.data ?? [];
  const open = shared.data ?? [];
  if (!assigned.length && !open.length) return null;
  return (
    <section className="tm-card space-y-3 rounded-2xl border border-line bg-surface p-5">
      <h2 className="text-lg font-semibold">Тесты и практические работы</h2>
      {assigned.length > 0 && (
        <ul className="space-y-2">
          {assigned.map((a) => {
            const st = studentStatus(a, a.students[0]);
            return (
              <li key={a.id}>
                <Link
                  href={`/dashboard/assignments/${a.id}`}
                  className="tm-opt flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-line px-4 py-3 hover:bg-muted"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium">{a.title}</span>
                    <span className="block text-sm text-fg-soft">задал(а) {a.teacher_name}</span>
                  </span>
                  <Badge tone={st.tone}>{st.text}</Badge>
                  {a.deadline && !a.closed && <span className="text-sm text-fg-soft">до {fmtDateTime(a.deadline)}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      {open.length > 0 && (
        <ul className="space-y-2">
          {open.map((t) => (
            <SelfRow key={t.id} test={t} signedIn={signedIn} onChanged={shared.reload} />
          ))}
        </ul>
      )}
    </section>
  );
}

function TeacherRow({
  id,
  title,
  tasks,
  own,
  assign,
  visibility,
  note,
}: {
  id: string;
  title: string;
  tasks: number;
  own: boolean;
  assign: boolean;
  visibility: TestVisibility;
  note: string | null;
}) {
  const v = VISIBILITY[visibility];
  return (
    <li className="flex flex-wrap items-center gap-3 py-2.5">
      <span className="min-w-0 flex-1">
        {own ? (
          <Link href={`/dashboard/tests/${id}`} className="font-medium hover:text-brand">
            {title}
          </Link>
        ) : (
          <span className="font-medium">{title}</span>
        )}
        <span className="ml-2 text-sm text-fg-soft">
          заданий: {tasks}
          {note && ` · ${note}`}
        </span>
      </span>
      <Badge tone={v.tone}>{v.label}</Badge>
      {assign && tasks > 0 && (
        <Link href={`/dashboard/assignments/new?test=${id}`} className="text-sm font-medium text-brand hover:underline">
          Назначить
        </Link>
      )}
    </li>
  );
}

/** Общий тест для самостоятельного прохождения: статус своей работы и кнопка «Пройти». */
function SelfRow({ test, signedIn, onChanged }: { test: CourseTest; signedIn: boolean; onChanged: () => void }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const a = test.self_assignment;
  const row = a?.students[0];
  const inProgress = lastAttempt(row)?.status === "in_progress";
  const st = a ? studentStatus(a, row) : null;

  async function go() {
    setBusy(true);
    setError(undefined);
    try {
      const attempt = await assessment.startSelf(test.id);
      router.push(`/dashboard/attempts/${attempt.id}`);
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
      onChanged();
    }
  }

  return (
    <li className="tm-opt space-y-2 rounded-xl border border-line px-4 py-3">
      <div>
        <span className="block font-medium">{test.title}</span>
        <span className="block text-sm text-fg-soft">
          заданий: {test.tasks_count} · баллов: {test.max_score} · можно проходить сколько угодно раз
        </span>
      </div>
      <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
        {st && row?.attempts.length ? (
          <span className="mr-auto">
            <Badge tone={st.tone}>{st.text}</Badge>
          </span>
        ) : null}
        {a && row?.attempts.some((t) => t.status === "submitted") && (
          <Link href={`/dashboard/assignments/${a.id}`} className="text-sm text-brand hover:underline">
            Мои попытки
          </Link>
        )}
        {signedIn ? (
          <Button onClick={go} loading={busy} disabled={test.tasks_count === 0} className="h-9">
            {inProgress ? "Продолжить" : row?.attempts.length ? "Пройти ещё раз" : "Пройти"}
          </Button>
        ) : (
          <Link href="/login" className="text-sm font-medium text-brand hover:underline">
            Войдите, чтобы пройти
          </Link>
        )}
      </div>
      {error && <Alert>{error}</Alert>}
    </li>
  );
}
