"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ApiError, type NotificationItem, notifications } from "@/lib/api";
import { fmtDate, fmtDateTime, fmtTime } from "@/lib/dates";

const CHANGED = "tm:notifications";
const LINK = "mt-1 mr-3 inline-block text-sm font-medium text-brand-text hover:underline";

/** Список уведомлений. Колокольчик и блок на дашборде видны одновременно, поэтому изменения расходятся событием. */
export function useNotifications() {
  const [items, setItems] = useState<NotificationItem[] | null>(null);
  const [unread, setUnread] = useState(0);
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    try {
      const res = await notifications.list();
      setItems(res.items);
      setUnread(res.unread);
      setError(undefined);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось загрузить уведомления");
    }
  }, []);

  useEffect(() => {
    // Загрузка данных при появлении компонента.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
    window.addEventListener(CHANGED, load);
    return () => window.removeEventListener(CHANGED, load);
  }, [load]);

  const markAllRead = useCallback(async () => {
    await notifications.markAllRead();
    window.dispatchEvent(new Event(CHANGED));
  }, []);

  const markRead = useCallback(async (id: string) => {
    await notifications.markRead(id);
    window.dispatchEvent(new Event(CHANGED));
  }, []);

  return { items, unread, error, load, markAllRead, markRead };
}

/** Одно уведомление. onOpen — пользователь перешёл по ссылке из него. */
export function NotificationRow({ n, onOpen }: { n: NotificationItem; onOpen?: () => void }) {
  return (
    <li className="flex gap-3 px-5 py-4">
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
        {typeof n.payload.opens_at === "string" && new Date(n.payload.opens_at) > new Date() && (
          <p className="mt-1 text-sm">Откроется {fmtDateTime(n.payload.opens_at)}</p>
        )}
        {typeof n.payload.deadline === "string" && (
          <p className="mt-1 text-sm">Сдать до {fmtDateTime(n.payload.deadline)}</p>
        )}
        {n.body && <p className="mt-1 text-sm text-fg-soft">{n.body}</p>}
        {typeof n.payload.conversation_id === "string" && (
          <Link href={`/dashboard/chats?c=${n.payload.conversation_id}`} onClick={onOpen} className={LINK}>
            Открыть чат
          </Link>
        )}
        {typeof n.payload.request_id === "string" && typeof n.payload.conversation_id !== "string" && (
          <Link href="/dashboard/requests" onClick={onOpen} className={LINK}>
            К заявкам
          </Link>
        )}
        {typeof n.payload.href === "string" && n.payload.href.startsWith("/") && (
          <Link href={n.payload.href} onClick={onOpen} className={LINK}>
            Открыть
          </Link>
        )}
        {typeof n.payload.assignment_id === "string" && (
          <Link href={`/dashboard/assignments/${n.payload.assignment_id}`} onClick={onOpen} className={LINK}>
            Открыть тест
          </Link>
        )}
        <p className="mt-1 text-xs text-fg-soft">
          {fmtDate(n.created_at, { day: "numeric", month: "long" })}, {fmtTime(n.created_at)}
        </p>
      </div>
    </li>
  );
}
