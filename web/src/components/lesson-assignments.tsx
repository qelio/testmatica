"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AssignModal } from "@/components/assign-modal";
import { Badge, Button, Select } from "@/components/ui";
import { assessment, type Lesson } from "@/lib/api";
import { KIND_LABELS, studentStatus, summary } from "@/lib/assignments";
import { useLoad } from "@/lib/hooks";

/** ДЗ и тесты урока: педагог выдаёт прямо из карточки занятия, ученик открывает (ТЗ, раздел 6). */
export function LessonAssignments({ lesson, isTeacher }: { lesson: Lesson; isTeacher: boolean }) {
  const router = useRouter();
  const list = useLoad(() => assessment.assignments(isTeacher ? "teacher" : "student", { lesson_id: lesson.id }), [lesson.id, isTeacher]);
  const tests = useLoad(async () => (isTeacher ? assessment.tests() : []), [isTeacher]);
  const [testId, setTestId] = useState("");
  const [kind, setKind] = useState<"homework" | "live" | null>(null);

  const target = lesson.kind === "group" ? lesson.group_id : lesson.participants?.[0]?.id;
  if (!isTeacher && !list.data?.length) return null;

  return (
    <div className="space-y-2 border-t border-line pt-3">
      <h3 className="text-sm font-medium">Задания к уроку</h3>
      {list.data?.length ? (
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
      ) : (
        <p className="text-sm text-fg-soft">Пока ничего не выдано.</p>
      )}
      {isTeacher && target && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-48 flex-1">
            <Select label="Тест" value={testId} onChange={(e) => setTestId(e.target.value)}>
              <option value="">{tests.data?.length ? "Выберите тест" : "Сначала создайте тест"}</option>
              {tests.data?.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.title}
                </option>
              ))}
            </Select>
          </div>
          <Button variant="secondary" disabled={!testId} onClick={() => setKind("homework")}>
            Выдать ДЗ
          </Button>
          <Button variant="secondary" disabled={!testId} onClick={() => setKind("live")}>
            Тест на уроке
          </Button>
        </div>
      )}
      {isTeacher && target && testId && (
        <AssignModal
          testId={testId}
          open={kind !== null}
          initialKind={kind ?? "homework"}
          preset={{ targetType: lesson.kind === "group" ? "group" : "student", targetId: target, lessonId: lesson.id }}
          onClose={() => setKind(null)}
          onAssigned={(a) => router.push(`/dashboard/assignments/${a.id}`)}
        />
      )}
    </div>
  );
}
