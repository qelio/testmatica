"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Select, Spinner } from "@/components/ui";
import { assessment, type Exam, type ExamBoardRow, type ExamLabel, type ExamProgress, type ExamStage } from "@/lib/api";
import { fmtDateTime } from "@/lib/dates";
import { TASK_TYPE_LABELS } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

export const EXAM_KIND_LABELS = { ege: "ЕГЭ", oge: "ОГЭ" } as const;

/** id задания → подпись «ЕГЭ №8» и название. */
export function examIndex(exams: Exam[]): Map<string, ExamLabel & { exam: Exam }> {
  const map = new Map<string, ExamLabel & { exam: Exam }>();
  for (const e of exams)
    for (const i of e.items) map.set(i.id, { id: i.id, label: `${EXAM_KIND_LABELS[e.kind]} №${i.number}`, title: i.title, exam: e });
  return map;
}

/** Чипы заданий экзамена у задачи или занятия. */
export function ExamChips({ labels }: { labels: ExamLabel[] }) {
  if (!labels.length) return null;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {labels.map((l) => (
        <span key={l.id} title={l.title} className="rounded-md bg-tutor/10 px-1.5 py-0.5 text-xs font-medium text-tutor">
          {l.label}
        </span>
      ))}
    </span>
  );
}

/** Выпадающий список заданий: экзамены — группами. Для фильтров и выбора. */
export function ExamItemSelect({
  exams,
  value,
  onChange,
  label,
  empty,
  exclude = [],
}: {
  exams: Exam[];
  value: string;
  onChange: (id: string) => void;
  label: string;
  empty: string;
  exclude?: string[];
}) {
  return (
    <Select label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{empty}</option>
      {exams.map((e) => (
        <optgroup key={e.id} label={e.title}>
          {e.items
            .filter((i) => !exclude.includes(i.id))
            .map((i) => (
              <option key={i.id} value={i.id}>
                №{i.number}. {i.title}
              </option>
            ))}
        </optgroup>
      ))}
    </Select>
  );
}

