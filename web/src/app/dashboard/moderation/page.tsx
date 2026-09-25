"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Button, EmptyState, Modal, Spinner } from "@/components/ui";
import { moderation, type QueueItem } from "@/lib/api";
import { fmtDateTime } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

const LINKS: Record<string, (id: string) => string> = {
  course: (id) => `/dashboard/library/course/${id}`,
};

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
                </div>
                {LINKS[item.kind] && (
                  <Link href={LINKS[item.kind](item.ref_id)} target="_blank" className="text-sm font-medium text-brand hover:underline">
                    Открыть ↗
                  </Link>
                )}
              </div>
              {item.status === "pending" && (
                <div className="mt-4 flex gap-2">
                  <Button onClick={() => approve(item)}>Одобрить</Button>
                  <Button variant="secondary" onClick={() => setRejecting(item)}>
                    Вернуть на доработку
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
    <Modal open={!!item} onClose={onClose} title="Вернуть на доработку">
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
            <span className="mb-1.5 block text-sm font-medium">Что нужно исправить (увидит автор)</span>
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
            Отправить автору
          </Button>
        </form>
      )}
    </Modal>
  );
}
