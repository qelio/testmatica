"use client";

import Link from "next/link";

import { Badge } from "@/components/ui";
import { assessment, type Lesson } from "@/lib/api";
import { KIND_LABELS, studentStatus, summary } from "@/lib/assignments";
import { useLoad } from "@/lib/hooks";

/** Тесты урока (ДЗ и тест на уроке) — только просмотр; назначают в разделе «Назначение тестов». */
export function LessonAssignments({ lesson, isTeacher }: { lesson: Lesson; isTeacher: boolean }) {
  const list = useLoad(() => assessment.assignments(isTeacher ? "teacher" : "student", { lesson_id: lesson.id }), [lesson.id, isTeacher]);
  if (!list.data?.length) return null;

  return (
    <div className="space-y-2 border-t border-line pt-3">
      <h3 className="text-sm font-medium">Тесты к уроку</h3>
      <ul className="space-y-1.5">
        {list.data.map((a) => {
          const st = isTeacher ? null : studentStatus(a, a.students[0]);
          const s = isTeacher ? summary(a) : null;
          return (
            <li key={a.id} className="flex flex-wrap items-center gap-2 text-sm">
              <Link href={`/dashboard/assignments/${a.id}`} className="min-w-0 flex-1 truncate font-medium text-brand hover:underline">
                {a.title}
              </Link>
              <Badge tone={a.kind === "live" ? "brand" : "neutral"}>{KIND_LABELS[a.kind]}</Badge>
              {st && <Badge tone={st.tone}>{st.text}</Badge>}
              {s && (
                <span className="text-fg-soft">
                  сдали {s.submitted} из {s.total}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
