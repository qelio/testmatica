import type { Assignment, AttemptBrief } from "@/lib/api";
import { fmtDateTime } from "@/lib/dates";

export type Tone = "neutral" | "brand" | "warn" | "ok";
type Row = Assignment["students"][number];

export const KIND_LABELS = { test: "Тест", homework: "ДЗ", live: "Тест на уроке" } as const;

export function lastAttempt(row: Row | undefined): AttemptBrief | undefined {
  return row?.attempts[row.attempts.length - 1];
}

/** Лучшая проверенная попытка — она идёт в итог (решение №15). */
export function bestAttempt(row: Row | undefined): AttemptBrief | undefined {
  const checked = row?.attempts.filter((t) => t.status === "submitted" && t.checked) ?? [];
  return checked.reduce<AttemptBrief | undefined>((best, t) => (!best || (t.percent ?? 0) > (best.percent ?? 0) ? t : best), undefined);
}

/** Можно ли начать ещё одну попытку (по числу попыток; сроки проверяет сервер). */
export function canRetry(a: Assignment, row: Row | undefined): boolean {
  if (!row || a.closed || a.overdue || a.not_open_yet) return false;
  return a.max_attempts === null || row.attempts.length < row.allowed_attempts;
}

/** Состояние работы ученика — одинаково для ученика и в таблице педагога. */
export function studentStatus(a: Assignment, row: Row | undefined): { text: string; tone: Tone } {
  const last = lastAttempt(row);
  if (last?.status === "in_progress") return { text: `В процессе · ${last.answered} из ${last.total}`, tone: "brand" };
  if (a.not_open_yet && a.opens_at) return { text: `Откроется ${fmtDateTime(a.opens_at)}`, tone: "neutral" };
  const best = bestAttempt(row);
  const more = canRetry(a, row) && last ? " · можно ещё раз" : "";
  if (best) {
    return { text: `Оценка ${best.grade} · ${Math.round(best.percent ?? 0)}%${more}`, tone: (best.grade ?? 0) >= 4 ? "ok" : "warn" };
  }
  if (last?.status === "submitted") return { text: `Сдано, проверяется${more}`, tone: "neutral" };
  if (a.closed) return { text: "Тест завершён", tone: "warn" };
  if (a.overdue) return { text: "Просрочено", tone: "warn" };
  return { text: "Не начато", tone: "neutral" };
}

export function attemptsText(a: Pick<Assignment, "max_attempts">): string {
  if (a.max_attempts === null) return "попыток без ограничений";
  return a.max_attempts === 1 ? "одна попытка" : `попыток: ${a.max_attempts}`;
}

/** Сводка по работе для педагога. */
export function summary(a: Assignment) {
  const lasts = a.students.map(lastAttempt);
  const submitted = lasts.filter((t) => t?.status === "submitted");
  const checked = a.students.map(bestAttempt).filter(Boolean);
  return {
    total: a.students.length,
    inProgress: lasts.filter((t) => t?.status === "in_progress").length,
    submitted: submitted.length,
    toReview: a.students.filter((r) => r.attempts.some((t) => t.status === "submitted" && !t.checked)).length,
    avg: checked.length ? Math.round(checked.reduce((n, t) => n + (t?.percent ?? 0), 0) / checked.length) : null,
  };
}

export function fmtLimit(s: { time_mode: string; time_limit_s: number | null }): string | null {
  if (s.time_mode === "none" || !s.time_limit_s) return null;
  const min = s.time_limit_s / 60;
  const value = Number.isInteger(min) ? `${min} мин` : `${Math.round(s.time_limit_s)} с`;
  return s.time_mode === "total" ? `${value} на тест` : `${value} на задание`;
}

/** Классы, для которых бывают тесты. */
export const GRADE_LEVELS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];

export function gradeLevelLabel(level: number | null | undefined): string | null {
  return level ? `${level} класс` : null;
}

/** Фильтр по классу: "" — все, "none" — класс не указан (тесты, созданные до решения №36). */
export function matchesGrade(level: number | null | undefined, filter: string): boolean {
  if (!filter) return true;
  if (filter === "none") return !level;
  return level === Number(filter);
}
