"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Button, Spinner } from "@/components/ui";
import { billing } from "@/lib/api";
import { fmtRub } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

// Тестовые карты поддельного провайдера — как у настоящих платёжных систем в тестовом режиме.
const CARDS = [
  { last4: "4242", title: "Карта •• 4242", hint: "оплата пройдёт" },
  { last4: "0002", title: "Карта •• 0002", hint: "банк откажет" },
];

/** Страница оплаты поддельного провайдера: вместо неё будет переход на страницу ЮKassa. Деньги не списываются. */
export default function FakePaymentPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const payment = useLoad(() => billing.payment(id), [id]);
  const [card, setCard] = useState("4242");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function finish(outcome: "success" | "cancel") {
    setBusy(true);
    setError(undefined);
    try {
      await billing.fakeResult(id, outcome, card);
      router.replace(`/dashboard/subscription?payment=${id}`);
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  if (payment.error) return <Alert>{payment.error}</Alert>;
  if (!payment.data) return <Spinner />;
  const p = payment.data;
  return (
    <div className="mx-auto max-w-md space-y-5 pt-6">
      <Alert kind="info">Тестовая оплата: деньги не списываются. Позже здесь будет страница платёжной системы.</Alert>
      <section className="space-y-4 rounded-2xl border border-line bg-surface p-5">
        <div>
          <p className="text-sm text-fg-soft">{p.description}</p>
          <p className="text-3xl font-semibold tabular-nums">{fmtRub(p.amount_rub)}</p>
        </div>
        {error && <Alert>{error}</Alert>}
        {p.status !== "pending" ? (
          <>
            <p className="text-sm">Этот платёж уже {p.status === "succeeded" ? "оплачен" : "отменён"}.</p>
            <Button onClick={() => router.replace("/dashboard/subscription")}>К тарифу</Button>
          </>
        ) : (
          <>
            <fieldset className="space-y-2">
              <legend className="mb-1 text-sm font-medium">Тестовая карта</legend>
              {CARDS.map((c) => (
                <label key={c.last4} className="flex items-center gap-3 rounded-xl border border-line px-3 py-2.5 text-sm">
                  <input type="radio" name="card" checked={card === c.last4} onChange={() => setCard(c.last4)} className="accent-brand" />
                  <span className="flex-1">{c.title}</span>
                  <span className="text-fg-soft">{c.hint}</span>
                </label>
              ))}
            </fieldset>
            <div className="flex gap-2">
              <Button className="flex-1" loading={busy} onClick={() => finish("success")}>
                Оплатить
              </Button>
              <Button variant="secondary" disabled={busy} onClick={() => finish("cancel")}>
                Отменить
              </Button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
