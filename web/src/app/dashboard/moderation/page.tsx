"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Button, EmptyState, Modal, Spinner } from "@/components/ui";
import { moderation, type QueueItem } from "@/lib/api";
import { fmtDateTime } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

const LINKS: Record<string, (id: string) => string> = {
  course: (id) => `/dashboard/library/course/${id}`,
  task: (id) => `/dashboard/tasks/${id}`,
  plan_template: (id) => `/dashboard/planning/templates/${id}`,
  education_doc: (id) => `/dashboard/moderation/education/${id}`,
};

// Подписи кнопок: для спора «одобрить» — значит согласиться с педагогом и удалить отзыв.
const ACTIONS: Record<string, { approve: string; reject: string; rejectTitle: string; rejectLabel: string }> = {
  review: { approve: "Опубликовать", reject: "Не публиковать", rejectTitle: "Не публиковать отзыв", rejectLabel: "Причина (увидит автор)" },
  review_reply: { approve: "Опубликовать ответ", reject: "Не публиковать", rejectTitle: "Не публиковать ответ", rejectLabel: "Причина (увидит педагог)" },
  review_dispute: { approve: "Удалить отзыв", reject: "Оставить отзыв", rejectTitle: "Оставить отзыв опубликованным", rejectLabel: "Почему отзыв остаётся (увидит педагог)" },
};
const DEFAULT_ACTIONS = { approve: "Одобрить", reject: "Вернуть на доработку", rejectTitle: "Вернуть на доработку", rejectLabel: "Что нужно исправить (увидит автор)" };

const str = (v: unknown) => (typeof v === "string" ? v : null);

/** Что показать модератору прямо в карточке: текст отзыва, ответа, причину спора. */
function ReviewDetails({ item }: { item: QueueItem }) {
  const d = item.details;
  const quote = (label: string, text: string | null) =>
    text && (
      <div className="text-sm">
        <p className="text-fg-soft">{label}</p>
        <p className="whitespace-pre-line">{text}</p>
      </div>
    );
  return (
    <div className="mt-3 space-y-2 rounded-xl bg-muted p-3">
      {item.kind === "review" && quote(`Отзыв ученика (${d.rating}/10)`, str(d.text))}
      {item.kind === "review_reply" && (
        <>
          {quote(`Отзыв ученика ${str(d.student_name) ?? ""} (${d.rating}/10)`, str(d.review_text))}
          {quote("Ответ педагога", str(d.text))}
        </>
      )}
      {item.kind === "review_dispute" && (
        <>
          {quote(`Отзыв ученика ${str(d.student_name) ?? ""} (${d.rating}/10)`, str(d.review_text))}
          {quote("Почему педагог просит удалить", str(d.reason))}
          {str(d.dispute_id) && (
            <Link href={`/dashboard/chats?c=${d.dispute_id}`} className="inline-block text-sm font-medium text-brand hover:underline">
              Чат с педагогом →
            </Link>
          )}
        </>
      )}
      {str(d.tutor_id) && (
        <Link href={`/tutors/${d.tutor_id}#reviews`} target="_blank" className="block text-sm text-brand hover:underline">
          Профиль педагога {str(d.tutor_name) ?? ""} ↗
        </Link>
      )}
    </div>
  );
}

export default function ModerationPage() {
  const [status, setStatus] = useState<"pending" | "approved" | "rejected">("pending");
  const queue = useLoad(() => moderation.queue(status), [status]);
  const [rejecting, setRejecting] = useState<QueueItem | null>(null);
  const [error, setError] = useState<string>();

  async function approve(item: QueueItem) {
    setError(undefined);
    try {
      await moderation.decide(item.id, "approve");
      queue.reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Очередь модерации</h1>
        <p className="mt-1 text-fg-soft">Заявки проверяются по порядку поступления.</p>
      </div>
      <div className="flex rounded-xl border border-line bg-muted p-1 text-sm" role="tablist">
        {(
          [
            ["pending", "Ожидают"],
            ["approved", "Одобрены"],
            ["rejected", "Отклонены"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            role="tab"
            aria-selected={status === value}
            onClick={() => setStatus(value)}
            className={`flex-1 rounded-lg px-3 py-1.5 font-medium ${status === value ? "bg-surface shadow-sm" : "text-fg-soft hover:text-fg"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {(error || queue.error) && <Alert>{error ?? queue.error}</Alert>}
      {!queue.data ? (
        <Spinner />
      ) : queue.data.length === 0 ? (
        <EmptyState title={status === "pending" ? "Очередь пуста" : "Здесь пока ничего нет"} />
      ) : (
        <ul className="space-y-3">
          {queue.data.map((item) => (
            <li key={item.id} className="rounded-2xl border border-line bg-surface p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <Badge>{item.kind_label}</Badge>
                  <h2 className="mt-1.5 text-lg font-semibold">{item.title}</h2>
                  <p className="text-sm text-fg-soft">
                    {item.author_name} · {fmtDateTime(item.created_at)}
                  </p>
                  {item.comment && <p className="mt-2 text-sm">Комментарий: {item.comment}</p>}
                  {item.kind in ACTIONS && <ReviewDetails item={item} />}
                </div>
                {LINKS[item.kind] && (
                  <Link href={LINKS[item.kind](item.ref_id)} target="_blank" className="text-sm font-medium text-brand hover:underline">
                    Открыть ↗
                  </Link>
                )}
              </div>
              {item.status === "pending" && (
                <div className="mt-4 flex gap-2">
                  <Button onClick={() => approve(item)}>{(ACTIONS[item.kind] ?? DEFAULT_ACTIONS).approve}</Button>
                  <Button variant="secondary" onClick={() => setRejecting(item)}>
                    {(ACTIONS[item.kind] ?? DEFAULT_ACTIONS).reject}
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <RejectModal
        item={rejecting}
        onClose={() => setRejecting(null)}
        onDone={() => {
          setRejecting(null);
          queue.reload();
        }}
      />
    </div>
  );
}

function RejectModal({ item, onClose, onDone }: { item: QueueItem | null; onClose: () => void; onDone: () => void }) {
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  return (
    <Modal open={!!item} onClose={onClose} title={(item && ACTIONS[item.kind]?.rejectTitle) ?? DEFAULT_ACTIONS.rejectTitle}>
      {item && (
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(undefined);
            try {
              await moderation.decide(item.id, "reject", comment);
              setComment("");
              onDone();
            } catch (err) {
              setError(errorText(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          {error && <Alert>{error}</Alert>}
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium">{(ACTIONS[item.kind] ?? DEFAULT_ACTIONS).rejectLabel}</span>
            <textarea
              rows={4}
              required
              maxLength={2000}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
            />
          </label>
          <Button type="submit" loading={busy} disabled={!comment.trim()} className="w-full">
            {(ACTIONS[item.kind] ?? DEFAULT_ACTIONS).reject}
          </Button>
        </form>
      )}
    </Modal>
  );
}
