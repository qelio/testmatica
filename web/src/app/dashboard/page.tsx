"use client";

import { useCallback, useEffect, useState } from "react";

import { Alert } from "@/components/ui";
import { ApiError, type NotificationItem, notifications } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/dates";

const MODE_TEXT = {
  school: "Вы в режиме «Школьный учитель»: классы, журнал и КТП.",
  tutor: "Вы в режиме «Репетитор»: ученики, заявки и оплата через платформу.",
};

export default function DashboardPage() {
  const { user } = useAuth();
  const [items, setItems] = useState<NotificationItem[] | null>(null);
  const [unread, setUnread] = useState(0);
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    try {
      const res = await notifications.list();
      setItems(res.items);
      setUnread(res.unread);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось загрузить уведомления");
    }
  }, []);

  useEffect(() => {
    // Загрузка данных при открытии страницы.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  if (!user) return null;
  const firstName = user.full_name.split(" ")[0];

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Здравствуйте, {firstName}!</h1>
        {user.teacher_mode && <p className="mt-2 text-fg-soft">{MODE_TEXT[user.teacher_mode]}</p>}
      </div>

      <section className="rounded-2xl border border-line bg-surface">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="font-semibold">
            Уведомления
            {unread > 0 && (
              <span className="ml-2 rounded-full bg-brand px-2 py-0.5 text-xs font-medium text-white">{unread}</span>
            )}
          </h2>
          {unread > 0 && (
            <button
              className="text-sm text-brand hover:underline"
              onClick={async () => {
                await notifications.markAllRead();
                await load();
              }}
            >
              Прочитать все
            </button>
          )}
        </div>
        {error && (
          <div className="p-5">
            <Alert>{error}</Alert>
          </div>
        )}
        {items === null && !error && <p className="px-5 py-6 text-sm text-fg-soft">Загрузка…</p>}
        {items?.length === 0 && <p className="px-5 py-6 text-sm text-fg-soft">Пока нет уведомлений</p>}
        <ul className="divide-y divide-line">
          {items?.map((n) => (
            <li key={n.id} className="flex gap-3 px-5 py-4">
              <span
                className={`mt-2 h-2 w-2 shrink-0 rounded-full ${n.read_at ? "bg-transparent" : "bg-brand"}`}
                aria-label={n.read_at ? undefined : "Не прочитано"}
              />
              <div className="min-w-0">
                <p className="font-medium">{n.title}</p>
                {(n.payload.new_starts_at || n.payload.starts_at) && (
                  <p className="mt-1 text-sm">
                    {n.payload.new_starts_at
                      ? `Новое время: ${fmtDateTime(n.payload.new_starts_at)}`
                      : fmtDateTime(n.payload.starts_at as string)}
                  </p>
                )}
                {n.body && <p className="mt-1 text-sm text-fg-soft">{n.body}</p>}
                <p className="mt-1 text-xs text-fg-soft">{new Date(n.created_at).toLocaleString("ru-RU")}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-2xl border border-dashed border-line p-5 text-sm text-fg-soft">
        Журнал, задания и библиотека появятся на следующих этапах разработки.
      </section>
    </div>
  );
}
