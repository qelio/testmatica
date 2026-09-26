"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { OfferCard } from "@/components/offers";
import { RequestForm } from "@/components/request-form";
import { Avatar } from "@/components/tutor-card";
import { Alert, Badge, Button, EmptyState, Field, Modal, Select, Spinner } from "@/components/ui";
import { content, type LessonRequest, marketplace } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/dates";
import { fmtRub, fmtSchedule, GOAL_LABELS, REQUEST_STATUS } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

export default function RequestsPage() {
  const { user } = useAuth();
  if (!user) return <Spinner />;
  return user.roles.includes("teacher") ? <TutorView /> : <StudentView />;
}

function RequestSummary({ r }: { r: LessonRequest }) {
  return (
    <div className="space-y-1 text-sm">
      <p>
        <b>{r.subject_name}</b> · {GOAL_LABELS[r.goal]} · {fmtRub(r.price)} за {r.duration_min} мин · {fmtSchedule(r.schedule)}
      </p>
      {r.current.length > 0 && <p className="text-fg-soft">Уже знает: {r.current.join(", ")}</p>}
      {r.desired.length > 0 && <p className="text-fg-soft">Хочет: {r.desired.join(", ")}</p>}
      {r.comment && <p className="whitespace-pre-line">«{r.comment}»</p>}
    </div>
  );
}

/** Записи в группы из каталога — место зарезервировано до запуска группы. */
function MyEnrollments() {
  const list = useLoad(() => marketplace.enrolledOffers(), []);
  if (!list.data?.length) return null;
  return (
    <section className="space-y-2">
      <h2 className="font-semibold">Мои записи в группы</h2>
      <div className="grid gap-3 md:grid-cols-2">
        {list.data.map((o) => (
          <OfferCard key={o.id} offer={o} />
        ))}
      </div>
    </section>
  );
}

