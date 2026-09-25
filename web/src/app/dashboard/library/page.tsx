"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { CourseDetailsModal } from "@/components/course-view";
import { Catalog, CourseGrid } from "@/components/library";
import { KIND_LABELS } from "@/components/material-view";
import { Button, EmptyState, Spinner } from "@/components/ui";
import { content } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLoad } from "@/lib/hooks";

type Tab = "public" | "mine" | "shared" | "favorites";

const BASE = "/dashboard/library";

export default function LibraryPage() {
  const { user } = useAuth();
  const router = useRouter();
  const isAuthor = !!user?.roles.some((r) => r === "teacher" || r === "moderator" || r === "admin");
  const isStudent = !!user?.roles.includes("student");
  const [tab, setTab] = useState<Tab>(isAuthor ? "mine" : "public");
  const [creating, setCreating] = useState(false);

  const tabs: { value: Tab; label: string; show: boolean }[] = [
    { value: "mine", label: "Моя библиотека", show: isAuthor },
    { value: "shared", label: "От моих педагогов", show: isStudent },
    { value: "public", label: "Публичная библиотека", show: true },
    { value: "favorites", label: "Избранное", show: true },
  ];

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Библиотека</h1>
        {isAuthor && <Button onClick={() => setCreating(true)}>Новый курс</Button>}
      </div>
      <div className="flex gap-1 overflow-x-auto border-b border-line" role="tablist">
        {tabs
          .filter((t) => t.show)
          .map((t) => (
            <button
              key={t.value}
              role="tab"
              aria-selected={tab === t.value}
              onClick={() => setTab(t.value)}
              className={`-mb-px shrink-0 border-b-2 px-3 py-2.5 text-sm font-medium ${tab === t.value ? "border-brand text-fg" : "border-transparent text-fg-soft hover:text-fg"}`}
            >
              {t.label}
            </button>
          ))}
      </div>

      {tab === "public" && <Catalog base={BASE} />}
      {tab === "mine" && <MyCourses onCreate={() => setCreating(true)} />}
      {tab === "shared" && <SharedCourses />}
      {tab === "favorites" && <Favorites />}

      {creating && (
        <CourseDetailsModal onClose={() => setCreating(false)} onSaved={(id) => router.push(`${BASE}/course/${id}`)} />
      )}
    </div>
  );
}

function MyCourses({ onCreate }: { onCreate: () => void }) {
  const courses = useLoad(() => content.myCourses(), []);
  return (
    <CourseGrid
      courses={courses.data}
      base={BASE}
      showStatus
      empty={
        <EmptyState
          title="В вашей библиотеке пока нет курсов"
          text="Курс сразу виден вашим ученикам. В публичную библиотеку он попадёт после проверки модератором."
          action={<Button onClick={onCreate}>Создать курс</Button>}
        />
      }
    />
  );
}

function SharedCourses() {
  const courses = useLoad(() => content.sharedCourses(), []);
  return (
    <CourseGrid
      courses={courses.data}
      base={BASE}
      empty={<EmptyState title="Ваши педагоги пока не добавили материалы" text="Загляните в публичную библиотеку — там много бесплатных курсов." />}
    />
  );
}

function Favorites() {
  const items = useLoad(() => content.favorites(), []);
  if (!items.data) return <Spinner />;
  if (!items.data.length) return <EmptyState title="В избранном пусто" text="Отмечайте материалы звёздочкой ☆, чтобы быстро к ним вернуться." />;
  return (
    <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
      {items.data.map((m) => (
        <li key={m.id}>
          <Link href={`${BASE}/module/${m.module_id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-muted">
            <span className="text-tutor">★</span>
            <span className="flex-1 font-medium">{m.title}</span>
            <span className="text-sm text-fg-soft">{KIND_LABELS[m.kind]}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
