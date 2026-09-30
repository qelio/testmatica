"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Alert, Badge, Button, Spinner } from "@/components/ui";
import { billing, type BillingPayment, type SubscriptionState } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/dates";
import { fmtRub } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

// Сравнение тарифов (ТЗ, раздел 12). soon — возможность ещё не сделана, появится на следующих этапах.
const FEATURES: { title: string; free: string; basic: string; soon?: boolean }[] = [
  { title: "Классы и группы", free: "до 3 активных", basic: "без ограничений" },
  { title: "Видеосвязь на бесплатных занятиях", free: "до 40 минут", basic: "без лимита" },
  { title: "Записи занятий", free: "3 последние, 14 дней", basic: "без лимита, 30 дней" },
  { title: "Журнал, КТП, расписание, тесты", free: "✓", basic: "✓" },
  { title: "Публичный профиль и заявки учеников", free: "✓", basic: "✓" },
  { title: "Модерация ваших материалов", free: "в общей очереди", basic: "в первую очередь" },
  { title: "Прокторинг тестов", free: "—", basic: "✓" },
  { title: "Аналитика", free: "средний балл, посещаемость", basic: "+ динамика, сравнение, тепловая карта, ведомость, PDF/Excel" },
  { title: "Поддержка", free: "обычная", basic: "приоритетная" },
];

export default function SubscriptionPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Subscription />
    </Suspense>
  );
}

function Subscription() {
  const state = useLoad(() => billing.subscription(), []);
  const payments = useLoad(() => billing.payments(), []);
  const params = useSearchParams();
  const router = useRouter();
  const returned = params.get("payment");

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Тариф</h1>
        <p className="mt-1 text-sm text-fg-soft">Подписка — только для педагогов, оплата помесячно.</p>
      </div>
      {returned && (
        <PaymentResult
          id={returned}
          onFinished={() => {
            state.reload();
            payments.reload();
          }}
          onClose={() => router.replace("/dashboard/subscription")}
        />
      )}
      {state.error && <Alert>{state.error}</Alert>}
      {!state.data ? !state.error && <Spinner /> : <Current s={state.data} onChanged={() => { state.reload(); payments.reload(); }} />}
      {state.data && <Compare s={state.data} />}
      {payments.data && payments.data.length > 0 && <History items={payments.data} />}
    </div>
  );
}