function StudentView() {
  const list = useLoad(() => marketplace.myRequests(), []);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string>();
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Мои заявки</h1>
        <div className="flex gap-2">
          <Link href="/tutors" className="rounded-xl border border-line px-4 py-2.5 text-sm font-medium hover:bg-muted">
            Найти репетитора
          </Link>
          <Button onClick={() => setCreating(true)}>Открытая заявка</Button>
        </div>
      </div>
      <p className="text-sm text-fg-soft">
        Выберите репетитора в поиске («Хочу с вами заниматься») или опубликуйте открытую заявку — откликнуться смогут все репетиторы по предмету.
      </p>
      <MyEnrollments />
      {(list.error || error) && <Alert>{list.error || error}</Alert>}
      {!list.data ? (
        !list.error && <Spinner />
      ) : !list.data.length ? (
        <EmptyState title="Заявок пока нет" text="Опишите, что нужно, и предложите цену — договоритесь с репетитором в чате." />
      ) : (
        <ul className="space-y-3">
          {list.data.map((r) => (
            <li key={r.id} className="space-y-3 rounded-2xl border border-line bg-surface p-5">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={REQUEST_STATUS[r.status].tone}>{REQUEST_STATUS[r.status].text}</Badge>
                <span className="text-sm text-fg-soft">
                  {r.direct ? "адресная" : "открытая"} · от {fmtDateTime(r.created_at)}
                  {r.status === "open" && ` · до ${fmtDateTime(r.expires_at)}`}
                </span>
                {r.status === "open" && (
                  <button
                    className="ml-auto text-sm text-fg-soft hover:text-danger"
                    onClick={async () => {
                      if (!window.confirm("Закрыть заявку? Переговоры по ней завершатся.")) return;
                      try {
                        await marketplace.closeRequest(r.id);
                        list.reload();
                      } catch (e) {
                        setError(errorText(e));
                      }
                    }}
                  >
                    Закрыть заявку
                  </button>
                )}
              </div>
              <RequestSummary r={r} />
              {r.responses.length > 0 ? (
                <ul className="divide-y divide-line rounded-xl border border-line">
                  {r.responses.map((x) => (
                    <li key={x.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                      <Avatar url={x.tutor.photo_url} name={x.tutor.full_name} size={36} />
                      <Link href={`/tutors/${x.tutor.id}`} className="min-w-0 flex-1 font-medium hover:underline">
                        {x.tutor.full_name}
                      </Link>
                      <span>
                        {fmtRub(x.price)}
                        <span className="text-fg-soft"> · {x.proposed_by === "tutor" ? "предлагает репетитор" : "ваша цена"}</span>
                      </span>
                      {x.status === "agreed" && <Badge tone="ok">договорились</Badge>}
                      {x.status === "closed" && <Badge>завершены</Badge>}
                      <Link href={`/dashboard/chats?c=${x.id}`} className="font-medium text-brand hover:underline">
                        Чат
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                r.status === "open" && <p className="text-sm text-fg-soft">Откликов пока нет — репетиторы получили уведомление.</p>
              )}
            </li>
          ))}
        </ul>
      )}
      <Modal open={creating} onClose={() => setCreating(false)} title="Открытая заявка">
        {creating && (
          <RequestForm
            onCreated={() => {
              setCreating(false);
              list.reload();
            }}
          />
        )}
      </Modal>
    </div>
  );
}

function TutorView() {
  const [tab, setTab] = useState<"open" | "mine">("open");
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <h1 className="text-2xl font-semibold tracking-tight">Заявки учеников</h1>
      <div className="flex rounded-xl border border-line bg-muted p-1 text-sm sm:w-fit" role="tablist">
        {(
          [
            ["open", "Открытые заявки"],
            ["mine", "Мои переговоры"],
          ] as const
        ).map(([k, t]) => (
          <button
            key={k}
            role="tab"
            aria-selected={tab === k}
            onClick={() => setTab(k)}
            className={`flex-1 rounded-lg px-4 py-1.5 font-medium whitespace-nowrap ${tab === k ? "bg-surface shadow-sm" : "text-fg-soft hover:text-fg"}`}
          >
            {t}
          </button>
        ))}
      </div>
      {tab === "open" ? <OpenRequests /> : <MyNegotiations />}
    </div>
  );
}

function OpenRequests() {
  const router = useRouter();
  const subjects = useLoad(() => content.subjects(), []);
  const [subject, setSubject] = useState("");
  const [all, setAll] = useState(false);
  const list = useLoad(() => marketplace.openRequests({ subject_id: subject || undefined, all_subjects: all }), [subject, all]);
  const [responding, setResponding] = useState<LessonRequest | null>(null);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-60">
          <Select label="Предмет" value={subject} onChange={(e) => setSubject(e.target.value)}>
            <option value="">Из моего профиля</option>
            {subjects.data?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
        </div>
        {!subject && (
          <label className="flex items-center gap-2 pb-3 text-sm">
            <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} className="h-4 w-4 accent-brand" />
            Все предметы
          </label>
        )}
      </div>
      {list.error && <Alert>{list.error}</Alert>}
      {!list.data ? (
        !list.error && <Spinner />
      ) : !list.data.length ? (
        <EmptyState
          title="Открытых заявок нет"
          text="Заявки по предметам из вашего профиля появятся здесь; о новых придёт уведомление. Профиль должен быть включён в поиске."
        />
      ) : (
        <ul className="space-y-3">
          {list.data.map((r) => {
            const mine = r.responses[0];
            return (
              <li key={r.id} className="space-y-3 rounded-2xl border border-line bg-surface p-5">
                <div className="flex flex-wrap items-center gap-2 text-sm text-fg-soft">
                  <span className="font-medium text-fg">{r.student.full_name}</span> · {fmtDateTime(r.created_at)}
                </div>
                <RequestSummary r={r} />
                {mine ? (
                  <Link href={`/dashboard/chats?c=${mine.id}`} className="inline-block text-sm font-medium text-brand hover:underline">
                    Вы откликнулись — открыть чат
                  </Link>
                ) : (
                  <Button onClick={() => setResponding(r)}>Откликнуться</Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <Modal open={!!responding} onClose={() => setResponding(null)} title="Отклик на заявку">
        {responding && (
          <RespondForm
            request={responding}
            onDone={(chatId) => {
              setResponding(null);
              router.push(`/dashboard/chats?c=${chatId}`);
            }}
          />
        )}
      </Modal>
    </div>
  );
}

function RespondForm({ request, onDone }: { request: LessonRequest; onDone: (chatId: string) => void }) {
  const [price, setPrice] = useState(request.price);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(undefined);
        try {
          const n = await marketplace.respond(request.id, { price: price === request.price ? null : price, message });
          onDone(n.response.id);
        } catch (err) {
          setError(errorText(err));
          setBusy(false);
        }
      }}
    >
      {error && <Alert>{error}</Alert>}
      <RequestSummary r={request} />
      <Field
        label="Ваша цена за занятие, ₽"
        type="number"
        min={100}
        step={50}
        value={price}
        hint={price === request.price ? "Цена ученика — он сможет сразу договориться" : "Ученик увидит ваше предложение и сможет согласиться"}
        onChange={(e) => setPrice(Number(e.target.value))}
      />
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium">Сообщение ученику</span>
        <textarea
          rows={3}
          maxLength={2000}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Коротко о себе и как будете заниматься"
          className="w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
        />
      </label>
      <Button type="submit" loading={busy} className="w-full">
        Откликнуться и открыть чат
      </Button>
    </form>
  );
}

function MyNegotiations() {
  const list = useLoad(() => marketplace.myResponses(), []);
  if (list.error) return <Alert>{list.error}</Alert>;
  if (!list.data) return <Spinner />;
  if (!list.data.length) return <EmptyState title="Переговоров пока нет" text="Откликнитесь на заявку или дождитесь, когда ученик напишет вам из профиля." />;
  return (
    <ul className="space-y-3">
      {list.data.map((r) => {
        const x = r.responses[0];
        return (
          <li key={r.id} className="space-y-2 rounded-2xl border border-line bg-surface p-5">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">{r.student.full_name}</span>
              <Badge tone={REQUEST_STATUS[r.status].tone}>{REQUEST_STATUS[r.status].text}</Badge>
              {x?.status === "agreed" && <Badge tone="ok">вы договорились</Badge>}
              {x?.status === "closed" && <Badge>переговоры завершены</Badge>}
              {r.direct && <Badge tone="brand">вам лично</Badge>}
            </div>
            <RequestSummary r={r} />
            {x && (
              <p className="text-sm">
                Сейчас: <b>{fmtRub(x.price)}</b> · {x.proposed_by === "tutor" ? "ваше предложение" : "цена ученика"} ·{" "}
                <Link href={`/dashboard/chats?c=${x.id}`} className="font-medium text-brand hover:underline">
                  чат
                </Link>
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}
