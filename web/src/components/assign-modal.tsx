"use client";

import { useState } from "react";

import { Alert, Button, Field, Modal, Select } from "@/components/ui";
import { academic, type Assignment, assessment, classroom, schedule } from "@/lib/api";
import { fmtDateTime, fromInputs } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

type Kind = "homework" | "live";
export type AssignPreset = { targetType: "group" | "student"; targetId: string; lessonId: string };

/** Выдать тест: как ДЗ (дедлайн) или как тест на уроке; группе или ученику; оценка — в журнал урока. */
export function AssignModal({
  testId,
  open,
  onClose,
  onAssigned,
  initialKind = "homework",
  preset,
}: {
  testId: string;
  open: boolean;
  onClose: () => void;
  onAssigned: (a: Assignment) => void;
  initialKind?: Kind;
  preset?: AssignPreset;
}) {
  return (
    <Modal open={open} onClose={onClose} title="Выдать тест">
      {open && <AssignForm testId={testId} onAssigned={onAssigned} initialKind={initialKind} preset={preset} />}
    </Modal>
  );
}

function AssignForm({
  testId,
  onAssigned,
  initialKind,
  preset,
}: {
  testId: string;
  onAssigned: (a: Assignment) => void;
  initialKind: Kind;
  preset?: AssignPreset;
}) {
  const groups = useLoad(() => classroom.groups(), []);
  const students = useLoad(() => classroom.students(), []);
  // Уроки за последнюю неделю и на две недели вперёд — к какому привязать работу и куда ставить оценку.
  const lessons = useLoad(() => {
    const now = Date.now();
    return schedule.lessons(new Date(now - 7 * 864e5), new Date(now + 14 * 864e5));
  }, []);
  const gradeTypes = useLoad(() => academic.gradeTypes(), []);

  const [kind, setKind] = useState<Kind>(initialKind);
  const [targetType, setTargetType] = useState<"group" | "student">(preset?.targetType ?? "group");
  const [targetId, setTargetId] = useState(preset?.targetId ?? "");
  const [deadlineDate, setDeadlineDate] = useState("");
  const [deadlineTime, setDeadlineTime] = useState("20:00");
  const [lessonId, setLessonId] = useState(preset?.lessonId ?? "");
  const [toJournal, setToJournal] = useState(false);
  const [gradeTypeId, setGradeTypeId] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const targetLessons = (lessons.data ?? []).filter(
    (l) =>
      l.status === "scheduled" &&
      (targetType === "group" ? l.group_id === targetId : l.kind === "individual" && l.participants?.some((p) => p.id === targetId)),
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      onAssigned(
        await assessment.assign(testId, {
          kind,
          target_type: targetType,
          target_id: targetId,
          lesson_id: lessonId || null,
          deadline: kind === "homework" && deadlineDate ? fromInputs(deadlineDate, deadlineTime).toISOString() : null,
          grade_to_journal: toJournal && !!lessonId,
          grade_type_id: toJournal && lessonId ? gradeTypeId || null : null,
        }),
      );
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const tab = (active: boolean) =>
    `flex-1 rounded-lg px-3 py-1.5 text-sm font-medium ${active ? "bg-surface shadow-sm" : "text-fg-soft hover:text-fg"}`;

  return (
    <form className="space-y-4" onSubmit={submit}>
      {error && <Alert>{error}</Alert>}
      <div className="flex rounded-xl border border-line bg-muted p-1" role="radiogroup" aria-label="Как выдать">
        <button type="button" role="radio" aria-checked={kind === "homework"} className={tab(kind === "homework")} onClick={() => setKind("homework")}>
          Домашнее задание
        </button>
        <button type="button" role="radio" aria-checked={kind === "live"} className={tab(kind === "live")} onClick={() => setKind("live")}>
          Тест на уроке
        </button>
      </div>
      <p className="text-sm text-fg-soft">
        {kind === "homework"
          ? "Ученики проходят сами до дедлайна. Сдать можно один раз — повторно, только если вы переназначите."
          : "Ученики проходят прямо сейчас, вы видите прогресс каждого. Когда закончите — завершите тест, незавершённые работы сдадутся."}
      </p>

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

      {kind === "homework" && (
        <div className="grid grid-cols-2 gap-3">
          <Field label="Дедлайн (необязательно)" type="date" value={deadlineDate} onChange={(e) => setDeadlineDate(e.target.value)} />
          <Field label="Время" type="time" value={deadlineTime} disabled={!deadlineDate} onChange={(e) => setDeadlineTime(e.target.value)} />
        </div>
      )}

      <Select label="Урок (необязательно)" value={lessonId} disabled={!targetId} onChange={(e) => setLessonId(e.target.value)}>
        <option value="">{targetId ? (targetLessons.length ? "Без привязки к уроку" : "Уроков рядом нет") : "Сначала выберите, кому"}</option>
        {targetLessons.map((l) => (
          <option key={l.id} value={l.id}>
            {fmtDateTime(l.starts_at)}
            {l.topic ? ` · ${l.topic}` : l.subject ? ` · ${l.subject}` : ""}
          </option>
        ))}
      </Select>

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
      {toJournal && lessonId && (
        <Select label="Тип оценки" value={gradeTypeId} required onChange={(e) => setGradeTypeId(e.target.value)}>
          <option value="">Выберите</option>
          {gradeTypes.data?.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </Select>
      )}

      <Button type="submit" loading={busy} disabled={!targetId} className="w-full">
        {kind === "live" ? "Запустить тест" : "Выдать"}
      </Button>
    </form>
  );
}
