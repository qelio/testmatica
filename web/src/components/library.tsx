"use client";

import Link from "next/link";
import { useState } from "react";

import { STATUS_LABELS } from "@/components/course-view";
import { Alert, Badge, EmptyState, Spinner } from "@/components/ui";
import { content, type CourseSummary } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

export function CourseCard({ course, base, showStatus }: { course: CourseSummary; base: string; showStatus?: boolean }) {
  return (
    <Link href={`${base}/course/${course.id}`} className="flex flex-col rounded-2xl border border-line bg-surface p-5 transition-colors hover:border-brand/50">
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm text-fg-soft">{course.subject?.name ?? "Без предмета"}</span>
        {showStatus && <Badge tone={STATUS_LABELS[course.status].tone}>{STATUS_LABELS[course.status].text}</Badge>}
      </div>
      <h3 className="mt-1 text-lg font-semibold leading-snug">{course.title}</h3>
      {course.description && <p className="mt-1 line-clamp-2 text-sm text-fg-soft">{course.description}</p>}
      <p className="mt-auto pt-4 text-xs text-fg-soft">
        {course.author_name} · разделов {course.sections_count} · материалов {course.materials_count}
      </p>
    </Link>
  );
}

export function CourseGrid({ courses, base, showStatus, empty }: { courses: CourseSummary[] | null; base: string; showStatus?: boolean; empty: React.ReactNode }) {
  if (!courses) return <Spinner />;
  if (!courses.length) return <>{empty}</>;
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {courses.map((c) => (
        <CourseCard key={c.id} course={c} base={base} showStatus={showStatus} />
      ))}
    </div>
  );
}

/** Публичная библиотека: фильтр по предмету и поиск. */
export function Catalog({ base }: { base: string }) {
  const subjects = useLoad(() => content.subjects(), []);
  const [subject, setSubject] = useState("");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const courses = useLoad(() => content.catalog({ subject_id: subject, q: search }), [subject, search]);

  return (
    <div className="space-y-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setSearch(query.trim());
        }}
      >
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Поиск по курсам…"
          aria-label="Поиск по курсам"
          className="h-11 w-full max-w-md rounded-xl border border-line bg-surface px-3.5 outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
        />
      </form>
      <div className="flex flex-wrap gap-1.5">
        {[{ id: "", name: "Все предметы" }, ...(subjects.data ?? [])].map((s) => (
          <button
            key={s.id}
            onClick={() => setSubject(s.id)}
            aria-pressed={subject === s.id}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${subject === s.id ? "bg-brand text-on-brand" : "bg-muted text-fg-soft hover:text-fg"}`}
          >
            {s.name}
          </button>
        ))}
      </div>
      {courses.error && <Alert>{courses.error}</Alert>}
      <CourseGrid
        courses={courses.data}
        base={base}
        empty={<EmptyState title="Курсов не найдено" text="Попробуйте другой предмет или запрос." />}
      />
    </div>
  );
}
