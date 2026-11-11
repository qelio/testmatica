"use client";

import Link from "next/link";

import { seatsText } from "@/components/offers";
import { Alert, Badge, EmptyState, Spinner } from "@/components/ui";
import { marketplace } from "@/lib/api";
import { fmtOfferSchedule, OFFER_STATUS } from "@/lib/format";
import { useLoad } from "@/lib/hooks";

/** Наборы в группы педагога: запись учеников, запуск при минимуме. */
export default function OffersPage() {
  const list = useLoad(() => marketplace.myOffers(), []);
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Наборы в группы</h1>
          <p className="mt-1 text-sm text-fg-soft">Карточка группы в каталоге: ученики записываются, при минимуме вы запускаете группу.</p>
        </div>
        <Link href="/dashboard/offers/new" className="rounded-xl bg-brand px-4 py-2.5 text-sm font-medium text-on-brand hover:bg-brand-strong">
          Новый набор
        </Link>
      </div>
      {list.error && <Alert>{list.error}</Alert>}
      {!list.data ? (
        !list.error && <Spinner />
      ) : !list.data.length ? (
        <EmptyState title="Наборов пока нет" text="Опишите группу: программа, расписание, цена, сколько учеников нужно для старта." />
      ) : (
        <ul className="space-y-2">
          {list.data.map((o) => {
            const st = OFFER_STATUS[o.status];
            const ready = ["recruiting", "underfilled"].includes(o.status) && o.enrolled_count >= o.min_students;
            return (
              <li key={o.id}>
                <Link href={`/dashboard/offers/${o.id}`} className="block rounded-2xl border border-line bg-surface px-5 py-4 hover:border-brand/50">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="min-w-0 flex-1 font-medium">{o.title}</span>
                    {ready && <Badge tone="ok">можно запускать</Badge>}
                    {o.private && <Badge>закрытая</Badge>}
                    <Badge tone={st.tone}>{st.text}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-fg-soft">
                    {o.subject.name} · {fmtOfferSchedule(o.schedule)}
                  </p>
                  <p className="mt-1 text-sm">{seatsText(o)}</p>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
