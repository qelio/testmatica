"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { AdminContentActions } from "@/components/admin-content";
import { priceText, Program, seatsText } from "@/components/offers";
import { Avatar, Rating } from "@/components/tutor-card";
import { Alert, Badge, Button, Spinner } from "@/components/ui";
import { marketplace } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtOfferSchedule, LEVEL_LABELS, OFFER_STATUS } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";
import { useMarketLinks } from "@/lib/market-base";

/** Страница группы — по ссылке открывается и закрытая группа. */
/** Страница набора в группу — на сайте и в кабинете. */
export function GroupOfferPage() {
  const links = useMarketLinks();
  const { id } = useParams<{ id: string }>();
  const { status, user } = useAuth();
  const authed = status === "authenticated";
  const offer = useLoad(() => marketplace.offer(id, authed), [id, authed]);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  if (offer.error) return <Alert>{offer.error}</Alert>;
  if (!offer.data) return <Spinner />;
  const o = offer.data;
  const st = OFFER_STATUS[o.status];
  const isStudent = !!user?.roles.includes("student");

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
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={st.tone}>{st.text}</Badge>
          {o.private && <Badge>закрытая группа</Badge>}
          {o.enrolled && <Badge tone="ok">вы записаны</Badge>}
        </div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{o.title}</h1>
        <p className="text-fg-soft">{[o.subject.name, o.levels.map((l) => LEVEL_LABELS[l]).join(", ")].filter(Boolean).join(" · ")}</p>
      </div>

      <Link href={links.tutor(o.tutor.id)} className="flex items-center gap-3 rounded-2xl border border-line bg-surface p-4 hover:border-brand/50">
        <Avatar url={o.tutor.photo_url} name={o.tutor.full_name} size={48} />
        <span className="min-w-0 flex-1">
          <span className="block font-medium">{o.tutor.full_name}</span>
          <Rating rating={o.tutor.rating} count={o.tutor.reviews_count} />
        </span>
        <span className="text-sm text-brand">Профиль →</span>
      </Link>

      <section className="grid gap-3 rounded-2xl border border-line bg-surface p-5 text-sm sm:grid-cols-2">
        <p>
          <span className="text-fg-soft">Расписание: </span>
          {fmtOfferSchedule(o.schedule)}
        </p>
        <p>
          <span className="text-fg-soft">Цена: </span>
          {priceText(o.price)}
          {o.price > 0 && <span className="block text-xs text-fg-soft">Оплата — перед каждым занятием отдельно.</span>}
        </p>
        <p>
          <span className="text-fg-soft">Места: </span>
          {seatsText(o)}
        </p>
        {o.status === "recruiting" && (
          <p>
            <span className="text-fg-soft">Запись до: </span>
            {new Date(`${o.enroll_until}T00:00:00`).toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}
          </p>
        )}
      </section>

      {error && <Alert>{error}</Alert>}
      <div className="flex flex-wrap gap-2">
        {o.is_owner ? (
          <Link href={`/dashboard/offers/${o.id}`} className="rounded-xl bg-brand px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-strong">
            Управлять набором
          </Link>
        ) : o.enrolled ? (
          ["recruiting", "underfilled"].includes(o.status) && (
            <Button variant="secondary" loading={busy} onClick={() => window.confirm("Отменить запись?") && act(() => marketplace.leaveOffer(o.id))}>
              Отменить запись
            </Button>
          )
        ) : !authed ? (
          <Link href="/login" className="rounded-xl bg-brand px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-strong">
            Войти и записаться
          </Link>
        ) : isStudent ? (
          <Button loading={busy} disabled={!o.joinable} onClick={() => act(() => marketplace.joinOffer(o.id))}>
            {o.joinable ? (o.status === "started" ? "Присоединиться к группе" : "Записаться") : o.seats_left ? "Запись закрыта" : "Мест нет"}
          </Button>
        ) : (
          <p className="self-center text-sm text-fg-soft">Записаться в группу может ученик.</p>
        )}
        <Button
          variant="secondary"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(o.share_url);
              setCopied(true);
            } catch {
              window.prompt("Скопируйте ссылку", o.share_url);
            }
          }}
        >
          {copied ? "Ссылка скопирована" : "Поделиться"}
        </Button>
        <AdminContentActions
          kind="offer"
          id={o.id}
          removed={o.status === "cancelled" || o.status === "closed"}
          onChanged={offer.reload}
        />
      </div>
      {o.enrolled && o.status === "recruiting" && (
        <p className="text-sm text-fg-soft">Место за вами. Когда наберётся минимум, педагог запустит группу — занятия появятся в расписании.</p>
      )}

      {o.description && (
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">О группе</h2>
          <p className="whitespace-pre-line">{o.description}</p>
        </section>
      )}
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Программа</h2>
        <Program items={o.program} />
      </section>
    </div>
  );
}
