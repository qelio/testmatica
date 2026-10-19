"use client";

import type { BellSchedule, Lesson } from "@/lib/api";
import { addDays, fmtTime, sameDay, startOfWeek, unzoned, WEEKDAYS_SHORT, zoned } from "@/lib/dates";

// Дни и часы сетки — «настенное» время пользователя (lib/dates): занятия ставятся по zoned(начало).

export type View = "day" | "week" | "month";

const DAY_START = 7; // первая строка сетки — 07:00
const DAY_END = 23;
const HOUR_PX = 56;

function lessonColors(lesson: Lesson): string {
  if (lesson.status === "cancelled") return "border-line bg-muted text-fg-soft line-through";
  // Платные занятия — оранжевые, бесплатные — синие.
  return lesson.paid
    ? "border-tutor/60 bg-tutor/15 text-fg hover:bg-tutor/25"
    : "border-school/60 bg-school/15 text-fg hover:bg-school/25";
}

/** Раскладка пересекающихся занятий одного дня по колонкам (у ученика бывают занятия разных педагогов). */
function layout(lessons: Lesson[]): { lesson: Lesson; col: number; cols: number }[] {
  const sorted = [...lessons].sort((a, b) => +new Date(a.starts_at) - +new Date(b.starts_at));
  const result: { lesson: Lesson; col: number; cols: number }[] = [];
  let cluster: typeof result = [];
  let clusterEnd = 0;
  const flush = () => {
    const cols = Math.max(1, ...cluster.map((c) => c.col + 1));
    cluster.forEach((c) => result.push({ ...c, cols }));
    cluster = [];
  };
  for (const lesson of sorted) {
    const start = +new Date(lesson.starts_at);
    const end = +new Date(lesson.ends_at);
    if (cluster.length && start >= clusterEnd) flush();
    const used = new Set(cluster.filter((c) => +new Date(c.lesson.ends_at) > start).map((c) => c.col));
    let col = 0;
    while (used.has(col)) col++;
    cluster.push({ lesson, col, cols: 1 });
    clusterEnd = Math.max(clusterEnd, end);
  }
  if (cluster.length) flush();
  return result;
}

