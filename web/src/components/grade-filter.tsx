"use client";

import { GRADE_LEVELS } from "@/lib/assignments";

/** Выбор класса для фильтра списков тестов и назначений. */
export function GradeFilter({ value, onChange, withNone = true }: { value: string; onChange: (v: string) => void; withNone?: boolean }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label="Класс"
      className="h-10 rounded-xl border border-line bg-surface px-3 text-sm outline-none focus:border-brand"
    >
      <option value="">Все классы</option>
      {GRADE_LEVELS.map((g) => (
        <option key={g} value={g}>
          {g} класс
        </option>
      ))}
      {withNone && <option value="none">Класс не указан</option>}
    </select>
  );
}
