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
