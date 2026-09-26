"use client";

import { useState } from "react";

import { REVIEW_STATUS, ReviewForm } from "@/components/reviews";
import { Alert, Badge, Button, EmptyState, Modal, Spinner } from "@/components/ui";
import { classroom, marketplace, type MyTeacher } from "@/lib/api";
import { errorText, useLoad } from "@/lib/hooks";

export default function MyTeachersPage() {
  const teachers = useLoad(() => classroom.myTeachers(), []);
  const groups = useLoad(() => classroom.myGroups(), []);
  const reviews = useLoad(() => marketplace.myReviews(), []);
  const [reviewing, setReviewing] = useState<MyTeacher | null>(null);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState<string>();

  async function respond(linkId: string, accept: boolean) {
    setBusy(linkId);
    setError(undefined);
    try {
      await (accept ? classroom.acceptRequest(linkId) : classroom.declineRequest(linkId));
      teachers.reload();
      groups.reload();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(undefined);
    }
  }

  const pending = teachers.data?.filter((t) => t.status === "pending") ?? [];
  const active = teachers.data?.filter((t) => t.status === "active") ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <h1 className="text-2xl font-semibold tracking-tight">Мои педагоги</h1>
      {(error || teachers.error) && <Alert>{error ?? teachers.error}</Alert>}
      {!teachers.data && !teachers.error && <Spinner />}

      {pending.length > 0 && (
        <section className="space-y-3">
          <h2 className="font-semibold">Запросы на добавление</h2>
          {pending.map((t) => (
            <div
              key={t.link_id}
              className="flex flex-wrap items-center gap-3 rounded-2xl border border-brand/40 bg-brand/5 px-5 py-4"
            >
              <p className="min-w-0 flex-1">
                <b>{t.full_name}</b> хочет добавить вас в свои ученики
              </p>
              <div className="flex gap-2">
                <Button variant="secondary" loading={busy === t.link_id} onClick={() => respond(t.link_id, false)}>
                  Отклонить
                </Button>
                <Button loading={busy === t.link_id} onClick={() => respond(t.link_id, true)}>
                  Принять
                </Button>
              </div>
            </div>
          ))}
        </section>
      )}

      {teachers.data && (
        <section className="space-y-3">
          <h2 className="font-semibold">Педагоги</h2>
          {active.length === 0 ? (
            <EmptyState
              title="Пока нет педагогов"
              text="Когда педагог добавит вас или вы примете приглашение, он появится здесь."
            />
          ) : (
            <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
              {active.map((t) => (
                <li key={t.link_id} className="px-5 py-3.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="min-w-0 flex-1 font-medium">{t.full_name}</p>
                    {(() => {
                      const mine = reviews.data?.find((r) => r.tutor_id === t.teacher_id);
                      if (mine?.status === "removed") return <Badge tone="warn">{REVIEW_STATUS.removed.text}</Badge>;
                      return (
                        <>
                          {mine && <Badge tone={REVIEW_STATUS[mine.status].tone}>отзыв {mine.rating}/10 · {REVIEW_STATUS[mine.status].text}</Badge>}
                          <button className="text-sm font-medium text-brand hover:underline" onClick={() => setReviewing(t)}>
                            {mine ? "Изменить отзыв" : "Оставить отзыв"}
                          </button>
                        </>
                      );
                    })()}
                  </div>
                  {t.groups.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {t.groups.map((g) => (
                        <Badge key={g.id}>{g.title}</Badge>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <Modal open={!!reviewing} onClose={() => setReviewing(null)} title={`Отзыв: ${reviewing?.full_name ?? ""}`}>
        {reviewing && (
          <ReviewForm
            tutorId={reviewing.teacher_id}
            mine={reviews.data?.find((r) => r.tutor_id === reviewing.teacher_id) ?? null}
            onSaved={() => {
              setReviewing(null);
              reviews.reload();
            }}
          />
        )}
      </Modal>

      {groups.data && groups.data.length > 0 && (
        <section className="space-y-3">
          <h2 className="font-semibold">Мои группы</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {groups.data.map((g) => (
              <div key={g.id} className="rounded-2xl border border-line bg-surface p-4">
                <p className="font-medium">{g.title}</p>
                <p className="mt-1 text-sm text-fg-soft">{[g.subject, g.teacher_name].filter(Boolean).join(" · ")}</p>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
