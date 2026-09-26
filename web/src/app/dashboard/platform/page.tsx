"use client";

import { useState } from "react";

import { Alert, Button, Field, Spinner } from "@/components/ui";
import { admin } from "@/lib/api";
import { errorText, useLoad } from "@/lib/hooks";

type Item = { key: string; title: string; unit: string; hint?: string };

const GROUPS: { title: string; note?: string; items: Item[] }[] = [
  { title: "Тариф «Базовый»", items: [{ key: "basic_price_rub", title: "Цена в месяц", unit: "₽", hint: "Новая цена — для новых оплат и продлений" }] },
  {
    title: "Лимиты бесплатного тарифа",
    items: [
      { key: "free_max_groups", title: "Активных классов и групп", unit: "шт." },
      { key: "free_video_minutes", title: "Длительность бесплатного видеозанятия", unit: "мин" },
      { key: "free_recordings_keep", title: "Записей занятий хранится", unit: "шт." },
      { key: "free_recording_days", title: "Срок хранения записи", unit: "дней" },
    ],
  },
  { title: "Тариф «Базовый»: записи", items: [{ key: "basic_recording_days", title: "Срок хранения записи", unit: "дней" }] },
  {
    title: "Оплата занятий и escrow",
    note: "Применяются, когда будет подключена оплата занятий.",
    items: [
      { key: "commission_percent", title: "Комиссия платформы с платных занятий", unit: "%" },
      { key: "dispute_window_minutes", title: "Окно спора после занятия", unit: "мин" },
      { key: "payment_deadline_hours", title: "Оплатить не позже чем за", unit: "ч до занятия" },
      { key: "payout_min_rub", title: "Автовывод — от суммы", unit: "₽" },
    ],
  },
];

/** Настройки платформы (ТЗ: тарифы, лимиты free-версии, параметры escrow, языки программирования). */
export default function PlatformSettingsPage() {
  const current = useLoad(() => admin.settings(), []);
  if (current.error) return <Alert>{current.error}</Alert>;
  if (!current.data) return <Spinner />;
  return <SettingsForm initial={current.data} />;
}

function SettingsForm({ initial }: { initial: Record<string, number> }) {
  const [saved, setSaved] = useState(initial);
  const [values, setValues] = useState(initial);
  const [error, setError] = useState<string>();
  const [info, setInfo] = useState<string>();
  const [busy, setBusy] = useState(false);
  const changed = Object.fromEntries(Object.entries(values).filter(([k, v]) => saved[k] !== v));

  return (
    <form
      className="mx-auto max-w-3xl space-y-5"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(undefined);
        setInfo(undefined);
        try {
          const next = await admin.saveSettings(changed);
          setSaved(next);
          setValues(next);
          setInfo("Сохранено. Сервисы применят новые значения в течение 30 секунд.");
        } catch (err) {
          setError(errorText(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      <h1 className="text-2xl font-semibold tracking-tight">Настройки платформы</h1>
      {error && <Alert>{error}</Alert>}
      {info && <Alert kind="success">{info}</Alert>}
      {GROUPS.map((g) => (
        <section key={g.title} className="space-y-3 rounded-2xl border border-line bg-surface p-5">
          <div>
            <h2 className="font-semibold">{g.title}</h2>
            {g.note && <p className="text-sm text-fg-soft">{g.note}</p>}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {g.items.map((it) => (
              <Field
                key={it.key}
                label={`${it.title}, ${it.unit}`}
                type="number"
                min={0}
                required
                hint={it.hint}
                value={values[it.key] ?? ""}
                onChange={(e) => setValues({ ...values, [it.key]: Number(e.target.value) })}
              />
            ))}
          </div>
        </section>
      ))}
      <section className="space-y-1 rounded-2xl border border-line bg-surface p-5 text-sm">
        <h2 className="font-semibold">Языки программирования</h2>
        <p>Python 3 — в задачах с кодом и песочнице.</p>
        <p className="text-fg-soft">Модель задач и песочница рассчитаны на несколько языков; другие появятся здесь, когда будут подключены (решение №8).</p>
      </section>
      <div className="sticky bottom-4 flex justify-end">
        <Button type="submit" loading={busy} disabled={!Object.keys(changed).length}>
          Сохранить{Object.keys(changed).length ? ` (${Object.keys(changed).length})` : ""}
        </Button>
      </div>
    </form>
  );
}
