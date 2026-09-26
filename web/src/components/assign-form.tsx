"use client";

import { useState } from "react";

import { Alert, Button, Field, Select } from "@/components/ui";
import { academic, type Assignment, type AssignmentKind, assessment, classroom, schedule } from "@/lib/api";
import { fmtDateTime, fromInputs } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

export type AssignPreset = {
  testId?: string;
  kind?: AssignmentKind;
  targetType?: "group" | "student";
  targetId?: string;
  lessonId?: string;
};

const KINDS: { kind: AssignmentKind; title: string; hint: string }[] = [
  { kind: "test", title: "Тест", hint: "Самостоятельная работа без привязки к уроку: ученики проходят, пока тест открыт." },
  { kind: "homework", title: "ДЗ к уроку", hint: "Домашнее задание к занятию — ученики увидят его в карточке урока в расписании." },
  {
    kind: "live",
    title: "Тест на уроке",
    hint: "Проходят во время занятия, вы видите прогресс каждого. Когда закончите — завершите тест, незавершённые работы сдадутся.",
  },
];
const ATTEMPTS: { value: string; title: string }[] = [
  { value: "1", title: "Одна" },
  { value: "2", title: "Две" },
  { value: "3", title: "Три" },
  { value: "5", title: "Пять" },
  { value: "", title: "Без ограничений" },
];

/** Дата и время одной парой полей; пусто — не задано. */
function When({ label, date, time, onDate, onTime }: { label: string; date: string; time: string; onDate: (v: string) => void; onTime: (v: string) => void }) {
  return (
    <div className="grid grid-cols-[1fr_7rem] gap-2">
      <Field label={label} type="date" value={date} onChange={(e) => onDate(e.target.value)} />
      <Field label="Время" type="time" value={time} disabled={!date} onChange={(e) => onTime(e.target.value)} />
    </div>
  );
}

