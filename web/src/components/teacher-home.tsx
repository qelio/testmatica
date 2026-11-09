"use client";

import Link from "next/link";
import { useState } from "react";

import { assessment, type Lesson, marketplace, schedule } from "@/lib/api";
import { summary } from "@/lib/assignments";
import { addDays, fmtDate, fmtTime, sameDay, startOfDay, unzoned, zoned } from "@/lib/dates";
import { useLoad } from "@/lib/hooks";

/** Главная педагога: сводка дня — занятия, работы на проверку, переносы и заявки, быстрые действия. */
export function TeacherHome() {
  // Занятия — с начала сегодняшнего дня (по часам пользователя) на неделю вперёд.
  const today = startOfDay(zoned(new Date()));
  const lessons = useLoad(() => schedule.lessons(unzoned(today), unzoned(addDays(today, 7))), []);
  const assignments = useLoad(() => assessment.assignments("teacher"), []);
  const requests = useLoad(() => schedule.requests(), []);
  // Заявки учеников по предметам педагога (если у него нет анкеты репетитора — просто не показываем).
  const open = useLoad(() => marketplace.openRequests({}).catch(() => []), []);

  const [now] = useState(() => Date.now());
  const active = (lessons.data ?? []).filter((l) => l.status === "scheduled" && new Date(l.ends_at).getTime() > now);
  const todayLessons = active.filter((l) => sameDay(zoned(l.starts_at), today));
  const upcoming = active.slice(0, 6);
  const toReview = (assignments.data ?? [])
    .map((a) => ({ a, n: summary(a).toReview }))
    .filter((x) => x.n > 0);
  const incoming = (requests.data ?? []).filter((r) => !r.requested_by_me);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile href="/dashboard/schedule" value={lessons.data ? todayLessons.length : null} label="занятий сегодня" tone="brand" />
        <Tile
          href="/dashboard/assignments"
          value={assignments.data ? toReview.reduce((s, x) => s + x.n, 0) : null}
          label="работ ждут проверки"
          tone="tutor"
        />
        <Tile href="/dashboard/schedule" value={requests.data ? incoming.length : null} label="предложений переноса" tone="school" />
        <Tile href="/dashboard/requests" value={open.data ? open.data.length : null} label="заявок учеников" tone="ok" />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="rounded-2xl border border-line bg-surface">
          <div className="flex items-center justify-between border-b border-line px-5 py-4">
            <h2 className="font-semibold">Ближайшие занятия</h2>
            <Link href="/dashboard/schedule" className="text-sm text-brand-text hover:underline">
              Расписание
            </Link>
          </div>
          {!lessons.data ? (
            <p className="px-5 py-6 text-sm text-fg-soft">Загрузка…</p>
          ) : upcoming.length === 0 ? (
            <p className="px-5 py-6 text-sm text-fg-soft">На этой неделе занятий нет.</p>
          ) : (
            <ul className="divide-y divide-line">
              {upcoming.map((l) => (
                <LessonRow key={l.id} lesson={l} today={today} now={now} />
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-2xl border border-line bg-surface">
          <div className="flex items-center justify-between border-b border-line px-5 py-4">
            <h2 className="font-semibold">Ждут вашей проверки</h2>
            <Link href="/dashboard/assignments" className="text-sm text-brand-text hover:underline">
              Все тесты
            </Link>
          </div>
          {!assignments.data ? (
            <p className="px-5 py-6 text-sm text-fg-soft">Загрузка…</p>
          ) : toReview.length === 0 ? (
            <p className="px-5 py-6 text-sm text-fg-soft">Всё проверено 👍</p>
          ) : (
            <ul className="divide-y divide-line">
              {toReview.slice(0, 6).map(({ a, n }) => (
                <li key={a.id}>
                  <Link href={`/dashboard/assignments/${a.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-muted">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{a.title}</span>
                      <span className="block truncate text-sm text-fg-soft">{a.target_title}</span>
                    </span>
                    <span className="shrink-0 rounded-full bg-tutor/15 px-2.5 py-0.5 text-sm font-medium text-tutor">{n}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="flex flex-wrap gap-2">
        {[
          ["/dashboard/schedule", "Запланировать занятие"],
          ["/dashboard/assignments/new", "Назначить тест"],
          ["/dashboard/tests/new", "Новый тест"],
          ["/dashboard/tasks", "Банк задач"],
          ["/dashboard/journal", "Журнал"],
          ["/dashboard/groups", "Ученики и группы"],
        ].map(([href, label]) => (
          <Link key={href} href={href} className="rounded-xl border border-line bg-surface px-4 py-2.5 text-sm font-medium hover:bg-muted">
            {label}
          </Link>
        ))}
      </section>
    </div>
  );
}

const TONES = {
  brand: "text-brand-text",
  tutor: "text-tutor",
  school: "text-school",
  ok: "text-ok",
} as const;

function Tile({ href, value, label, tone }: { href: string; value: number | null; label: string; tone: keyof typeof TONES }) {
  return (
    <Link href={href} className="rounded-2xl border border-line bg-surface px-4 py-3 hover:border-brand/50">
      <span className={`block text-3xl font-semibold tabular-nums ${value ? TONES[tone] : "text-fg-soft"}`}>{value ?? "…"}</span>
      <span className="block text-sm text-fg-soft">{label}</span>
    </Link>
  );
}

function LessonRow({ lesson, today, now }: { lesson: Lesson; today: Date; now: number }) {
  // Комната педагогу открыта за 30 минут до начала.
  const live = new Date(lesson.starts_at).getTime() <= now + 30 * 60_000;
  const day = zoned(lesson.starts_at);
  const when = sameDay(day, today) ? "сегодня" : sameDay(day, addDays(today, 1)) ? "завтра" : fmtDate(lesson.starts_at, { weekday: "short", day: "numeric", month: "short" });
  return (
    <li className="flex items-center gap-3 px-5 py-3">
      <span className="w-20 shrink-0 text-sm">
        <span className="block font-semibold tabular-nums">{fmtTime(lesson.starts_at)}</span>
        <span className="block text-xs text-fg-soft">{when}</span>
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium">{lesson.title}</span>
        <span className="block truncate text-sm text-fg-soft">
          {[lesson.subject, lesson.topic, `${lesson.duration_min} мин`].filter(Boolean).join(" · ")}
        </span>
      </span>
      {live && (
        <Link href={`/room/${lesson.id}`} className="shrink-0 rounded-xl bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-strong">
          Войти
        </Link>
      )}
    </li>
  );
}
