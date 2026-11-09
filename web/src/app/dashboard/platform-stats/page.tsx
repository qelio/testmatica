"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Spinner } from "@/components/ui";
import { admin, type UserStats } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/auth";
import { fmtDateTime } from "@/lib/dates";
import { fmtRub } from "@/lib/format";
import { useLoad } from "@/lib/hooks";

/** Статистика платформы (ТЗ: DAU/MAU, объём транзакций, конверсии, активность контента, топ педагогов). */
export default function PlatformStatsPage() {
  const [days, setDays] = useState(30);
  const users = useLoad(() => admin.userStats(days), [days]);
  const billing = useLoad(() => admin.billingStats(), []);
  const activity = useLoad(() => admin.auditStats(days), [days]);
  const payments = useLoad(() => admin.payments({ limit: 10 }), []);
  // Имена для топа педагогов и последних платежей.
  const ids = [...(activity.data?.top_teachers.map((t) => t.actor_id) ?? []), ...(payments.data?.map((p) => p.user_id) ?? [])];
  const names = useLoad(async () => (ids.length ? admin.users({ ids, limit: 200 }) : null), [ids.join()]);
  const name = (id: string) => names.data?.items.find((u) => u.id === id)?.full_name ?? "…";

  const teachers = users.data?.by_role.teacher ?? 0;
  const error = users.error || billing.error || activity.error;
  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Статистика платформы</h1>
        <div className="flex gap-1.5">
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              aria-pressed={days === d}
              onClick={() => setDays(d)}
              className={`rounded-lg border px-3 py-1.5 text-sm ${days === d ? "border-brand bg-brand/10 text-brand-text" : "border-line text-fg-soft"}`}
            >
              {d} дней
            </button>
          ))}
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      {!users.data || !billing.data ? (
        !error && <Spinner />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Card title="Пользователей" value={users.data.total} sub={Object.entries(users.data.by_role).map(([r, n]) => `${ROLE_LABELS[r] ?? r}: ${n}`).join(" · ")} />
            <Card title="DAU / WAU / MAU" value={`${users.data.dau} / ${users.data.wau} / ${users.data.mau}`}
              sub={users.data.mau ? `вовлечённость DAU/MAU ${Math.round((users.data.dau / users.data.mau) * 100)}%` : undefined} />
            <Card title="На тарифе «Базовый»" value={billing.data.subscribers}
              sub={teachers ? `конверсия педагогов ${Math.round((billing.data.subscribers / teachers) * 100)}% · автопродление ${billing.data.auto_renew}` : undefined} />
            <Card title="Оплачено всего" value={fmtRub(billing.data.revenue_rub)} sub={`платили: ${billing.data.ever_paid}`} />
          </div>

          <section className="rounded-2xl border border-line bg-surface p-5">
            <h2 className="mb-3 font-semibold">Активные пользователи и регистрации по дням</h2>
            <DailyBars series={users.data.series} />
          </section>

          <div className="grid gap-4 lg:grid-cols-2">
            <section className="rounded-2xl border border-line bg-surface p-5">
              <h2 className="mb-3 font-semibold">Активность за {days} дней</h2>
              {!activity.data ? (
                <Spinner />
              ) : (
                <ul className="divide-y divide-line text-sm">
                  {activity.data.activity.map((a) => (
                    <li key={a.type} className="flex justify-between py-1.5">
                      <span>{a.title}</span>
                      <b className="tabular-nums">{a.total}</b>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="rounded-2xl border border-line bg-surface p-5">
              <h2 className="mb-1 font-semibold">Топ педагогов</h2>
              <p className="mb-3 text-xs text-fg-soft">По действиям в учёбе: занятия, тесты, оценки, видеозанятия.</p>
              {activity.data?.top_teachers.length ? (
                <ol className="space-y-1.5 text-sm">
                  {activity.data.top_teachers.map((t, i) => (
                    <li key={t.actor_id} className="flex items-center gap-2">
                      <span className="w-5 text-fg-soft">{i + 1}.</span>
                      <Link href={`/dashboard/users/${t.actor_id}`} className="min-w-0 flex-1 truncate hover:text-brand-text">
                        {name(t.actor_id)}
                      </Link>
                      <span className="tabular-nums text-fg-soft">{t.actions}</span>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-sm text-fg-soft">Пока нет данных.</p>
              )}
            </section>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <section className="rounded-2xl border border-line bg-surface p-5">
              <h2 className="mb-3 font-semibold">Выручка по месяцам</h2>
              {billing.data.months.length ? (
                <ul className="space-y-1.5 text-sm">
                  {billing.data.months.map((m) => {
                    const top = Math.max(...billing.data!.months.map((x) => x.revenue_rub), 1);
                    return (
                      <li key={m.month} className="flex items-center gap-2">
                        <span className="w-20 text-fg-soft">{new Date(`${m.month}T00:00:00`).toLocaleDateString("ru-RU", { month: "short", year: "numeric" })}</span>
                        <span className="h-4 flex-1 overflow-hidden rounded bg-muted">
                          <span className="block h-full rounded bg-brand" style={{ width: `${(m.revenue_rub / top) * 100}%` }} />
                        </span>
                        <span className="w-28 text-right tabular-nums">{fmtRub(m.revenue_rub)}</span>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="text-sm text-fg-soft">Оплат пока не было.</p>
              )}
              <p className="mt-3 text-xs text-fg-soft">Пока — только подписки. Оплата занятий появится позже.</p>
            </section>
            <section className="rounded-2xl border border-line bg-surface p-5">
              <h2 className="mb-3 font-semibold">Последние платежи</h2>
              <ul className="divide-y divide-line text-sm">
                {payments.data?.map((p) => (
                  <li key={p.id} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 py-1.5">
                    <Link href={`/dashboard/users/${p.user_id}`} className="min-w-0 flex-1 truncate hover:text-brand-text">
                      {name(p.user_id)}
                    </Link>
                    <span className="text-xs text-fg-soft">{fmtDateTime(p.created_at)}</span>
                    <span className="tabular-nums">{fmtRub(p.amount_rub)}</span>
                    <Badge tone={p.status === "succeeded" ? "ok" : p.status === "canceled" ? "warn" : "neutral"}>
                      {p.status === "succeeded" ? "оплачен" : p.status === "canceled" ? "не прошёл" : "ожидает"}
                    </Badge>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </>
      )}
    </div>
  );
}

function Card({ title, value, sub }: { title: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-2xl border border-line bg-surface px-4 py-3">
      <p className="text-xs text-fg-soft">{title}</p>
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-fg-soft">{sub}</p>}
    </div>
  );
}

/** Столбики по дням: активные (заливка) и регистрации (тёмная часть снизу). */
function DailyBars({ series }: { series: UserStats["series"] }) {
  const top = Math.max(1, ...series.map((d) => Math.max(d.active, d.registrations)));
  return (
    <div className="space-y-2">
      <div className="flex h-40 items-end gap-0.5">
        {series.map((d) => (
          <div
            key={d.day}
            className="relative flex-1 rounded-t bg-brand/30"
            style={{ height: `${(d.active / top) * 100}%`, minHeight: 2 }}
            title={`${new Date(`${d.day}T00:00:00`).toLocaleDateString("ru-RU")}: активных ${d.active}, регистраций ${d.registrations}`}
          >
            {d.registrations > 0 && (
              <div className="absolute inset-x-0 bottom-0 rounded-t bg-brand" style={{ height: `${(d.registrations / Math.max(d.active, d.registrations)) * 100}%` }} />
            )}
          </div>
        ))}
      </div>
      <p className="flex gap-4 text-xs text-fg-soft">
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm bg-brand/30" /> активные за день
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm bg-brand" /> регистрации
        </span>
      </p>
    </div>
  );
}
