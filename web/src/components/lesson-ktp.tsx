"use client";

import Link from "next/link";

import { PlanItems } from "@/components/plan-lesson-form";
import { type Lesson, planning } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

/** Уроки КТП на занятии — в карточке занятия у педагога: тема, результаты, материалы. */
export function LessonKtp({ lesson }: { lesson: Lesson }) {
  const ktp = useLoad(() => planning.byLesson(lesson.id), [lesson.id]);
  if (!ktp.data?.length) return null;
  return (
    <div className="space-y-2 border-t border-line pt-3">
      <h3 className="text-sm font-medium">По КТП</h3>
      {ktp.data.map(({ plan_id, plan_title, lesson: l }) => (
        <div key={l.id} className="space-y-1 text-sm">
          <p>
            <Link href={`/dashboard/planning/${plan_id}`} className="font-medium text-brand-text hover:underline">
              {l.topic}
            </Link>
            <span className="text-fg-soft"> · {plan_title}</span>
          </p>
          {l.goals && <p className="text-fg-soft">{l.goals}</p>}
          {l.class_items.length > 0 && (
            <div>
              <span className="text-xs text-fg-soft uppercase">К уроку</span>
              <PlanItems items={l.class_items} />
            </div>
          )}
          {l.home_items.length > 0 && (
            <div>
              <span className="text-xs text-fg-soft uppercase">На дом</span>
              <PlanItems items={l.home_items} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
