"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { CodeEditor } from "@/components/code-editor";
import { ExamBoardView } from "@/components/exams";
import { AttachmentView } from "@/components/files";
import { resultText } from "@/components/task-solver";
import { Alert, Badge, Button, EmptyState, Field, Spinner } from "@/components/ui";
import { assessment, classroom, type Submission } from "@/lib/api";
import { fmtDateTime } from "@/lib/dates";
import { FAILURE_LABELS, TASK_TYPE_LABELS } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

/** Ученик глазами педагога: подготовка к ЕГЭ/ОГЭ и история решений. */
export default function StudentPage() {
  const { id } = useParams<{ id: string }>();
  const students = useLoad(() => classroom.students(), []);
  const name = students.data?.find((s) => s.student_id === id)?.full_name;
  const [tab, setTab] = useState<"exams" | "history">("exams");

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <Link href="/dashboard/groups" className="text-sm text-fg-soft hover:text-fg">
        ← Ученики
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">{name ?? "Ученик"}</h1>
      <div className="flex rounded-xl border border-line bg-muted p-1 text-sm sm:w-fit" role="tablist">
        {(
          [
            ["exams", "ЕГЭ и ОГЭ"],
            ["history", "Решения"],
          ] as const
        ).map(([key, title]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`flex-1 rounded-lg px-4 py-1.5 font-medium whitespace-nowrap ${tab === key ? "bg-surface shadow-sm" : "text-fg-soft hover:text-fg"}`}
          >
            {title}
          </button>
        ))}
      </div>
      {tab === "exams" ? <ExamBoardView targetType="student" targetId={id} /> : <History studentId={id} />}
    </div>
  );
}

/** История решений: код каждой попытки, протокол тестов, проверка развёрнутых ответов. */
function History({ studentId: id }: { studentId: string }) {
  const history = useLoad(() => assessment.history(id), [id]);

  // Группируем попытки по задачам, задачи — по последней попытке.
  const groups = new Map<string, Submission[]>();
  for (const s of history.data ?? []) groups.set(s.task_id, [...(groups.get(s.task_id) ?? []), s]);

  return (
    <div className="space-y-5">
      {history.error && <Alert>{history.error}</Alert>}
      {!history.data ? (
        !history.error && <Spinner />
      ) : groups.size === 0 ? (
        <EmptyState title="Ученик ещё не решал задачи" text="Здесь появятся его попытки — с кодом и результатами проверки." />
      ) : (
        [...groups.values()].map((subs) => <TaskHistory key={subs[0].task_id} subs={subs} onChanged={history.reload} />)
      )}
    </div>
  );
}

function TaskHistory({ subs, onChanged }: { subs: Submission[]; onChanged: () => void }) {
  const first = subs[0];
  const solved = subs.some((s) => s.status === "correct");
  return (
    <section className="rounded-2xl border border-line bg-surface">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-5 py-3">
        <Link href={`/dashboard/tasks/${first.task_id}`} className="min-w-0 flex-1 font-medium hover:underline">
          {first.task_title ?? "Задача"}
        </Link>
        {first.task_type && <Badge>{TASK_TYPE_LABELS[first.task_type]}</Badge>}
        {solved && <Badge tone="ok">решено</Badge>}
        <span className="text-sm text-fg-soft">попыток: {subs.length}</span>
      </header>
      <ol className="divide-y divide-line">
        {subs.map((s, i) => (
          <Attempt key={s.id} sub={s} number={subs.length - i} onChanged={onChanged} />
        ))}
      </ol>
    </section>
  );
}

function Attempt({ sub, number, onChanged }: { sub: Submission; number: number; onChanged: () => void }) {
  const r = resultText(sub);
  return (
    <li className="space-y-2 px-5 py-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">Попытка {number}</span>
        <Badge tone={r.tone}>{r.text}</Badge>
        <span className="ml-auto text-xs text-fg-soft">{fmtDateTime(sub.created_at)}</span>
      </div>
      {sub.answer.text && <p className="whitespace-pre-wrap text-sm">{sub.answer.text}</p>}
      {sub.files.map((f) => (
        <AttachmentView key={f.id} att={f} />
      ))}
      {sub.answer.code && (
        <details open={number === 1 || sub.status === "correct"}>
          <summary className="cursor-pointer text-sm text-brand">Код</summary>
          <div className="mt-1.5">
            <CodeEditor value={sub.answer.code} readOnly minHeight="60px" />
          </div>
        </details>
      )}
      {sub.run_log && sub.run_log.length > 0 && (
        <details>
          <summary className="cursor-pointer text-sm text-brand">Протокол тестов</summary>
          <table className="mt-1.5 w-full text-sm">
            <tbody>
              {sub.run_log.map((c) => (
                <tr key={c.number} className="border-t border-line align-top">
                  <td className="py-1 pr-3">№{c.number}</td>
                  <td className={`py-1 pr-3 ${c.status === "passed" ? "text-ok" : "text-danger"}`}>
                    {c.status === "passed" ? "пройден" : (FAILURE_LABELS[c.status as keyof typeof FAILURE_LABELS] ?? c.status)}
                  </td>
                  <td className="py-1 pr-3 text-fg-soft">{c.time_ms} мс</td>
                  <td className="py-1 font-mono text-xs whitespace-pre-wrap">{c.error || c.output}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
      {sub.teacher_comment && <p className="text-sm">Ваш комментарий: {sub.teacher_comment}</p>}
      {(sub.status === "pending_review" || sub.status === "reviewed") && <ReviewForm sub={sub} onChanged={onChanged} />}
    </li>
  );
}

function ReviewForm({ sub, onChanged }: { sub: Submission; onChanged: () => void }) {
  const [open, setOpen] = useState(sub.status === "pending_review");
  const [score, setScore] = useState(Math.round((sub.score ?? 1) * 100));
  const [comment, setComment] = useState(sub.teacher_comment ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="text-sm text-brand hover:underline">
        Изменить оценку
      </button>
    );
  }
  return (
    <form
      className="space-y-2 rounded-xl bg-muted p-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(undefined);
        try {
          await assessment.review(sub.id, score / 100, comment);
          setOpen(false);
          onChanged();
        } catch (err) {
          setError(errorText(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      {error && <Alert>{error}</Alert>}
      <div className="grid gap-2 sm:grid-cols-[8rem_1fr]">
        <Field label="Результат, %" type="number" min={0} max={100} value={score} onChange={(e) => setScore(Number(e.target.value))} />
        <Field label="Комментарий ученику" value={comment} maxLength={2000} onChange={(e) => setComment(e.target.value)} />
      </div>
      <Button type="submit" loading={busy}>
        Сохранить проверку
      </Button>
    </form>
  );
}
