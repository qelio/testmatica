// Даты в интерфейсе — в часовом поясе браузера; на сервер уходят в UTC (ISO 8601).

export const WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

export function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

export function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n, d.getHours(), d.getMinutes());
}

/** Понедельник недели, в которую попадает дата. */
export function startOfWeek(d: Date): Date {
  const day = startOfDay(d);
  return addDays(day, -weekdayIndex(day));
}

/** 0 — понедельник … 6 — воскресенье (как на сервере). */
export function weekdayIndex(d: Date): number {
  return (d.getDay() + 6) % 7;
}

export function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

export function timezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Moscow";
}

export function fmtTime(d: Date | string): string {
  return new Date(d).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

export function fmtDate(d: Date | string, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "long" }): string {
  return new Date(d).toLocaleDateString("ru-RU", opts);
}

export function fmtDateTime(d: Date | string): string {
  return `${fmtDate(d, { weekday: "short", day: "numeric", month: "long" })}, ${fmtTime(d)}`;
}

/** Значения для <input type="date"> и <input type="time"> в местном времени. */
export function toDateInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function toTimeInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fromInputs(date: string, time: string): Date {
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  return new Date(y, m - 1, d, hh, mm);
}

export function pluralLessons(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  const word =
    mod10 === 1 && mod100 !== 11 ? "занятие" : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? "занятия" : "занятий";
  return `${n} ${word}`;
}