/** Назначение теста: какой тест, кому, как (тест / ДЗ / на уроке), когда открыть и закрыть, сколько попыток. */
export function AssignForm({ preset, onAssigned }: { preset: AssignPreset; onAssigned: (a: Assignment) => void }) {
  const tests = useLoad(() => assessment.tests(), []);
  const groups = useLoad(() => classroom.groups(), []);
  const students = useLoad(() => classroom.students(), []);
  // Уроки за месяц назад и на два вперёд — к какому привязать тест и куда ставить оценку.
  const lessons = useLoad(() => {
    const now = Date.now();
    return schedule.lessons(new Date(now - 30 * 864e5), new Date(now + 60 * 864e5));
  }, []);
  const gradeTypes = useLoad(() => academic.gradeTypes(), []);

  const [testId, setTestId] = useState(preset.testId ?? "");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<AssignmentKind>(preset.kind ?? (preset.lessonId ? "homework" : "test"));
  const [targetType, setTargetType] = useState<"group" | "student">(preset.targetType ?? "group");
  const [targetId, setTargetId] = useState(preset.targetId ?? "");
  const [lessonId, setLessonId] = useState(preset.lessonId ?? "");
  const [openDate, setOpenDate] = useState("");
  const [openTime, setOpenTime] = useState("08:00");
  const [closeDate, setCloseDate] = useState("");
  const [closeTime, setCloseTime] = useState("20:00");
  const [attempts, setAttempts] = useState("1");
  const [toJournal, setToJournal] = useState(false);
  const [gradeTypeId, setGradeTypeId] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const withLesson = kind !== "test";
  const targetLessons = (lessons.data ?? []).filter(
    (l) =>
      l.status !== "cancelled" &&
      (targetType === "group" ? l.group_id === targetId : l.kind === "individual" && l.participants?.some((p) => p.id === targetId)),
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    const lesson = withLesson ? lessonId || null : null;
    try {
      onAssigned(
        await assessment.assign(testId, {
          kind,
          title: title.trim() || null,
          target_type: targetType,
          target_id: targetId,
          lesson_id: lesson,
          opens_at: openDate ? fromInputs(openDate, openTime).toISOString() : null,
          deadline: closeDate ? fromInputs(closeDate, closeTime).toISOString() : null,
          max_attempts: attempts ? Number(attempts) : null,
          grade_to_journal: toJournal && !!lesson,
          grade_type_id: toJournal && lesson ? gradeTypeId || null : null,
        }),
      );
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const tab = (active: boolean) =>
    `flex-1 rounded-lg px-3 py-1.5 text-sm font-medium whitespace-nowrap ${active ? "bg-surface shadow-sm" : "text-fg-soft hover:text-fg"}`;

  return (
    <form className="space-y-5" onSubmit={submit}>
      {error && <Alert>{error}</Alert>}
      <Select label="Тест" value={testId} required onChange={(e) => setTestId(e.target.value)}>
        <option value="">{tests.data && !tests.data.length ? "Сначала создайте тест" : "Выберите тест"}</option>
        {tests.data?.map((t) => (
          <option key={t.id} value={t.id}>
            {t.title} · заданий: {t.tasks_count}
          </option>
        ))}
      </Select>
      <Field
        label="Название для учеников"
        maxLength={200}
        value={title}
        placeholder={tests.data?.find((t) => t.id === testId)?.title ?? "Например: ДЗ к уроку 12 марта"}
        hint="Так назначение увидят ученики, в журнале и уведомлениях. Не заполните — будет как у теста."
        onChange={(e) => setTitle(e.target.value)}
      />

      <div className="space-y-2">
        <div className="flex flex-wrap rounded-xl border border-line bg-muted p-1" role="radiogroup" aria-label="Как назначить">
          {KINDS.map((k) => (
            <button key={k.kind} type="button" role="radio" aria-checked={kind === k.kind} className={tab(kind === k.kind)} onClick={() => setKind(k.kind)}>
              {k.title}
            </button>
          ))}
        </div>
        <p className="text-sm text-fg-soft">{KINDS.find((k) => k.kind === kind)?.hint}</p>
      </div>

      <div className="grid grid-cols-[auto_1fr] items-end gap-3">
        <Select
          label="Кому"
          value={targetType}
          onChange={(e) => {
            setTargetType(e.target.value as "group" | "student");
            setTargetId("");
            setLessonId("");
          }}
        >
          <option value="group">Группе</option>
          <option value="student">Ученику</option>
        </Select>
        <Select
          label={targetType === "group" ? "Группа" : "Ученик"}
          value={targetId}
          required
          onChange={(e) => {
            setTargetId(e.target.value);
            setLessonId("");
          }}
        >
          <option value="">Выберите</option>
          {targetType === "group"
            ? groups.data?.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.title}
                </option>
              ))
            : students.data
                ?.filter((s) => s.status === "active")
                .map((s) => (
                  <option key={s.student_id} value={s.student_id}>
                    {s.full_name}
                  </option>
                ))}
        </Select>
      </div>

      {withLesson && (
        <Select label="Урок" value={lessonId} required disabled={!targetId} onChange={(e) => setLessonId(e.target.value)}>
          <option value="">{targetId ? (targetLessons.length ? "Выберите урок" : "Уроков рядом нет") : "Сначала выберите, кому"}</option>
          {targetLessons.map((l) => (
            <option key={l.id} value={l.id}>
              {fmtDateTime(l.starts_at)}
              {l.topic ? ` · ${l.topic}` : l.subject ? ` · ${l.subject}` : ""}
            </option>
          ))}
        </Select>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <When label="Откроется (пусто — сразу)" date={openDate} time={openTime} onDate={setOpenDate} onTime={setOpenTime} />
        <When label="Закроется (пусто — без срока)" date={closeDate} time={closeTime} onDate={setCloseDate} onTime={setCloseTime} />
      </div>

      <fieldset>
        <legend className="mb-1.5 text-sm font-medium">Сколько раз можно пройти</legend>
        <div className="flex flex-wrap gap-1.5">
          {ATTEMPTS.map((o) => (
            <button
              key={o.value || "none"}
              type="button"
              aria-pressed={attempts === o.value}
              onClick={() => setAttempts(o.value)}
              className={`rounded-lg border px-3 py-1.5 text-sm ${attempts === o.value ? "border-brand bg-brand/10 text-brand" : "border-line text-fg-soft hover:text-fg"}`}
            >
              {o.title}
            </button>
          ))}
        </div>
        {attempts !== "1" && <p className="mt-1.5 text-xs text-fg-soft">В итог и в журнал идёт лучшая из попыток.</p>}
      </fieldset>

      {withLesson && (
        <label className={`flex items-start gap-3 ${lessonId ? "" : "opacity-50"}`}>
          <input
            type="checkbox"
            checked={toJournal && !!lessonId}
            disabled={!lessonId}
            onChange={(e) => setToJournal(e.target.checked)}
            className="mt-1 h-4 w-4 accent-brand"
          />
          <span className="text-sm">
            <span className="font-medium">Поставить оценку в журнал</span>
            <span className="block text-fg-soft">
              Когда работа проверена: от 85% — 5, от 65% — 4, от 45% — 3, ниже — 2. Оценка появится в колонке выбранного урока.
            </span>
          </span>
        </label>
      )}
      {withLesson && toJournal && lessonId && (
        <Select label="Тип оценки" value={gradeTypeId} required onChange={(e) => setGradeTypeId(e.target.value)}>
          <option value="">Выберите</option>
          {gradeTypes.data?.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </Select>
      )}

      <Button type="submit" loading={busy} disabled={!testId || !targetId || (withLesson && !lessonId)} className="w-full">
        {kind === "live" && !openDate ? "Запустить тест" : "Назначить"}
      </Button>
    </form>
  );
}
