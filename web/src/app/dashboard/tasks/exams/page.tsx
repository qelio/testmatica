"use client";

import Link from "next/link";
import { useState } from "react";

import { EXAM_KIND_LABELS } from "@/components/exams";
import { Alert, Button, Field, Modal, Select, Spinner } from "@/components/ui";
import { assessment, content, type Exam, type ExamItem, type ExamKind } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorText, useLoad } from "@/lib/hooks";

const INPUT =
  "h-9 min-w-0 rounded-lg border border-line bg-surface px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

/** Каталог заданий ЕГЭ/ОГЭ — ведут модераторы (формат экзаменов меняется каждый год). */
export default function ExamCatalogPage() {
  const { user } = useAuth();
  const staff = !!user?.roles.some((r) => r === "moderator" || r === "admin");
  const exams = useLoad(() => assessment.exams(), []);
  const [examId, setExamId] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string>();

  if (!staff) return <Alert>Каталог ЕГЭ и ОГЭ ведут модераторы.</Alert>;
  if (!exams.data) return <Spinner />;
  const exam = exams.data.find((e) => e.id === examId) ?? exams.data[0];

  async function act(action: () => Promise<unknown>) {
    setError(undefined);
    try {
      await action();
      exams.reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <Link href="/dashboard/tasks" className="text-sm text-fg-soft hover:text-fg">
        ← Банк задач
      </Link>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Задания ЕГЭ и ОГЭ</h1>
          <p className="mt-1 text-sm text-fg-soft">Номера и названия заданий по демоверсиям ФИПИ. К ним авторы относят задачи.</p>
        </div>
        <Button variant="secondary" onClick={() => setCreating(true)}>
          Новый экзамен
        </Button>
      </div>
      {error && <Alert>{error}</Alert>}
      {exam && (
        <>
          <Select label="Экзамен" value={exam.id} onChange={(e) => setExamId(e.target.value)}>
            {exams.data.map((e) => (
              <option key={e.id} value={e.id}>
                {e.title}
              </option>
            ))}
          </Select>
          <ol className="divide-y divide-line rounded-2xl border border-line bg-surface">
            {exam.items.map((i) => (
              <ItemRow
                key={i.id}
                item={i}
                onSave={(data) => act(() => assessment.updateExamItem(i.id, data))}
                onDelete={() => act(() => assessment.deleteExamItem(i.id))}
              />
            ))}
            <li className="px-4 py-3">
              <AddItem exam={exam} onAdd={(data) => act(() => assessment.addExamItem(exam.id, data))} />
            </li>
          </ol>
          <Button
            variant="ghost"
            className="text-danger"
            onClick={() => window.confirm(`Удалить «${exam.title}»?`) && act(() => assessment.deleteExam(exam.id))}
          >
            Удалить экзамен
          </Button>
        </>
      )}
      <NewExamModal
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(e) => {
          setCreating(false);
          setExamId(e.id);
          exams.reload();
        }}
      />
    </div>
  );
}

function ItemRow({
  item,
  onSave,
  onDelete,
}: {
  item: ExamItem;
  onSave: (data: { number: number; title: string }) => Promise<void>;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [number, setNumber] = useState(item.number);
  const [title, setTitle] = useState(item.title);
  if (editing) {
    return (
      <li className="px-4 py-2.5">
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            await onSave({ number, title: title.trim() });
            setEditing(false);
          }}
        >
          <input type="number" min={1} max={99} value={number} onChange={(e) => setNumber(Number(e.target.value))} className={`${INPUT} w-20`} aria-label="Номер" />
          <input autoFocus value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} className={`${INPUT} flex-1`} aria-label="Название" />
          <Button type="submit" className="h-9" disabled={!title.trim()}>
            Сохранить
          </Button>
          <Button type="button" variant="ghost" className="h-9" onClick={() => setEditing(false)}>
            Отмена
          </Button>
        </form>
      </li>
    );
  }
  return (
    <li className="flex items-center gap-3 px-4 py-2.5">
      <span className="w-8 text-right font-semibold text-fg-soft tabular-nums">{item.number}</span>
      <span className="min-w-0 flex-1">{item.title}</span>
      <button className="text-sm text-fg-soft hover:text-fg" onClick={() => setEditing(true)}>
        Изменить
      </button>
      <button className="px-1 text-sm text-fg-soft hover:text-danger" onClick={onDelete} aria-label={`Удалить задание №${item.number}`}>
        ✕
      </button>
    </li>
  );
}

function AddItem({ exam, onAdd }: { exam: Exam; onAdd: (data: { number: number; title: string }) => Promise<void> }) {
  const next = Math.max(0, ...exam.items.map((i) => i.number)) + 1;
  const [title, setTitle] = useState("");
  return (
    <form
      className="flex items-center gap-2"
      onSubmit={async (e) => {
        e.preventDefault();
        await onAdd({ number: next, title: title.trim() });
        setTitle("");
      }}
    >
      <span className="w-8 text-right font-semibold text-fg-soft tabular-nums">{next}</span>
      <input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder="Новое задание" aria-label="Новое задание" className={`${INPUT} flex-1`} />
      <Button type="submit" variant="secondary" className="h-9" disabled={!title.trim()}>
        Добавить
      </Button>
    </form>
  );
}

function NewExamModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (e: Exam) => void }) {
  const subjects = useLoad(() => content.subjects(), []);
  const [kind, setKind] = useState<ExamKind>("ege");
  const [subjectId, setSubjectId] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string>();
  const subject = subjects.data?.find((s) => s.id === subjectId);
  return (
    <Modal open={open} onClose={onClose} title="Новый экзамен">
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!subject) return;
          setError(undefined);
          try {
            onCreated(
              await assessment.createExam({
                kind,
                subject_id: subject.id,
                subject_name: subject.name,
                title: title.trim() || `${EXAM_KIND_LABELS[kind]} · ${subject.name}`,
              }),
            );
          } catch (err) {
            setError(errorText(err));
          }
        }}
      >
        {error && <Alert>{error}</Alert>}
        <div className="grid grid-cols-2 gap-3">
          <Select label="Экзамен" value={kind} onChange={(e) => setKind(e.target.value as ExamKind)}>
            <option value="ege">ЕГЭ</option>
            <option value="oge">ОГЭ</option>
          </Select>
          <Select label="Предмет" value={subjectId} onChange={(e) => setSubjectId(e.target.value)} required>
            <option value="">Выберите</option>
            {subjects.data?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
        </div>
        <Field
          label="Название"
          placeholder={subject ? `${EXAM_KIND_LABELS[kind]} · ${subject.name}` : "Например, ЕГЭ · Математика (база)"}
          value={title}
          maxLength={120}
          onChange={(e) => setTitle(e.target.value)}
        />
        <Button type="submit" className="w-full" disabled={!subject}>
          Создать
        </Button>
      </form>
    </Modal>
  );
}
