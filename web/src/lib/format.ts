import type { Student } from "./api";

export const SOURCE_LABELS: Record<Student["source"], string> = {
  invite: "по приглашению",
  manual: "аккаунт создан вами",
  request: "по запросу",
  marketplace: "через поиск",
};

/** 1 ученик, 2 ученика, 5 учеников. */
export function pluralStudents(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  const word =
    mod10 === 1 && mod100 !== 11
      ? "ученик"
      : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)
        ? "ученика"
        : "учеников";
  return `${n} ${word}`;
}

export const ATTENDANCE_LABELS = {
  present: { short: "✓", full: "Присутствовал" },
  late: { short: "О", full: "Опоздал" },
  absent: { short: "Н", full: "Отсутствовал" },
  sick: { short: "Б", full: "Болел" },
} as const;

export function fmtAverage(value: number | null): string {
  return value === null ? "—" : value.toFixed(2).replace(/\.?0+$/, "").replace(".", ",");
}

export function fmtRate(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

/** Цвет оценки: 5 и 4 — хорошо, 3 — средне, 2 и 1 — плохо. */
export function gradeTone(value: number): string {
  return value >= 4 ? "text-ok" : value === 3 ? "text-tutor" : "text-danger";
}

export const TASK_TYPE_LABELS = {
  choice: "Выбор ответа",
  short: "Короткий ответ",
  long: "Развёрнутый ответ",
  code: "Код (Python)",
} as const;

export const DIFFICULTY_LABELS = { 1: "базовый", 2: "средний", 3: "сложный" } as const;

export const FAILURE_LABELS = {
  wrong_answer: "неверный ответ",
  runtime_error: "ошибка выполнения",
  time_limit: "превышено время",
  memory_limit: "превышена память",
} as const;

export const LEVEL_LABELS = { "1-4": "1–4 класс", "5-9": "5–9 класс", "10-11": "10–11 класс", student: "Студенты", adult: "Взрослые" } as const;
export const FORMAT_LABELS = { individual: "Индивидуально", group: "В группе" } as const;

/** Онлайн-статус: «онлайн», «в сети сегодня в 14:05», «в сети 12 сентября». */
export function presenceText(p: { online: boolean; last_seen_at: string | null }): string {
  if (p.online) return "онлайн";
  if (!p.last_seen_at) return "давно не в сети";
  const seen = new Date(p.last_seen_at);
  const now = new Date();
  if (seen.toDateString() === now.toDateString()) {
    return `в сети сегодня в ${seen.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;
  }
  return `в сети ${seen.toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}`;
}

export function fmtRub(n: number): string {
  return `${n.toLocaleString("ru-RU")} ₽`;
}

