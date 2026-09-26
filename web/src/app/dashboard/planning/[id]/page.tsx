"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { ExamItemsByIds } from "@/components/exams";
import { EMPTY_LESSON, LessonForm, PlanItems } from "@/components/plan-lesson-form";
import { Alert, Button, Field, Spinner } from "@/components/ui";
import { type Plan, type PlanLesson, planning } from "@/lib/api";
import { fmtDate, fmtTime, toDateInput } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

function slotLabel(s: Plan["slots"][number]): string {
  return `${fmtDate(s.starts_at, { weekday: "short", day: "numeric", month: "short" })}, ${fmtTime(s.starts_at)}`;
}

export default function PlanPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const plan = useLoad(() => planning.plan(id), [id]);
  const [error, setError] = useState<string>();
  const [info, setInfo] = useState<string>();
  const [adding, setAdding] = useState<string | "end" | null>(null);
  const [from, setFrom] = useState("");

  async function act(action: () => Promise<unknown>, message?: string) {
    setError(undefined);
    setInfo(undefined);
    try {
      await action();
      if (message) setInfo(message);
      plan.reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  if (plan.error) return <Alert>{plan.error}</Alert>;
  if (!plan.data) return <Spinner />;
  const p = plan.data;
  const done = p.lessons.filter((l) => l.done).length;

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <Link href="/dashboard/planning" className="text-sm text-fg-soft hover:text-fg">
        ← Планирование
      </Link>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{p.title}</h1>
        <p className="mt-1 text-sm text-fg-soft">
          {[p.target_title, p.subject, `уроков: ${p.lessons.length}`, `пройдено: ${done}`, `занятий в расписании: ${p.slots.length}`]
            .filter(Boolean)
            .join(" · ")}
        </p>
      </div>
      {error && <Alert>{error}</Alert>}
      {info && <Alert kind="success">{info}</Alert>}

      <div className="flex flex-wrap items-end gap-2 rounded-2xl border border-line bg-surface p-4">
        <div className="w-44">
          <Field label="Проставить даты с" type="date" value={from || p.start_date || toDateInput(new Date())} onChange={(e) => setFrom(e.target.value)} />
        </div>
        <Button
          variant="secondary"
          className="h-11"
          onClick={() =>
            act(async () => {
              const r = await planning.distribute(p.id, from || p.start_date || null);
              setInfo(
                r.left
                  ? `Даты проставлены: ${r.placed}. Урокам без даты (${r.left}) не хватило занятий — добавьте их в расписание.`
                  : `Даты проставлены: ${r.placed}.`,
              );
            })
          }
        >
          Проставить даты по расписанию
        </Button>
        <span className="text-xs text-fg-soft">Пройденные уроки не сдвигаются; остальные по порядку ложатся на занятия.</span>
        <span className="ml-auto flex gap-2">
          <Button
            variant="ghost"
            className="h-11"
            onClick={() =>
              act(async () => {
                const t = await planning.saveAsTemplate(p.id);
                router.push(`/dashboard/planning/templates/${t.id}`);
              })
            }
          >
            Сохранить как шаблон
          </Button>
          <Button
            variant="ghost"
            className="h-11 text-danger"
            onClick={() =>
              window.confirm("Удалить КТП? Занятия в расписании останутся.") &&
              act(async () => {
                await planning.deletePlan(p.id);
                router.replace("/dashboard/planning");
              })
            }
          >
            Удалить
          </Button>
        </span>
      </div>

      {p.lessons.length === 0 && adding === null && (
        <Alert kind="info">План пуст. Добавляйте уроки сразу или постепенно — по мере того как проходите темы.</Alert>
      )}
      <ol className="space-y-2">
        {p.lessons.map((lesson, i) => (
          <li key={lesson.id} className="space-y-2">
            <LessonRow plan={p} lesson={lesson} n={i + 1} act={act} onAddAfter={() => setAdding(lesson.id)} />
            {adding === lesson.id && (
              <div className="rounded-2xl border border-brand/40 bg-surface p-4">
                <LessonForm
                  submitLabel="Добавить урок"
                  onCancel={() => setAdding(null)}
                  onSubmit={async (data) => {
                    await planning.addLesson(p.id, data, lesson.id);
                    setAdding(null);
                    plan.reload();
                  }}
                />
              </div>
            )}
          </li>
        ))}
      </ol>
      {adding === "end" ? (
        <div className="rounded-2xl border border-brand/40 bg-surface p-4">
          <LessonForm
            initial={EMPTY_LESSON}
            submitLabel="Добавить урок"
            onCancel={() => setAdding(null)}
            onSubmit={async (data) => {
              await planning.addLesson(p.id, data);
              setAdding(null);
              plan.reload();
            }}
          />
        </div>
      ) : (
        <Button variant="secondary" onClick={() => setAdding("end")}>
          + Урок в конец плана
        </Button>
      )}
    </div>
  );
}