export function TimeGrid({
  days,
  lessons,
  onOpen,
  onSlot,
  bells,
}: {
  days: Date[];
  lessons: Lesson[];
  onOpen: (lesson: Lesson) => void;
  onSlot?: (at: Date) => void;
  /** Расписание звонков педагога — полосы уроков с номерами (решение №55). */
  bells?: BellSchedule | null;
}) {
  const hours = Array.from({ length: DAY_END - DAY_START }, (_, i) => DAY_START + i);
  const periods = (bells?.periods ?? []).map((p, i) => {
    const [sh, sm] = p.start.split(":").map(Number);
    const [eh, em] = p.end.split(":").map(Number);
    const top = ((sh * 60 + sm - DAY_START * 60) / 60) * HOUR_PX;
    return { n: i + 1, top, height: (((eh - sh) * 60 + (em - sm)) / 60) * HOUR_PX, label: `${p.start}–${p.end}` };
  });
  const showBells = periods.length > 0 && days.some((d) => bells!.weekdays.includes((d.getDay() + 6) % 7));
  // Со звонками столбец времени шире: слева — номер и время урока, справа — часы, не налезают друг на друга.
  const timeCol = showBells ? 132 : 56;
  const today = zoned(new Date());
  return (
    <div className="overflow-x-auto rounded-2xl border border-line bg-surface">
      <div className="min-w-[640px]" style={{ minWidth: days.length === 1 ? 0 : undefined }}>
        <div className="sticky top-0 z-10 grid border-b border-line bg-surface" style={{ gridTemplateColumns: `${timeCol}px repeat(${days.length}, 1fr)` }}>
          <div />
          {days.map((d) => (
            <div key={d.toISOString()} className="border-l border-line px-2 py-2 text-center text-sm">
              <span className="text-fg-soft">{WEEKDAYS_SHORT[(d.getDay() + 6) % 7]}</span>{" "}
              <span
                className={`inline-grid h-7 min-w-7 place-items-center rounded-full font-semibold ${sameDay(d, today) ? "bg-brand text-white" : ""}`}
              >
                {d.getDate()}
              </span>
            </div>
          ))}
        </div>
        <div className="relative grid" style={{ gridTemplateColumns: `${timeCol}px repeat(${days.length}, 1fr)` }}>
          <div className="relative">
            {hours.map((h) => (
              <div key={h} className="relative text-right text-xs text-fg-soft" style={{ height: HOUR_PX }}>
                <span className="absolute -top-2 right-2">{h}:00</span>
              </div>
            ))}
            {/* Номер урока по звонкам — у шкалы времени, напротив начала урока. */}
            {showBells &&
              periods.map((p) => (
                <span
                  key={p.n}
                  title={`${p.n} урок · ${p.label}`}
                  className="pointer-events-none absolute left-1 flex h-4 items-center gap-1 rounded bg-sun/25 px-1 text-[10px] whitespace-nowrap text-fg tabular-nums"
                  style={{ top: p.top + 2 }}
                >
                  <b className="font-semibold">{p.n}</b>
                  <span className="text-fg-soft">{p.label}</span>
                </span>
              ))}
          </div>
          {days.map((day) => {
            const dayLessons = lessons.filter((l) => sameDay(zoned(l.starts_at), day));
            return (
              <div key={day.toISOString()} className="relative border-l border-line">
                {/* Уроки по звонкам — светлые полосы под занятиями. */}
                {bells?.weekdays.includes((day.getDay() + 6) % 7) &&
                  periods.map((p) => (
                    <div
                      key={p.n}
                      aria-hidden
                      title={`${p.n} урок · ${p.label}`}
                      className="pointer-events-none absolute inset-x-0 border-y border-sun/40 bg-sun/[0.12]"
                      style={{ top: p.top, height: p.height }}
                    />
                  ))}
                {hours.map((h) => (
                  <button
                    key={h}
                    type="button"
                    aria-label={onSlot ? `Новое занятие ${h}:00` : undefined}
                    disabled={!onSlot}
                    onClick={() => onSlot?.(unzoned(new Date(day.getFullYear(), day.getMonth(), day.getDate(), h)))}
                    className="block w-full border-b border-line/60 enabled:hover:bg-muted/60"
                    style={{ height: HOUR_PX }}
                  />
                ))}
                {layout(dayLessons).map(({ lesson, col, cols }) => {
                  const start = zoned(lesson.starts_at);
                  const minutes = (start.getHours() - DAY_START) * 60 + start.getMinutes();
                  const top = Math.max(0, (minutes / 60) * HOUR_PX);
                  const height = Math.max(22, (lesson.duration_min / 60) * HOUR_PX - 2);
                  return (
                    <button
                      key={lesson.id}
                      onClick={() => onOpen(lesson)}
                      className={`absolute overflow-hidden rounded-lg border-l-4 px-1.5 py-1 text-left text-xs transition-colors ${lessonColors(lesson)}`}
                      style={{ top, height, left: `calc(${(col / cols) * 100}% + 2px)`, width: `calc(${100 / cols}% - 4px)` }}
                    >
                      <span className="block font-semibold">{fmtTime(lesson.starts_at)} {lesson.title}</span>
                      {height > 36 && lesson.subject && <span className="block truncate text-fg-soft">{lesson.subject}</span>}
                      {lesson.pending_reschedule && <span className="block text-tutor">перенос?</span>}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export function MonthGrid({
  anchor,
  lessons,
  onOpen,
  onDay,
}: {
  anchor: Date;
  lessons: Lesson[];
  onOpen: (lesson: Lesson) => void;
  onDay: (day: Date) => void;
}) {
  const first = startOfWeek(new Date(anchor.getFullYear(), anchor.getMonth(), 1));
  const days = Array.from({ length: 42 }, (_, i) => addDays(first, i));
  const today = zoned(new Date());
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface">
      <div className="grid grid-cols-7 border-b border-line text-center text-xs text-fg-soft">
        {WEEKDAYS_SHORT.map((w) => (
          <div key={w} className="py-2">
            {w}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {days.map((day) => {
          const inMonth = day.getMonth() === anchor.getMonth();
          const dayLessons = lessons
            .filter((l) => sameDay(zoned(l.starts_at), day))
            .sort((a, b) => +new Date(a.starts_at) - +new Date(b.starts_at));
          return (
            <div key={day.toISOString()} className={`min-h-24 border-b border-r border-line p-1 ${inMonth ? "" : "bg-muted/40"}`}>
              <button
                onClick={() => onDay(day)}
                className={`mb-1 grid h-6 min-w-6 place-items-center rounded-full px-1 text-xs font-medium hover:bg-muted ${sameDay(day, today) ? "bg-brand text-white hover:bg-brand-strong" : inMonth ? "" : "text-fg-soft"}`}
              >
                {day.getDate()}
              </button>
              <div className="space-y-0.5">
                {dayLessons.slice(0, 3).map((lesson) => (
                  <button
                    key={lesson.id}
                    onClick={() => onOpen(lesson)}
                    className={`block w-full truncate rounded border-l-2 px-1 text-left text-[11px] ${lessonColors(lesson)}`}
                  >
                    {fmtTime(lesson.starts_at)} {lesson.title}
                  </button>
                ))}
                {dayLessons.length > 3 && (
                  <button onClick={() => onDay(day)} className="px-1 text-[11px] text-fg-soft hover:text-fg">
                    ещё {dayLessons.length - 3}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Видимый период: from/to — «настенные» (для запроса к серверу — unzoned), days — дни сетки. */
export function rangeFor(view: View, anchor: Date): { from: Date; to: Date; days: Date[] } {
  if (view === "day") {
    const from = new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate());
    return { from, to: addDays(from, 1), days: [from] };
  }
  if (view === "week") {
    const from = startOfWeek(anchor);
    return { from, to: addDays(from, 7), days: Array.from({ length: 7 }, (_, i) => addDays(from, i)) };
  }
  const from = startOfWeek(new Date(anchor.getFullYear(), anchor.getMonth(), 1));
  return { from, to: addDays(from, 42), days: [] };
}
