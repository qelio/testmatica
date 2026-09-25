"use client";

import { useState } from "react";

import { Alert, Button, Field } from "@/components/ui";
import { assessment, type Submission } from "@/lib/api";
import { errorText } from "@/lib/hooks";

/** Проверка развёрнутого ответа педагогом: процент выполнения и комментарий ученику. */
export function ReviewForm({ sub, onChanged }: { sub: Submission; onChanged: () => void }) {
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
