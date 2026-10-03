import type { Student } from "./api";
import { fmtDate, fmtTime, zoned } from "@/lib/dates";

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

/** 1 отзыв, 2 отзыва, 5 отзывов. */
export function pluralReviews(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  const word = mod10 === 1 && mod100 !== 11 ? "отзыв" : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? "отзыва" : "отзывов";
  return `${n} ${word}`;
}

/** Рейтинг 1–10 с одним знаком: «9,2». */
export function fmtRating(n: number): string {
  return n.toLocaleString("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
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
  if (zoned(p.last_seen_at).toDateString() === zoned(new Date()).toDateString()) {
    return `в сети сегодня в ${fmtTime(p.last_seen_at)}`;
  }
  return `в сети ${fmtDate(p.last_seen_at, { day: "numeric", month: "long" })}`;
}

export function fmtRub(n: number): string {
  return `${n.toLocaleString("ru-RU")} ₽`;
}

export const GOAL_LABELS = {
  ege: "Подготовка к ЕГЭ",
  oge: "Подготовка к ОГЭ",
  school: "Школьная программа",
  gaps: "Устранение пробелов",
  olympiad: "Олимпиады",
  other: "Общее развитие",
} as const;

export const REQUEST_STATUS = {
  open: { text: "открыта", tone: "brand" },
  agreed: { text: "договорились", tone: "ok" },
  closed: { text: "закрыта", tone: "neutral" },
  expired: { text: "истекла", tone: "neutral" },
} as const;

/** Удобные дни: «пн, ср» (время согласуют в чате). */
export function fmtSchedule(s: { weekdays: number[] }): string {
  const days = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"];
  return s.weekdays.length ? s.weekdays.map((d) => days[d]).join(", ") : "любые дни";
}



const WEEKDAY_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"];

/** «пн, ср в 18:00 · 60 мин · с 5 октября · 16 занятий». */
export function fmtOfferSchedule(s: { weekdays: number[]; time: string; duration_min: number; start_date: string; lessons_count: number | null }): string {
  const start = new Date(`${s.start_date}T00:00:00`).toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
  return [
    `${s.weekdays.map((d) => WEEKDAY_SHORT[d]).join(", ")} в ${s.time}`,
    `${s.duration_min} мин`,
    `с ${start}`,
    s.lessons_count ? `${s.lessons_count} ${pluralWord(s.lessons_count, "занятие", "занятия", "занятий")}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function pluralWord(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  return mod10 === 1 && mod100 !== 11 ? one : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? few : many;
}

export const OFFER_STATUS = {
  recruiting: { text: "идёт набор", tone: "brand" },
  underfilled: { text: "недобор", tone: "warn" },
  started: { text: "группа занимается", tone: "ok" },
  closed: { text: "набор закрыт", tone: "neutral" },
  cancelled: { text: "набор отменён", tone: "warn" },
} as const;
