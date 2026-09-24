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
