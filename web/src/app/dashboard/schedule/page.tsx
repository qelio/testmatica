"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { MonthGrid, rangeFor, TimeGrid, type View } from "@/components/calendar";
import { CreateLessonModal, LessonModal, type LessonPreset } from "@/components/lesson-modals";
import { Alert, Button, Spinner } from "@/components/ui";
import { type Lesson, schedule } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { addDays, fmtDate, fmtDateTime, fromInputs } from "@/lib/dates";
import { useLoad } from "@/lib/hooks";

const VIEWS: { value: View; label: string }[] = [
  { value: "day", label: "День" },
  { value: "week", label: "Неделя" },
  { value: "month", label: "Месяц" },
];

function title(view: View, anchor: Date, days: Date[]): string {
  if (view === "day") return fmtDate(anchor, { weekday: "long", day: "numeric", month: "long" });
  if (view === "month") {
    const s = fmtDate(anchor, { month: "long", year: "numeric" });
    return s.charAt(0).toUpperCase() + s.slice(1);
  }
  const first = days[0];
  const last = days[6];
  return first.getMonth() === last.getMonth()
    ? `${first.getDate()}–${fmtDate(last)}`
    : `${fmtDate(first)} – ${fmtDate(last)}`;
}

export default function SchedulePage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Schedule />
    </Suspense>
  );
}

/** ?group=&date=&time=&duration=&weekdays=0,2&count= — серия занятий группы (из запущенного набора). */
function presetFrom(params: URLSearchParams): { at: Date; preset: LessonPreset } | null {
  const group = params.get("group");
  const date = params.get("date");
  if (!group || !date) return null;
  const weekdays = (params.get("weekdays") ?? "").split(",").filter(Boolean).map(Number);
  return {
    at: fromInputs(date, params.get("time") ?? "18:00"),
    preset: {
      groupId: group,
      weekdays,
      duration: Number(params.get("duration")) || undefined,
      count: Number(params.get("count")) || undefined,
    },
  };
}

function Schedule() {
  const { user } = useAuth();
  const params = useSearchParams();
  const router = useRouter();
  const [fromLink] = useState(() => presetFrom(params));
  const isTeacher = !!user?.roles.includes("teacher");
  const [view, setView] = useState<View>("week");
  const [anchor, setAnchor] = useState(() => fromLink?.at ?? new Date());
  const [open, setOpen] = useState<Lesson | null>(null);
  const [creating, setCreating] = useState<Date | null | false>(fromLink?.at ?? false);
  const [notice, setNotice] = useState<string>();

  const { from, to, days } = rangeFor(view, anchor);
  const lessons = useLoad(() => schedule.lessons(from, to), [from.toISOString(), to.toISOString()]);
  const requests = useLoad(() => schedule.requests(), []);

  function shift(dir: -1 | 1) {
    if (view === "day") setAnchor((a) => addDays(a, dir));
    else if (view === "week") setAnchor((a) => addDays(a, 7 * dir));
    else setAnchor((a) => new Date(a.getFullYear(), a.getMonth() + dir, 1));
  }

  function refresh(message?: string) {
    setOpen(null);
    setCreating(false);
    setNotice(message);
    lessons.reload();
    requests.reload();
  }

  const incoming = (requests.data ?? []).filter((r) => !r.requested_by_me);

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Расписание</h1>
        {isTeacher && <Button onClick={() => setCreating(null)}>Новое занятие</Button>}
      </div>

      {notice && (
        <div onClick={() => setNotice(undefined)}>
          <Alert kind="success">{notice}</Alert>
        </div>
      )}

      {incoming.length > 0 && (
        <div className="space-y-2">
          {incoming.map((r) => (
            <button
              key={r.id}
              onClick={() => setOpen(r.lesson)}
              className="flex w-full flex-wrap items-center justify-between gap-2 rounded-2xl border border-tutor/40 bg-tutor/10 px-4 py-3 text-left text-sm"
            >
              <span>
                Предлагают перенести занятие <b>{r.lesson.title}</b> с {fmtDateTime(r.lesson.starts_at)} на{" "}
                <b>{fmtDateTime(r.new_starts_at)}</b>
              </span>
              <span className="font-medium text-brand">Ответить →</span>
            </button>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" className="h-9" onClick={() => setAnchor(new Date())}>
          Сегодня
        </Button>
        <div className="flex">
          <Button variant="ghost" className="h-9 px-3" aria-label="Назад" onClick={() => shift(-1)}>
            ←
          </Button>
          <Button variant="ghost" className="h-9 px-3" aria-label="Вперёд" onClick={() => shift(1)}>
            →
          </Button>
        </div>
        <h2 className="min-w-0 flex-1 text-lg font-semibold">{title(view, anchor, days)}</h2>
        <div className="flex rounded-xl border border-line bg-muted p-1 text-sm" role="tablist">
          {VIEWS.map((v) => (
            <button
              key={v.value}
              role="tab"
              aria-selected={view === v.value}
              onClick={() => setView(v.value)}
              className={`rounded-lg px-3 py-1 font-medium ${view === v.value ? "bg-surface shadow-sm" : "text-fg-soft hover:text-fg"}`}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>

      {isTeacher && (
        <div className="flex gap-4 text-xs text-fg-soft">
          <span className="flex items-center gap-1.5">
            <span className="h-3 w-3 rounded-sm bg-school/60" /> бесплатные
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-3 w-3 rounded-sm bg-tutor/60" /> платные
          </span>
        </div>
      )}

      {lessons.error && <Alert>{lessons.error}</Alert>}
      {!lessons.data && !lessons.error ? (
        <Spinner />
      ) : view === "month" ? (
        <MonthGrid
          anchor={anchor}
          lessons={lessons.data ?? []}
          onOpen={setOpen}
          onDay={(d) => {
            setAnchor(d);
            setView("day");
          }}
        />
      ) : (
        <TimeGrid
          days={days}
          lessons={lessons.data ?? []}
          onOpen={setOpen}
          onSlot={isTeacher ? (at) => setCreating(at) : undefined}
        />
      )}

      {!isTeacher && lessons.data?.length === 0 && (
        <p className="text-sm text-fg-soft">На этот период занятий нет.</p>
      )}

      <LessonModal
        lesson={open}
        isTeacher={isTeacher}
        onClose={() => setOpen(null)}
        onChanged={(msg) => {
          refresh(msg);
        }}
      />
      {isTeacher && (
        <CreateLessonModal
          open={creating !== false}
          initial={creating || null}
          preset={creating && fromLink && creating === fromLink.at ? fromLink.preset : undefined}
          onClose={() => {
            setCreating(false);
            if (fromLink) router.replace("/dashboard/schedule");
          }}
          onCreated={(msg) => {
            refresh(msg);
            if (fromLink) router.replace("/dashboard/schedule");
          }}
        />
      )}
    </div>
  );
}
