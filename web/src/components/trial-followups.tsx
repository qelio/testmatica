"use client";

import { useState } from "react";

import { ReviewForm } from "@/components/reviews";
import { Alert, Button, Modal } from "@/components/ui";
import { marketplace, type TrialFollowup } from "@/lib/api";
import { fmtDateTime } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

const TEXTAREA =
  "w-full rounded-xl border border-line bg-surface px-3.5 py-2 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

/** После пробного: оставить отзыв и ответить, продолжать ли занятия (ТЗ, раздел 4). Видно ученику на дашборде. */
export function TrialFollowups() {
  const list = useLoad(() => marketplace.pendingTrials(), []);
  if (!list.data?.length) return null;
  return (
    <section className="space-y-3">
      {list.data.map((t) => (
        <TrialCard key={t.lesson_id} trial={t} onDone={list.reload} />
      ))}
    </section>
  );
}

function TrialCard({ trial, onDone }: { trial: TrialFollowup; onDone: () => void }) {
  const [comment, setComment] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const [reviewed, setReviewed] = useState(trial.reviewed);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function answer(decision: "continue" | "stop") {
    setBusy(true);
    setError(undefined);
    try {
      await marketplace.answerTrial(trial.lesson_id, decision, comment);
      onDone();
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-2xl border border-brand/40 bg-brand/5 p-5">
      <div>
        <h2 className="font-semibold">Как прошло пробное занятие с {trial.tutor.full_name}?</h2>
        <p className="text-sm text-fg-soft">
          {trial.title} · {fmtDateTime(trial.lesson_starts_at)}
        </p>
      </div>
      {error && <Alert>{error}</Alert>}
      <textarea
        rows={2}
        maxLength={1000}
        className={TEXTAREA}
        value={comment}
        placeholder="Комментарий для педагога (необязательно): что понравилось, удобное время…"
        onChange={(e) => setComment(e.target.value)}
      />
      <div className="flex flex-wrap gap-2">
        <Button loading={busy} onClick={() => answer("continue")}>
          Продолжу заниматься
        </Button>
        <Button variant="secondary" disabled={busy} onClick={() => answer("stop")}>
          Не буду продолжать
        </Button>
        {!reviewed ? (
          <Button variant="ghost" onClick={() => setReviewing(true)}>
            Оставить отзыв
          </Button>
        ) : (
          <span className="self-center text-sm text-fg-soft">Отзыв отправлен ✓</span>
        )}
      </div>
      <Modal open={reviewing} onClose={() => setReviewing(false)} title={`Отзыв: ${trial.tutor.full_name}`}>
        {reviewing && (
          <ReviewForm
            tutorId={trial.tutor.id}
            mine={null}
            onSaved={() => {
              setReviewing(false);
              setReviewed(true);
            }}
          />
        )}
      </Modal>
    </div>
  );
}