/** Вернулись со страницы оплаты: ждём, пока провайдер подтвердит платёж. */
function PaymentResult({ id, onFinished, onClose }: { id: string; onFinished: () => void; onClose: () => void }) {
  const [p, setP] = useState<BillingPayment>();
  useEffect(() => {
    let stop = false;
    let tries = 0;
    async function poll() {
      try {
        const next = await billing.payment(id);
        if (stop) return;
        setP(next);
        if (next.status !== "pending") {
          onFinished();
          return;
        }
      } catch {
        /* повторим */
      }
      if (++tries < 20 && !stop) setTimeout(poll, 1500);
    }
    void poll();
    return () => {
      stop = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);
  if (!p || p.status === "pending") return <Alert kind="info">Проверяем оплату…</Alert>;
  return (
    <Alert kind={p.status === "succeeded" ? "success" : "error"}>
      <span className="flex flex-wrap items-center gap-3">
        <span className="flex-1">{p.status === "succeeded" ? "Оплата прошла — тариф «Базовый» подключён." : `Оплата не прошла: ${p.error ?? "отменена"}.`}</span>
        <button className="text-sm underline" onClick={onClose}>
          Скрыть
        </button>
      </span>
    </Alert>
  );
}

function Current({ s, onChanged }: { s: SubscriptionState; onChanged: () => void }) {
  const [autoRenew, setAutoRenew] = useState(true);
  const [offer, setOffer] = useState(false); // акцепт оферты — оплата с этой галочкой
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const basic = s.plan === "basic";

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(undefined);
    try {
      await action();
      onChanged();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function pay() {
    setBusy(true);
    setError(undefined);
    try {
      const p = await billing.checkout(basic ? s.auto_renew || autoRenew : autoRenew);
      // Страница оплаты провайдера (сейчас — тестовая страница на нашем сайте).
      if (p.confirmation_url) window.location.assign(p.confirmation_url);
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  return (
    <section className={`space-y-4 rounded-2xl border p-5 ${basic ? "border-ok/40 bg-ok/5" : "border-line bg-surface"}`}>
      {error && <Alert>{error}</Alert>}
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm text-fg-soft">Ваш тариф</p>
          <p className="text-xl font-semibold">{basic ? "Базовый" : "Бесплатный"}</p>
          {basic && s.period_end && (
            <p className="text-sm text-fg-soft">
              {s.auto_renew ? "Продлится автоматически" : "Действует до"} {fmtDate(s.period_end, { day: "numeric", month: "long", year: "numeric" })}
            </p>
          )}
          {!basic && s.period_end && (
            <p className="text-sm text-fg-soft">«Базовый» закончился {fmtDate(s.period_end, { day: "numeric", month: "long" })}</p>
          )}
        </div>
        <Badge tone={basic ? "ok" : "neutral"}>{basic ? "подписка активна" : "без подписки"}</Badge>
      </div>

      {basic && (
        <div className="space-y-2 border-t border-line pt-4 text-sm">
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={s.auto_renew}
              disabled={busy || (!s.payment_method_title && !s.auto_renew)}
              onChange={(e) => run(() => billing.setAutoRenew(e.target.checked))}
              className="h-4 w-4 accent-ok"
            />
            <span>
              Продлевать автоматически
              {s.payment_method_title ? <span className="text-fg-soft"> · {s.payment_method_title}</span> : <span className="text-fg-soft"> · карта не сохранена</span>}
            </span>
          </label>
          {s.payment_method_title && (
            <button className="text-fg-soft hover:text-danger" disabled={busy} onClick={() => window.confirm("Отвязать карту? Автопродление выключится.") && run(() => billing.forgetCard())}>
              Отвязать карту
            </button>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
        {s.pending_payment?.confirmation_url && (
          <Button variant="secondary" onClick={() => window.location.assign(s.pending_payment!.confirmation_url!)}>
            Продолжить начатую оплату
          </Button>
        )}
        <Button onClick={pay} loading={busy} disabled={!offer}>
          {basic ? `Продлить на месяц — ${fmtRub(s.price_rub)}` : `Подключить «Базовый» — ${fmtRub(s.price_rub)} в месяц`}
        </Button>
        {!(basic && s.auto_renew) && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={autoRenew} onChange={(e) => setAutoRenew(e.target.checked)} className="h-4 w-4 accent-brand" />
            Сохранить карту и продлевать автоматически
          </label>
        )}
        <label className="flex basis-full items-start gap-2 text-sm">
          <input type="checkbox" checked={offer} onChange={(e) => setOffer(e.target.checked)} className="mt-0.5 h-4 w-4 accent-brand" />
          <span className="text-fg-soft">
            Принимаю условия{" "}
            <Link href="/legal/offer" target="_blank" className="text-brand underline">
              публичной оферты
            </Link>
            {autoRenew || (basic && s.auto_renew) ? ", в том числе автоматические списания раз в месяц — отключить можно здесь в любой момент" : ""}
          </span>
        </label>
      </div>
      {basic && <p className="text-xs text-fg-soft">Досрочная оплата добавит месяц к текущему сроку.</p>}
    </section>
  );
}

function Compare({ s }: { s: SubscriptionState }) {
  return (
    <section className="overflow-x-auto rounded-2xl border border-line bg-surface">
      <table className="w-full min-w-[34rem] text-sm">
        <thead>
          <tr className="border-b border-line text-left">
            <th className="px-4 py-3 font-medium text-fg-soft">Возможность</th>
            <th className={`px-4 py-3 font-semibold ${s.plan === "free" ? "text-brand" : ""}`}>Бесплатный</th>
            <th className={`px-4 py-3 font-semibold ${s.plan === "basic" ? "text-brand" : ""}`}>Базовый · {fmtRub(s.price_rub)}/мес</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {FEATURES.map((f) => (
            <tr key={f.title}>
              <td className="px-4 py-2.5">
                {f.title}
                {f.soon && <span className="ml-2 text-xs text-fg-soft">появится позже</span>}
              </td>
              <td className="px-4 py-2.5 text-fg-soft">{f.free}</td>
              <td className="px-4 py-2.5">{f.basic}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

const PAY_STATUS = {
  pending: { text: "ожидает оплаты", tone: "neutral" },
  succeeded: { text: "оплачен", tone: "ok" },
  canceled: { text: "не прошёл", tone: "warn" },
} as const;

function History({ items }: { items: BillingPayment[] }) {
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold">Платежи</h2>
      <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
        {items.map((p) => (
          <li key={p.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-sm">
            <span className="min-w-0 flex-1">
              {p.description}
              <span className="block text-xs text-fg-soft">
                {fmtDateTime(p.paid_at ?? p.created_at)}
                {p.error && ` · ${p.error}`}
              </span>
            </span>
            <span className="tabular-nums">{fmtRub(p.amount_rub)}</span>
            <Badge tone={PAY_STATUS[p.status].tone}>{PAY_STATUS[p.status].text}</Badge>
          </li>
        ))}
      </ul>
    </section>
  );
}
