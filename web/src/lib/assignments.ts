import type { Assignment, AttemptBrief } from "@/lib/api";

export type Tone = "neutral" | "brand" | "warn" | "ok";
type Row = Assignment["students"][number];

export const KIND_LABELS = { homework: "ДЗ", live: "Тест на уроке" } as const;

export function lastAttempt(row: Row | undefined): AttemptBrief | undefined {
  return row?.attempts[row.attempts.length - 1];
}

/** Состояние работы ученика — одинаково для ученика и в таблице педагога. */
export function studentStatus(a: Assignment, row: Row | undefined): { text: string; tone: Tone } {
  const last = lastAttempt(row);
  if (last?.status === "in_progress") return { text: `В процессе · ${last.answered} из ${last.total}`, tone: "brand" };
  const canRetry = row && last && row.attempts.length < row.allowed_attempts;
  if (canRetry && !a.overdue && !a.closed) return { text: "Можно пройти ещё раз", tone: "brand" };
  if (last?.status === "submitted") {
    if (!last.checked) return { text: "Сдано, проверяется", tone: "neutral" };
    return { text: `Оценка ${last.grade} · ${Math.round(last.percent ?? 0)}%`, tone: (last.grade ?? 0) >= 4 ? "ok" : "warn" };
  }
  if (a.closed) return { text: "Тест завершён", tone: "warn" };
  if (a.overdue) return { text: "Просрочено", tone: "warn" };
  return { text: "Не начато", tone: "neutral" };
}

/** Сводка по работе для педагога. */
export function summary(a: Assignment) {
  const lasts = a.students.map(lastAttempt);
  const submitted = lasts.filter((t) => t?.status === "submitted");
  const checked = submitted.filter((t) => t?.checked);
  return {
    total: a.students.length,
    inProgress: lasts.filter((t) => t?.status === "in_progress").length,
    submitted: submitted.length,
    toReview: submitted.length - checked.length,
    avg: checked.length ? Math.round(checked.reduce((n, t) => n + (t?.percent ?? 0), 0) / checked.length) : null,
  };
}

export function fmtLimit(s: { time_mode: string; time_limit_s: number | null }): string | null {
  if (s.time_mode === "none" || !s.time_limit_s) return null;
  const min = s.time_limit_s / 60;
  const value = Number.isInteger(min) ? `${min} мин` : `${Math.round(s.time_limit_s)} с`;
  return s.time_mode === "total" ? `${value} на тест` : `${value} на задание`;
}
