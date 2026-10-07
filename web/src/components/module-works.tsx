"use client";

import Link from "next/link";

import { Badge } from "@/components/ui";
import { assessment } from "@/lib/api";
import { studentStatus } from "@/lib/assignments";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/dates";
import { useLoad } from "@/lib/hooks";

/** Тесты и практические работы по теме модуля (решение №43): педагогу — его тесты, привязанные к модулю,
 *  с кнопкой «Назначить»; ученику — выданные ему работы по этой теме. */
export function ModuleWorks({ moduleId, courseId }: { moduleId: string; courseId: string }) {
  const { status, user } = useAuth();
  const author = !!user?.roles.some((r) => r === "teacher" || r === "moderator");
  const signedIn = status === "authenticated";
  const tests = useLoad(() => (signedIn && author ? assessment.tests(moduleId) : Promise.resolve([])), [moduleId, signedIn, author]);
  const works = useLoad(
    () => (signedIn && !author ? assessment.assignments("student", { module_id: moduleId }) : Promise.resolve([])),
    [moduleId, signedIn, author],
  );
  if (!signedIn) return null;

  if (author) {
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
        {!tests.data?.length ? (
          <p className="text-sm text-fg-soft">
            Привяжите тест к этому модулю — ученики увидят работы по нему здесь, рядом с теорией. Привязка — в настройках теста.
          </p>
        ) : (
          <ul className="divide-y divide-line">
            {tests.data.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center gap-3 py-2.5">
                <Link href={`/dashboard/tests/${t.id}`} className="min-w-0 flex-1 hover:text-brand">
                  <span className="font-medium">{t.title}</span>
                  <span className="ml-2 text-sm text-fg-soft">
                    заданий: {t.tasks_count}
                    {t.assignments_count ? ` · назначен ${t.assignments_count} раз` : ""}
                  </span>
                </Link>
                {t.tasks_count > 0 && (
                  <Link href={`/dashboard/assignments/new?test=${t.id}`} className="text-sm font-medium text-brand hover:underline">
                    Назначить
                  </Link>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    );
  }

  if (!works.data?.length) return null;
  return (
    <section className="tm-card space-y-3 rounded-2xl border border-line bg-surface p-5">
      <h2 className="text-lg font-semibold">Тесты и практические работы</h2>
      <ul className="space-y-2">
        {works.data.map((a) => {
          const st = studentStatus(a, a.students[0]);
          return (
            <li key={a.id}>
              <Link
                href={`/dashboard/assignments/${a.id}`}
                className="tm-opt flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-line px-4 py-3 hover:bg-muted"
              >
                <span className="min-w-0 flex-1 font-medium">{a.title}</span>
                <Badge tone={st.tone}>{st.text}</Badge>
                {a.deadline && !a.closed && <span className="text-sm text-fg-soft">до {fmtDateTime(a.deadline)}</span>}
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
