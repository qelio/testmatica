"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { OfferForm, seatsText } from "@/components/offers";
import { Alert, Badge, Button, Field, Spinner } from "@/components/ui";
import { classroom, type GroupOffer, marketplace } from "@/lib/api";
import { fmtDateTime } from "@/lib/dates";
import { fmtOfferSchedule, OFFER_STATUS } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

/** Ссылка на форму расписания с серией занятий группы по карточке набора. */
function scheduleLink(o: GroupOffer): string {
  const s = o.schedule;
  const qs = new URLSearchParams({
    group: o.id,
    date: s.start_date,
    time: s.time,
    duration: String(s.duration_min),
    weekdays: s.weekdays.join(","),
    ...(s.lessons_count ? { count: String(s.lessons_count) } : {}),
  });
  return `/dashboard/schedule?${qs}`;
}

/** Группа создаётся в classroom по событию — ждём её появления (обычно доли секунды). */
async function waitForGroup(id: string): Promise<void> {
  for (let i = 0; i < 20; i++) {
    try {
      await classroom.group(id);
      return;
    } catch {
      await new Promise((r) => setTimeout(r, 500));
    }
  }
}

export default function ManageOfferPage() {
  const { id } = useParams<{ id: string }>();
  const offer = useLoad(() => marketplace.offer(id, true), [id]);
  const [editing, setEditing] = useState(false);
  const [extending, setExtending] = useState(false);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  if (offer.error) return <Alert>{offer.error}</Alert>;
  if (!offer.data) return <Spinner />;
  const o = offer.data;
  const st = OFFER_STATUS[o.status];
  const editable = o.status === "recruiting" || o.status === "underfilled";

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(undefined);
    try {
      await action();
      offer.reload();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <Link href="/dashboard/offers" className="text-sm text-fg-soft hover:text-fg">
        ← Наборы в группы
      </Link>
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="min-w-0 flex-1 text-2xl font-semibold tracking-tight">{o.title}</h1>
        {o.private && <Badge>закрытая</Badge>}
        <Badge tone={st.tone}>{st.text}</Badge>
      </div>
      <p className="text-sm text-fg-soft">
        {o.subject.name} · {fmtOfferSchedule(o.schedule)}
      </p>
      {error && <Alert>{error}</Alert>}

      {o.status === "underfilled" && (
        <Alert kind="info">Срок набора прошёл, а минимум не набрался. Продлите набор или отмените его — записавшиеся получат уведомление.</Alert>
      )}
      {o.status === "started" && (
        <Alert kind="success">
          <span className="flex flex-wrap items-center gap-3">
            <span className="flex-1">Группа запущена: ученики привязаны к вам и добавлены в группу, групповой чат создан.</span>
            <Link href={scheduleLink(o)} className="font-medium underline">
              Поставить занятия в расписание
            </Link>
          </span>
        </Alert>
      )}

      <section className="space-y-3 rounded-2xl border border-line bg-surface p-5">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="min-w-0 flex-1 font-semibold">Записались · {seatsText(o)}</h2>
          <Button
            variant="secondary"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(o.share_url);
                setCopied(true);
              } catch {
                window.prompt("Ссылка на группу", o.share_url);
              }
            }}
          >
            {copied ? "Скопировано" : "Ссылка на группу"}
          </Button>
          <Link href={`/groups/${o.id}`} target="_blank" className="rounded-xl border border-line px-4 py-2 text-sm font-medium hover:bg-muted">
            Как видят ученики
          </Link>
        </div>
        {o.students?.length ? (
          <ul className="divide-y divide-line text-sm">
            {o.students.map((s) => (
              <li key={s.id} className="flex justify-between py-2">
                <span>{s.full_name}</span>
                <span className="text-fg-soft">{fmtDateTime(s.enrolled_at)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-fg-soft">Пока никто не записался. Поделитесь ссылкой{o.private ? " — группа закрытая, в каталоге её нет" : ""}.</p>
        )}
        <div className="flex flex-wrap gap-2 border-t border-line pt-3">
          {editable && (
            <Button
              loading={busy}
              disabled={o.enrolled_count < o.min_students}
              onClick={() =>
                window.confirm("Запустить группу? Ученики привяжутся к вам, карточку больше нельзя будет изменить.") &&
                act(async () => {
                  await marketplace.startOffer(o.id);
                  await waitForGroup(o.id);
                })
              }
            >
              Запустить группу
            </Button>
          )}
          {editable && (
            <Button variant="secondary" onClick={() => setExtending(!extending)}>
              Продлить набор
            </Button>
          )}
          {editable && (
            <Button variant="secondary" onClick={() => setEditing(!editing)}>
              {editing ? "Скрыть форму" : "Изменить карточку"}
            </Button>
          )}
          {o.status !== "cancelled" && o.status !== "closed" && (
            <Button
              variant="ghost"
              className="text-danger"
              disabled={busy}
              onClick={() =>
                window.confirm(o.status === "started" ? "Закрыть набор новых учеников?" : "Отменить набор? Записавшиеся получат уведомление.") &&
                act(() => marketplace.cancelOffer(o.id))
              }
            >
              {o.status === "started" ? "Закрыть набор" : "Отменить набор"}
            </Button>
          )}
        </div>
        {editable && o.enrolled_count < o.min_students && (
          <p className="text-xs text-fg-soft">Запустить можно, когда запишутся {o.min_students} (сейчас {o.enrolled_count}).</p>
        )}
        {extending && <Extend offer={o} onDone={() => { setExtending(false); offer.reload(); }} />}
      </section>

      {editing && editable && (
        <section className="rounded-2xl border border-line bg-surface p-5">
          <OfferForm offer={o} onSaved={() => { setEditing(false); offer.reload(); }} />
        </section>
      )}
    </div>
  );
}

function Extend({ offer, onDone }: { offer: GroupOffer; onDone: () => void }) {
  const [until, setUntil] = useState(offer.enroll_until);
  const [start, setStart] = useState(offer.schedule.start_date);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="grid gap-3 rounded-xl bg-muted p-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(undefined);
        try {
          await marketplace.extendOffer(offer.id, until, start);
          onDone();
        } catch (err) {
          setError(errorText(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      {error && <div className="sm:col-span-3"><Alert>{error}</Alert></div>}
      <Field label="Запись до" type="date" required value={until} onChange={(e) => setUntil(e.target.value)} />
      <Field label="Первое занятие" type="date" required value={start} onChange={(e) => setStart(e.target.value)} />
      <Button type="submit" loading={busy}>
        Продлить
      </Button>
    </form>
  );
}
