"use client";

import { Nunito, Unbounded } from "next/font/google";

import type { CourseTheme, TestTheme } from "@/lib/api";
import { COURSE_THEMES } from "@/lib/course-themes";

// Шрифты «Комикса» — грузятся только на страницах в этом оформлении.
const display = Unbounded({ variable: "--font-unbounded", subsets: ["latin", "cyrillic"], weight: ["600", "700", "800"], preload: false });
const body = Nunito({ variable: "--font-nunito-body", subsets: ["latin", "cyrillic"], weight: ["400", "600", "700", "800"], preload: false });

/** Оформление курса или теста (решение №42): переопределяет токены цветов и стили карточек, кнопок, вариантов
 *  внутри себя (globals.css, .tm-<тема>). Логика страниц та же; классика — без обёртки-сцены. */
export function ThemeScope({ theme, className = "", children }: { theme?: CourseTheme | null; className?: string; children: React.ReactNode }) {
  if (!theme || theme === "classic") return <div className={className}>{children}</div>;
  return <div className={`tm-theme tm-${theme} ${display.variable} ${body.variable} ${className}`}>{children}</div>;
}

/** Выбор оформления — плитки с мини-превью темы. course — «как у курса» привязанного модуля (только у тестов). */
export function ThemePicker<T extends TestTheme>({
  value,
  onChange,
  hint,
  course,
}: {
  value: T;
  onChange: (t: T) => void;
  hint?: string;
  course?: { title: string; theme: CourseTheme } | null;
}) {
  const options: { id: TestTheme; label: string; text: string; preview: CourseTheme }[] = [
    ...(course ? [{ id: "course" as const, label: "Как у курса", text: `Как у курса «${course.title}» — меняется вместе с ним`, preview: course.theme }] : []),
    ...COURSE_THEMES.map((t) => ({ ...t, preview: t.id })),
  ];
  return (
    <fieldset>
      <legend className="mb-1.5 text-sm font-medium">Оформление для учеников</legend>
      <div className={`grid gap-2 ${options.length > 2 ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
        {options.map((t) => (
          <label
            key={t.id}
            className={`flex cursor-pointer flex-col gap-2 rounded-xl border p-2.5 ${value === t.id ? "border-brand ring-2 ring-brand/20" : "border-line hover:bg-muted"}`}
          >
            <input type="radio" name="course-theme" className="sr-only" checked={value === t.id} onChange={() => onChange(t.id as T)} />
            <ThemePreview theme={t.preview} />
            <span>
              <span className="block text-sm font-medium">{t.label}</span>
              <span className="block text-xs text-fg-soft">{t.text}</span>
            </span>
          </label>
        ))}
      </div>
      {hint && <p className="mt-1.5 text-xs text-fg-soft">{hint}</p>}
    </fieldset>
  );
}

function ThemePreview({ theme }: { theme: CourseTheme }) {
  return (
    <ThemeScope theme={theme} className="tm-preview pointer-events-none rounded-lg bg-bg p-2.5">
      <div aria-hidden className="tm-card rounded-lg border border-line bg-surface p-2">
        <div className="flex items-center gap-1.5">
          <span className="tm-only tm-num">1</span>
          <span className="tm-title text-xs font-semibold">Урок 1</span>
        </div>
        <div className="mt-1.5 flex gap-1">
          <span className="tm-opt tm-opt-ok flex-1 rounded-md border border-ok bg-ok/10 px-1.5 py-0.5 text-[10px]">Верно</span>
          <span className="tm-opt flex-1 rounded-md border border-line px-1.5 py-0.5 text-[10px]">Ответ</span>
        </div>
      </div>
    </ThemeScope>
  );
}
