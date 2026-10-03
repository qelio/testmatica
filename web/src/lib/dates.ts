// Даты в интерфейсе — в часовом поясе пользователя из профиля (решение №40; до входа — браузера);
// на сервер уходят в UTC (ISO 8601).
//
// Два вида значений Date:
//  • момент времени (с сервера, для сервера) — форматируется fmtTime/fmtDate/fmtDateTime в поясе пользователя;
//  • «настенное» время пояса пользователя (дни и часы календаря, якорь расписания) — его поля getHours()/getDate()
//    совпадают с часами пользователя. Переход: zoned(момент) → настенное, unzoned(настенное) → момент.

const browserTz = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Moscow";
let displayTz: string | null = null;

/** Пояс, в котором показываем даты: из профиля пользователя (вызывает auth после входа и при смене профиля). */
export function setDisplayTimezone(tz: string | null | undefined): void {
  displayTz = tz || null;
}

/** Смещение пояса от UTC в минутах на момент d. */
function offsetMin(tz: string, d: Date): number {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", { timeZone: tz, hourCycle: "h23", year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric", second: "numeric" })
      .formatToParts(d)
      .map((p) => [p.type, Number(p.value)]),
  );
  const asUtc = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour % 24, parts.minute, parts.second);
  return Math.round((asUtc - Math.floor(d.getTime() / 1000) * 1000) / 60000);
}

/** Разница между поясом пользователя и браузера (мин) — 0, если они совпадают. */
function shiftMin(d: Date): number {
  const tz = displayTz;
  if (!tz || tz === browserTz()) return 0;
  return offsetMin(tz, d) - offsetMin(browserTz(), d);
}

/** Момент времени → «настенное» время пользователя (поля getHours() и т. п. — по его часам). */
export function zoned(d: Date | string): Date {
  const t = new Date(d);
  return new Date(t.getTime() + shiftMin(t) * 60000);
}

/** «Настенное» время пользователя → момент времени. */
export function unzoned(wall: Date): Date {
  const guess = new Date(wall.getTime() - shiftMin(wall) * 60000);
  return new Date(wall.getTime() - shiftMin(guess) * 60000);
}

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

/** Часовой пояс пользователя (для запросов, где сервер считает дни и недели). */
export function timezone(): string {
  return displayTz || browserTz();
}

/** Момент времени → «чч:мм» по часам пользователя. */
export function fmtTime(d: Date | string): string {
  return new Date(d).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", timeZone: timezone() });
}

/** Момент времени → дата по часам пользователя. */
export function fmtDate(d: Date | string, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "long" }): string {
  return new Date(d).toLocaleDateString("ru-RU", { ...opts, timeZone: timezone() });
}

/** «Настенная» дата (день календаря, якорь расписания) — без пересчёта поясов. */
export function fmtDay(wall: Date, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "long" }): string {
  return wall.toLocaleDateString("ru-RU", opts);
}

export function fmtDateTime(d: Date | string): string {
  return `${fmtDate(d, { weekday: "short", day: "numeric", month: "long" })}, ${fmtTime(d)}`;
}

/** Момент времени → значения для <input type="date"> и <input type="time"> по часам пользователя. */
export function toDateInput(d: Date): string {
  const w = zoned(d);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${w.getFullYear()}-${pad(w.getMonth() + 1)}-${pad(w.getDate())}`;
}

export function toTimeInput(d: Date): string {
  const w = zoned(d);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(w.getHours())}:${pad(w.getMinutes())}`;
}

/** Дата и время из полей формы (по часам пользователя) → момент времени. */
export function fromInputs(date: string, time: string): Date {
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  return unzoned(new Date(y, m - 1, d, hh, mm));
}

export function pluralLessons(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  const word =
    mod10 === 1 && mod100 !== 11 ? "занятие" : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? "занятия" : "занятий";
  return `${n} ${word}`;
}
