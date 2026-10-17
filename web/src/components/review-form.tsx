"use client";

import { useState } from "react";

import { Alert, Button, Field } from "@/components/ui";
import { assessment, type Submission } from "@/lib/api";
import { errorText } from "@/lib/hooks";

/** Проверка развёрнутого ответа педагогом: результат и комментарий ученику.
 *  points — сколько баллов стоит задание в работе: тогда результат вводится в баллах, иначе — в процентах. */
export function ReviewForm({
  sub,
  onChanged,
  points,
  openLabel = "Изменить оценку",
}: {
  sub: Submission;
  onChanged: () => void;
  points?: number;
  /** Подпись кнопки, пока форма свёрнута (у кода — «Проверить вручную»: по умолчанию проверка автоматическая). */
  openLabel?: string;
}) {
  const [open, setOpen] = useState(sub.status === "pending_review");
  const max = points ?? 100;
  const [score, setScore] = useState(Math.round((sub.score ?? 1) * max * 2) / 2);
  const [comment, setComment] = useState(sub.teacher_comment ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="text-sm text-brand hover:underline">
        {sub.reviewed_at ? "Изменить оценку" : openLabel}
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
          await assessment.review(sub.id, Math.min(1, Math.max(0, score / max)), comment);
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
        <Field
          label={points ? `Баллы (из ${points})` : "Результат, %"}
          type="number"
          min={0}
          max={max}
          step={points ? 0.5 : 1}
          value={score}
          onChange={(e) => setScore(Number(e.target.value))}
        />
        <Field label="Комментарий ученику" value={comment} maxLength={2000} onChange={(e) => setComment(e.target.value)} />
      </div>
      <Button type="submit" loading={busy}>
        Сохранить проверку
      </Button>
    </form>
  );
}
