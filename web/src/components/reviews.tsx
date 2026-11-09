"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Button, Modal } from "@/components/ui";
import { marketplace, type MyReview, type ReviewPublic, type ReviewsPage, type TutorReview } from "@/lib/api";
import { fmtDate } from "@/lib/dates";
import { fmtRating, pluralReviews } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

const TEXTAREA =
  "w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

export const REVIEW_STATUS = {
  pending: { text: "на проверке", tone: "neutral" },
  approved: { text: "опубликован", tone: "ok" },
  rejected: { text: "не опубликован", tone: "warn" },
  removed: { text: "удалён модератором", tone: "warn" },
} as const;

/** Оценка 1–10 кнопками. */
function RatingPicker({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  return (
    <div className="flex flex-wrap gap-1" role="radiogroup" aria-label="Оценка от 1 до 10">
      {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          onClick={() => onChange(n)}
          className={`h-9 w-9 rounded-lg border text-sm font-medium tabular-nums ${
            value === n ? "border-brand bg-brand text-on-brand" : n <= value ? "border-brand/40 bg-brand/10 text-brand-text" : "border-line text-fg-soft hover:text-fg"
          }`}
        >
          {n}
        </button>
      ))}
    </div>
  );
}

/** Форма отзыва: создать или изменить свой. */
export function ReviewForm({ tutorId, mine, onSaved }: { tutorId: string; mine: MyReview | null; onSaved: (r: MyReview) => void }) {
  const [rating, setRating] = useState(mine?.rating ?? 0);
  const [text, setText] = useState(mine?.text ?? "");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(undefined);
        try {
          onSaved(await marketplace.saveReview(tutorId, { rating, text }));
        } catch (err) {
          setError(errorText(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      {error && <Alert>{error}</Alert>}
      <div>
        <p className="mb-1.5 text-sm font-medium">Оценка</p>
        <RatingPicker value={rating} onChange={setRating} />
      </div>
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium">Отзыв</span>
        <textarea
          rows={5}
          required
          minLength={10}
          maxLength={3000}
          className={TEXTAREA}
          value={text}
          placeholder="Как проходят занятия, что получилось, что можно улучшить"
          onChange={(e) => setText(e.target.value)}
        />
      </label>
      <p className="text-xs text-fg-soft">
        Отзыв опубликуется после проверки модератором. {mine?.status === "approved" && "Изменённый отзыв проверят заново, до этого он не будет виден."}
      </p>
      <Button type="submit" loading={busy} disabled={!rating || text.trim().length < 10} className="w-full">
        {mine ? "Сохранить отзыв" : "Отправить отзыв"}
      </Button>
    </form>
  );
}

/** Свой отзыв со статусом — для ученика. */
export function MyReviewCard({ review, onEdit, onDeleted }: { review: MyReview; onEdit: () => void; onDeleted: () => void }) {
  const st = REVIEW_STATUS[review.status];
  return (
    <div className="space-y-2 rounded-2xl border border-brand/30 bg-brand/5 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">Ваш отзыв · {review.rating}/10</span>
        <Badge tone={st.tone}>{st.text}</Badge>
        <span className="ml-auto flex gap-3 text-sm">
          {review.status !== "removed" && (
            <button className="text-brand-text hover:underline" onClick={onEdit}>
              Изменить
            </button>
          )}
          <button
            className="text-fg-soft hover:text-danger"
            onClick={async () => {
              if (!window.confirm("Удалить отзыв?")) return;
              await marketplace.deleteReview(review.id);
              onDeleted();
            }}
          >
            Удалить
          </button>
        </span>
      </div>
      <p className="text-sm whitespace-pre-line">{review.text}</p>
      {review.comment && review.status !== "approved" && <p className="text-sm text-tutor">Модератор: {review.comment}</p>}
    </div>
  );
}

export function ReviewItem({ review, children }: { review: ReviewPublic; children?: React.ReactNode }) {
  return (
    <li className="space-y-2 py-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="rounded-lg bg-brand/10 px-2 py-0.5 text-sm font-semibold text-brand-text tabular-nums">{review.rating}/10</span>
        <span className="font-medium">{review.student_name}</span>
        <span className="text-sm text-fg-soft">{fmtDate(review.published_at, { day: "numeric", month: "long", year: "numeric" })}</span>
      </div>
      <p className="whitespace-pre-line">{review.text}</p>
      {review.reply && (
        <div className="ml-4 border-l-2 border-line pl-3 text-sm">
          <p className="font-medium">Ответ педагога</p>
          <p className="whitespace-pre-line text-fg-soft">{review.reply}</p>
        </div>
      )}
      {children}
    </li>
  );
}

function Distribution({ page }: { page: ReviewsPage }) {
  const max = Math.max(1, ...Object.values(page.distribution));
  return (
    <div className="flex flex-wrap items-end gap-6">
      <div>
        <p className="text-4xl font-semibold tabular-nums">{page.rating !== null ? fmtRating(page.rating) : "—"}</p>
        <p className="text-sm text-fg-soft">из 10 · {pluralReviews(page.reviews_count)}</p>
      </div>
      <div className="flex h-14 items-end gap-1" aria-label="Распределение оценок">
        {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => {
          const c = page.distribution[String(n)] ?? 0;
          return (
            <div key={n} className="flex w-5 flex-col items-center gap-0.5" title={`${n}: ${c}`}>
              <div className="w-full rounded-sm bg-brand/60" style={{ height: `${Math.max(2, (c / max) * 40)}px`, opacity: c ? 1 : 0.25 }} />
              <span className="text-[10px] text-fg-soft tabular-nums">{n}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Отзывы на публичной странице педагога: список, свой отзыв и форма для учеников педагога. */
export function TutorReviewsSection({ tutorId, authed, moderator }: { tutorId: string; authed: boolean; moderator: boolean }) {
  const page = useLoad(() => marketplace.reviews(tutorId, authed), [tutorId, authed]);
  const [extra, setExtra] = useState<ReviewPublic[]>([]);
  const [editing, setEditing] = useState(false);
  const [removing, setRemoving] = useState<ReviewPublic | null>(null);
  const data = page.data;
  const items = [...(data?.items ?? []), ...extra];

  return (
    <section id="reviews" className="scroll-mt-20 space-y-4">
      <h2 className="text-lg font-semibold">Отзывы</h2>
      {page.error && <Alert>{page.error}</Alert>}
      {data && (
        <>
          {data.reviews_count > 0 && <Distribution page={data} />}
          {data.mine ? (
            <MyReviewCard review={data.mine} onEdit={() => setEditing(true)} onDeleted={page.reload} />
          ) : (
            data.can_review && (
              <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-surface p-4">
                <p className="min-w-0 flex-1 text-sm">Вы занимаетесь у этого педагога — поделитесь впечатлениями.</p>
                <Button onClick={() => setEditing(true)}>Оставить отзыв</Button>
              </div>
            )
          )}
          {items.length ? (
            <ul className="divide-y divide-line">
              {items.map((r) => (
                <ReviewItem key={r.id} review={r}>
                  {moderator && (
                    <button className="text-sm text-fg-soft hover:text-danger" onClick={() => setRemoving(r)}>
                      Удалить отзыв (модератор)
                    </button>
                  )}
                </ReviewItem>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-fg-soft">Отзывов пока нет.</p>
          )}
          {data.total > items.length && (
            <Button
              variant="secondary"
              onClick={async () => {
                const next = await marketplace.reviews(tutorId, authed, items.length);
                setExtra((prev) => [...prev, ...next.items]);
              }}
            >
              Показать ещё
            </Button>
          )}
        </>
      )}
      <Modal open={editing} onClose={() => setEditing(false)} title="Отзыв о педагоге">
        {editing && (
          <ReviewForm
            tutorId={tutorId}
            mine={data?.mine ?? null}
            onSaved={() => {
              setEditing(false);
              page.reload();
            }}
          />
        )}
      </Modal>
      <ReasonModal
        open={!!removing}
        title="Удалить отзыв"
        label="Причина (увидит автор отзыва)"
        submit="Удалить отзыв"
        onClose={() => setRemoving(null)}
        onSubmit={async (reason) => {
          await marketplace.removeReview(removing!.id, reason);
          setRemoving(null);
          page.reload();
        }}
      />
    </section>
  );
}

/** Модалка с одним текстовым полем: причина удаления, спора и т. п. */
export function ReasonModal({
  open,
  title,
  label,
  submit,
  hint,
  onClose,
  onSubmit,
}: {
  open: boolean;
  title: string;
  label: string;
  submit: string;
  hint?: string;
  onClose: () => void;
  onSubmit: (text: string) => Promise<void>;
}) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  return (
    <Modal open={open} onClose={onClose} title={title}>
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(undefined);
          try {
            await onSubmit(text.trim());
            setText("");
          } catch (err) {
            setError(errorText(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        {error && <Alert>{error}</Alert>}
        {hint && <p className="text-sm text-fg-soft">{hint}</p>}
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">{label}</span>
          <textarea rows={4} required maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} className={TEXTAREA} />
        </label>
        <Button type="submit" loading={busy} disabled={text.trim().length < 3} className="w-full">
          {submit}
        </Button>
      </form>
    </Modal>
  );
}

const REPLY_STATUS = {
  pending: { text: "ответ на проверке", tone: "neutral" },
  approved: { text: "ответ опубликован", tone: "ok" },
  rejected: { text: "ответ не опубликован", tone: "warn" },
} as const;

/** Отзывы о себе — для педагога: публичный ответ и спор. */
export function ReviewsAboutMe() {
  const list = useLoad(() => marketplace.reviewsAboutMe(), []);
  const [replying, setReplying] = useState<string | null>(null);
  const [replyText, setReplyText] = useState("");
  const [disputing, setDisputing] = useState<TutorReview | null>(null);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function saveReply(id: string, text: string) {
    setBusy(true);
    setError(undefined);
    try {
      await marketplace.replyReview(id, text);
      setReplying(null);
      list.reload();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section id="reviews" className="scroll-mt-20 space-y-3 rounded-2xl border border-line bg-surface p-5">
      <div>
        <h2 className="text-lg font-semibold">Отзывы обо мне</h2>
        <p className="mt-1 text-sm text-fg-soft">
          Отзывы оставляют ваши ученики, публикуются они после проверки модератором. Можно ответить публично (ответ тоже проверяется) или
          оспорить отзыв — откроется чат с модератором.
        </p>
      </div>
      {(error || list.error) && <Alert>{error ?? list.error}</Alert>}
      {list.data && !list.data.length && <p className="text-sm text-fg-soft">Опубликованных отзывов пока нет.</p>}
      {list.data && list.data.length > 0 && (
        <ul className="divide-y divide-line">
          {list.data.map((r) => (
            <ReviewItem key={r.id} review={r}>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                {r.reply_status && <Badge tone={REPLY_STATUS[r.reply_status].tone}>{REPLY_STATUS[r.reply_status].text}</Badge>}
                {r.dispute_status === "open" && <Badge tone="brand">спор открыт</Badge>}
                {r.dispute_status === "dismissed" && <Badge>спор отклонён</Badge>}
                {r.dispute_id && (
                  <Link href={`/dashboard/chats?c=${r.dispute_id}`} className="text-brand-text hover:underline">
                    Чат с модератором
                  </Link>
                )}
                <span className="ml-auto flex gap-3">
                  <button
                    className="text-brand-text hover:underline"
                    onClick={() => {
                      setReplying(r.id);
                      setReplyText(r.reply_text ?? "");
                    }}
                  >
                    {r.reply_text ? "Изменить ответ" : "Ответить"}
                  </button>
                  {!r.dispute_status && (
                    <button className="text-fg-soft hover:text-fg" onClick={() => setDisputing(r)}>
                      Оспорить
                    </button>
                  )}
                </span>
              </div>
              {r.reply_status === "pending" && r.reply_text && <p className="text-sm text-fg-soft">Ваш ответ на проверке: «{r.reply_text}»</p>}
              {r.reply_status === "rejected" && r.reply_comment && <p className="text-sm text-tutor">Модератор: {r.reply_comment}</p>}
              {r.dispute_status === "dismissed" && r.dispute_comment && (
                <p className="text-sm text-fg-soft">Решение по спору: {r.dispute_comment}</p>
              )}
              {replying === r.id && (
                <form
                  className="space-y-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void saveReply(r.id, replyText);
                  }}
                >
                  <textarea rows={3} maxLength={2000} className={TEXTAREA} value={replyText} onChange={(e) => setReplyText(e.target.value)} />
                  <div className="flex flex-wrap gap-2">
                    <Button type="submit" loading={busy} disabled={!replyText.trim()}>
                      Отправить на проверку
                    </Button>
                    {r.reply_text && (
                      <Button type="button" variant="ghost" onClick={() => saveReply(r.id, "")}>
                        Убрать ответ
                      </Button>
                    )}
                    <Button type="button" variant="ghost" onClick={() => setReplying(null)}>
                      Отмена
                    </Button>
                  </div>
                </form>
              )}
            </ReviewItem>
          ))}
        </ul>
      )}
      <ReasonModal
        open={!!disputing}
        title="Оспорить отзыв"
        label="Почему отзыв нужно удалить"
        hint="Модератор получит заявку, а у вас откроется чат с модератором в «Сообщениях». Оспорить отзыв можно один раз."
        submit="Оспорить"
        onClose={() => setDisputing(null)}
        onSubmit={async (reason) => {
          await marketplace.disputeReview(disputing!.id, reason);
          setDisputing(null);
          list.reload();
        }}
      />
    </section>
  );
}