/** Привязка к заданиям ЕГЭ/ОГЭ: выбранные — чипами с удалением, новое — из списка. */
export function ExamItemsPicker({ exams, value, onChange }: { exams: Exam[]; value: string[]; onChange: (ids: string[]) => void }) {
  const index = examIndex(exams);
  return (
    <div className="space-y-2">
      {value.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {value.map((id) => {
            const l = index.get(id);
            return (
              <li key={id} className="inline-flex items-center gap-1.5 rounded-lg border border-tutor/30 bg-tutor/10 py-1 pr-1 pl-2 text-sm">
                <span className="font-medium text-tutor">{l?.label ?? "Задание"}</span>
                <span className="max-w-56 truncate text-fg-soft">{l?.title}</span>
                <button
                  type="button"
                  onClick={() => onChange(value.filter((x) => x !== id))}
                  className="px-1 text-fg-soft hover:text-danger"
                  aria-label={`Убрать ${l?.label ?? "задание"}`}
                >
                  ✕
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {value.length < 10 && (
        <ExamItemSelect
          exams={exams}
          value=""
          exclude={value}
          onChange={(id) => id && onChange([...value, id])}
          label="Задания ЕГЭ/ОГЭ"
          empty={value.length ? "+ добавить ещё задание" : "Не относится — или выберите задание"}
        />
      )}
    </div>
  );
}

function rate(p: ExamProgress): number | null {
  return p.attempted ? p.solved / p.attempted : null;
}

function ProgressBar({ p }: { p: ExamProgress }) {
  const r = rate(p);
  if (r === null) return <span className="text-sm text-fg-soft">не решал</span>;
  const tone = r >= 0.8 ? "bg-ok" : r >= 0.5 ? "bg-tutor" : "bg-danger";
  return (
    <div className="min-w-0">
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted" aria-hidden>
        <div className={`h-full ${tone}`} style={{ width: `${Math.max(4, r * 100)}%` }} />
      </div>
      <p className="mt-1 text-xs text-fg-soft">
        решено {p.solved} из {p.attempted} · попыток {p.attempts} · {Math.round(r * 100)}%
      </p>
    </div>
  );
}

const STAGES: { key: ExamStage; label: string; hint: string; on: string }[] = [
  { key: "theory", label: "Материал", hint: "Выдали теорию: рассказали, как решать", on: "border-brand/40 bg-brand/10 text-brand-text" },
  { key: "practice", label: "Практика", hint: "Решали самостоятельно, не на оценку", on: "border-tutor/40 bg-tutor/10 text-tutor" },
  { key: "control", label: "Контроль", hint: "Проверили знания", on: "border-ok/40 bg-ok/10 text-ok" },
];

const STORE_KEY = "exam-board";

function rememberedExam(key: string, exams: Exam[]): string {
  try {
    const id = localStorage.getItem(`${STORE_KEY}:${key}`);
    if (id && exams.some((e) => e.id === id)) return id;
  } catch {}
  return exams[0]?.id ?? "";
}

/**
 * Таблица заданий ЕГЭ/ОГЭ для ученика или группы: прогресс по решённым задачам и отметки педагога.
 * Ученик видит свою таблицу без примечаний и не может ставить отметки.
 */
export function ExamBoardView({ targetType, targetId }: { targetType: "student" | "group"; targetId: string }) {
  const exams = useLoad(() => assessment.exams(), []);
  if (exams.error) return <Alert>{exams.error}</Alert>;
  if (!exams.data) return <Spinner />;
  if (!exams.data.length) return <p className="text-sm text-fg-soft">Каталог заданий ЕГЭ/ОГЭ пока пуст.</p>;
  return <Board exams={exams.data} targetType={targetType} targetId={targetId} />;
}

function Board({ exams, targetType, targetId }: { exams: Exam[]; targetType: "student" | "group"; targetId: string }) {
  const key = `${targetType}:${targetId}`;
  const [examId, setExamId] = useState(() => rememberedExam(key, exams));
  const board = useLoad(() => assessment.examBoard(examId, targetType, targetId), [examId, targetType, targetId]);

  const rows = board.data?.rows ?? [];
  const done = rows.filter((r) => r.done).length;
  const staged = STAGES.map((st) => ({ ...st, count: rows.filter((r) => r[st.key]).length }));
  const total = rows.reduce(
    (acc, r) => ({ solved: acc.solved + r.progress.solved, attempted: acc.attempted + r.progress.attempted }),
    { solved: 0, attempted: 0 },
  );

  return (
    <div className="space-y-4">
      <div className="grid items-end gap-3 sm:grid-cols-[minmax(0,20rem)_1fr]">
        <Select
          label="Экзамен"
          value={examId}
          onChange={(e) => {
            setExamId(e.target.value);
            try {
              localStorage.setItem(`${STORE_KEY}:${key}`, e.target.value);
            } catch {}
          }}
        >
          {exams.map((e) => (
            <option key={e.id} value={e.id}>
              {e.title}
            </option>
          ))}
        </Select>
        {board.data && (
          <p className="text-sm text-fg-soft">
            Пройдено заданий: <b className="text-fg">{done}</b> из {rows.length} · решено задач:{" "}
            <b className="text-fg">{total.solved}</b> из {total.attempted}
            {total.attempted > 0 && ` (${Math.round((total.solved / total.attempted) * 100)}%)`}
            <br />
            {staged.map((st, i) => (
              <span key={st.key} title={st.hint}>
                {i > 0 && " · "}
                {st.label.toLowerCase()}: <b className="text-fg">{st.count}</b>
              </span>
            ))}
          </p>
        )}
      </div>
      {board.error && <Alert>{board.error}</Alert>}
      {!board.data ? (
        !board.error && <Spinner />
      ) : (
        <ol className="divide-y divide-line rounded-2xl border border-line bg-surface">
          {board.data.rows.map((r) => (
            <BoardRowView
              key={r.item_id}
              row={r}
              canEdit={board.data!.can_edit}
              targetType={targetType}
              targetId={targetId}
              students={board.data!.students}
            />
          ))}
        </ol>
      )}
      {board.data?.can_edit && (
        <p className="text-xs text-fg-soft">
          Этапы: «материал» — рассказали теорию, как решать; «практика» — решали сами, не на оценку; «контроль» — проверили знания.
          Прогресс считается по всем решениям ученика: задачи из курсов, домашних заданий и тестов, отнесённые к заданию экзамена.
          Примечания видны только вам; ученик видит отметки без примечаний.
        </p>
      )}
    </div>
  );
}

function BoardRowView({
  row,
  canEdit,
  targetType,
  targetId,
  students,
}: {
  row: ExamBoardRow;
  canEdit: boolean;
  targetType: "student" | "group";
  targetId: string;
  students: { id: string; full_name: string }[];
}) {
  const [marks, setMarks] = useState({ theory: row.theory, practice: row.practice, control: row.control, done: row.done });
  const [note, setNote] = useState(row.note ?? "");
  const [saved, setSaved] = useState(row.note ?? "");
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string>();
  const done = marks.done;

  // Отправляем только изменённое поле — соседние галочки не затираются.
  async function save(patch: Partial<typeof marks> & { note?: string }) {
    setError(undefined);
    const before = marks;
    const { note: nextNote, ...flags } = patch;
    setMarks((m) => ({ ...m, ...flags }));
    try {
      await assessment.setExamMark({ target_type: targetType, target_id: targetId, item_id: row.item_id, ...patch });
      if (nextNote !== undefined) setSaved(nextNote);
    } catch (e) {
      setError(errorText(e));
      setMarks(before);
    }
  }

  return (
    <li className={`px-4 py-3 ${done ? "bg-ok/5" : ""}`}>
      <div className="grid items-center gap-x-4 gap-y-2 sm:grid-cols-[2.5rem_minmax(0,1fr)_12rem] xl:grid-cols-[2.5rem_minmax(0,1fr)_12rem_auto]">
        <span className="text-lg font-semibold text-fg-soft tabular-nums">{row.number}</span>
        <button onClick={() => setOpen((o) => !o)} className="min-w-0 text-left" aria-expanded={open}>
          <span className="font-medium hover:underline">{row.title}</span>
          <span className="block text-xs text-fg-soft">
            {row.progress.last_at ? `последнее решение ${fmtDateTime(row.progress.last_at)}` : "решений пока нет"}
            {row.tasks_in_bank > 0 && ` · в банке задач: ${row.tasks_in_bank}`}
          </span>
        </button>
        <ProgressBar p={row.progress} />
        <div className="flex flex-wrap items-center gap-1.5 sm:col-start-2 sm:col-end-4 xl:col-auto">
          {STAGES.map((st) => (
            <label
              key={st.key}
              title={st.hint}
              className={`flex items-center gap-1.5 rounded-lg border px-2 py-1 text-sm select-none ${
                marks[st.key] ? st.on : "border-line text-fg-soft"
              } ${canEdit ? "cursor-pointer hover:border-fg-soft/50" : ""}`}
            >
              <input
                type="checkbox"
                checked={marks[st.key]}
                disabled={!canEdit}
                onChange={(e) => save({ [st.key]: e.target.checked })}
                className="h-4 w-4 accent-current"
              />
              {st.label}
            </label>
          ))}
          <label className={`ml-1 flex items-center gap-2 text-sm ${canEdit ? "cursor-pointer" : ""}`}>
            <input
              type="checkbox"
              checked={done}
              disabled={!canEdit}
              onChange={(e) => save({ done: e.target.checked })}
              className="h-5 w-5 accent-ok"
            />
            <span className={done ? "text-ok" : "text-fg-soft"}>пройдено</span>
          </label>
        </div>
      </div>
      {canEdit && (
        <input
          value={note}
          maxLength={2000}
          onChange={(e) => setNote(e.target.value)}
          onBlur={() => note !== saved && save({ note })}
          onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
          placeholder="Примечание: что повторить, на чём ошибается…"
          aria-label={`Примечание к заданию №${row.number}`}
          className="mt-2 h-9 w-full rounded-lg border border-transparent bg-muted/60 px-3 text-sm outline-none placeholder:text-fg-soft/70 focus:border-brand focus:bg-surface sm:ml-[3.5rem] sm:w-[calc(100%-3.5rem)]"
        />
      )}
      {error && (
        <div className="mt-2">
          <Alert>{error}</Alert>
        </div>
      )}
      {open &&
        (targetType === "student" ? (
          <ItemTasks studentId={targetId} itemId={row.item_id} />
        ) : (
          <ul className="mt-3 space-y-1.5 sm:ml-[3.5rem]">
            {students.map((s) => {
              const p = row.by_student.find((b) => b.student_id === s.id);
              return (
                <li key={s.id} className="grid grid-cols-[minmax(0,1fr)_12rem] items-center gap-3 text-sm">
                  <Link href={`/dashboard/students/${s.id}`} className="truncate hover:underline">
                    {s.full_name}
                  </Link>
                  {p ? <ProgressBar p={p} /> : <span className="text-fg-soft">—</span>}
                </li>
              );
            })}
          </ul>
        ))}
    </li>
  );
}

function ItemTasks({ studentId, itemId }: { studentId: string; itemId: string }) {
  const tasks = useLoad(() => assessment.examItemTasks(studentId, itemId), [studentId, itemId]);
  if (tasks.error) return <Alert>{tasks.error}</Alert>;
  if (!tasks.data) return <Spinner />;
  if (!tasks.data.length) return <p className="mt-2 text-sm text-fg-soft sm:ml-[3.5rem]">Задач по этому заданию ученик ещё не решал.</p>;
  return (
    <ul className="mt-3 space-y-1.5 text-sm sm:ml-[3.5rem]">
      {tasks.data.map((t) => (
        <li key={t.task_id} className="flex flex-wrap items-center gap-2">
          <Badge tone={t.solved ? "ok" : "warn"}>{t.solved ? "решена" : "не решена"}</Badge>
          <span className="min-w-0 flex-1 truncate">{t.title}</span>
          <span className="text-xs text-fg-soft">
            {TASK_TYPE_LABELS[t.type]} · попыток {t.attempts} · {fmtDateTime(t.last_at)}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Подписи заданий по их id (для занятий — расписание хранит только id). */
export function ExamItemsByIds({ ids }: { ids: string[] }) {
  const exams = useLoad(async () => (ids.length ? assessment.exams() : []), [ids.length]);
  if (!ids.length || !exams.data) return null;
  const index = examIndex(exams.data);
  const labels = ids.flatMap((id) => (index.has(id) ? [index.get(id)!] : []));
  return (
    <ul className="space-y-0.5">
      {labels.map((l) => (
        <li key={l.id}>
          <span className="font-medium text-tutor">{l.label}</span> {l.title}
        </li>
      ))}
    </ul>
  );
}

/** Выбор заданий ЕГЭ/ОГЭ в форме (сам загружает каталог). */
export function ExamItemsField({ value, onChange }: { value: string[]; onChange: (ids: string[]) => void }) {
  const exams = useLoad(() => assessment.exams(), []);
  if (!exams.data?.length) return null;
  return <ExamItemsPicker exams={exams.data} value={value} onChange={onChange} />;
}