function LessonRow({
  plan,
  lesson,
  n,
  act,
  onAddAfter,
}: {
  plan: Plan;
  lesson: PlanLesson;
  n: number;
  act: (action: () => Promise<unknown>, message?: string) => Promise<void>;
  onAddAfter: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const slot = plan.slots.find((s) => s.id === lesson.schedule_lesson_id);
  const homeTests = lesson.home_items.filter((x) => x.kind === "test" && x.ref_id);
  const last = n === plan.lessons.length;

  if (editing) {
    return (
      <div className="rounded-2xl border border-brand/40 bg-surface p-4">
        <p className="mb-3 text-sm font-medium text-fg-soft">Урок {n}</p>
        <LessonForm
          initial={lesson}
          onCancel={() => setEditing(false)}
          onSubmit={async (data) => {
            await planning.updateLesson(plan.id, lesson.id, data);
            setEditing(false);
            await act(async () => {});
          }}
        />
      </div>
    );
  }

  return (
    <div className={`rounded-2xl border bg-surface p-4 ${lesson.done ? "border-ok/40" : "border-line"}`}>
      <div className="grid gap-x-4 gap-y-3 md:grid-cols-[2rem_12rem_minmax(0,1fr)]">
        <label className="flex items-start gap-2 md:flex-col md:items-center" title="Урок пройден">
          <span className="text-lg font-semibold text-fg-soft tabular-nums">{n}</span>
          <input
            type="checkbox"
            checked={lesson.done}
            onChange={(e) => act(() => planning.updateLesson(plan.id, lesson.id, { done: e.target.checked }))}
            className="mt-1 h-5 w-5 accent-ok"
            aria-label={`Урок ${n} пройден`}
          />
        </label>
        <div>
          <select
            value={lesson.schedule_lesson_id ?? ""}
            onChange={(e) => act(() => planning.updateLesson(plan.id, lesson.id, { schedule_lesson_id: e.target.value || null }))}
            aria-label={`Занятие для урока ${n}`}
            className="h-10 w-full rounded-lg border border-line bg-surface px-2 text-sm"
          >
            <option value="">{lesson.planned_date && !slot ? fmtDate(lesson.planned_date) : "Без даты"}</option>
            {lesson.schedule_lesson_id && !slot && <option value={lesson.schedule_lesson_id}>{lesson.planned_date ? fmtDate(lesson.planned_date) : "Занятие"}</option>}
            {plan.slots.map((s) => (
              <option key={s.id} value={s.id}>
                {slotLabel(s)}
              </option>
            ))}
          </select>
          {slot?.topic && slot.topic !== lesson.topic && <p className="mt-1 text-xs text-fg-soft">В расписании: {slot.topic}</p>}
        </div>
        <div className="min-w-0 space-y-2">
          <p className={`font-medium ${lesson.done ? "text-fg-soft line-through decoration-ok/60" : ""}`}>{lesson.topic}</p>
          {lesson.goals && <p className="text-sm text-fg-soft">{lesson.goals}</p>}
          {(lesson.class_items.length > 0 || lesson.home_items.length > 0) && (
            <div className="grid gap-2 text-sm sm:grid-cols-2">
              <div>
                <p className="text-xs font-medium tracking-wide text-fg-soft uppercase">К уроку</p>
                <PlanItems items={lesson.class_items} />
              </div>
              <div>
                <p className="text-xs font-medium tracking-wide text-fg-soft uppercase">На дом</p>
                <PlanItems items={lesson.home_items} />
                {homeTests.map((t) => (
                  <Link
                    key={t.ref_id}
                    href={`/dashboard/assignments/new?${new URLSearchParams({
                      test: t.ref_id!,
                      kind: "homework",
                      target_type: plan.target_type,
                      target: plan.target_id,
                      ...(lesson.schedule_lesson_id ? { lesson: lesson.schedule_lesson_id } : {}),
                    })}`}
                    className="mt-1 block text-sm font-medium text-brand hover:underline"
                  >
                    Назначить «{t.title}» как ДЗ
                  </Link>
                ))}
              </div>
            </div>
          )}
          {lesson.exam_item_ids.length > 0 && (
            <div className="text-sm">
              <ExamItemsByIds ids={lesson.exam_item_ids} />
            </div>
          )}
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-sm">
            <button className="text-brand hover:underline" onClick={() => setEditing(true)}>
              Изменить
            </button>
            <button className="text-fg-soft hover:text-fg" onClick={onAddAfter}>
              + урок после
            </button>
            <button className="text-fg-soft hover:text-fg disabled:opacity-30" disabled={n === 1} onClick={() => act(() => planning.moveLesson(plan.id, lesson.id, n - 2))}>
              ↑ выше
            </button>
            <button className="text-fg-soft hover:text-fg disabled:opacity-30" disabled={last} onClick={() => act(() => planning.moveLesson(plan.id, lesson.id, n))}>
              ↓ ниже
            </button>
            <button
              className="text-fg-soft hover:text-danger"
              onClick={() => window.confirm(`Удалить урок «${lesson.topic}»?`) && act(() => planning.deleteLesson(plan.id, lesson.id))}
            >
              Удалить
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
