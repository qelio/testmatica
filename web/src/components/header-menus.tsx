"use client";

import { Bell, ChevronDown, MessageSquare } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Avatar, conversationPreview, shortTime } from "@/components/chat-preview";
import { NotificationRow, useNotifications } from "@/components/notifications";
import { Alert } from "@/components/ui";
import type { Conversation } from "@/lib/api";
import { ROLE_LABELS, useAuth } from "@/lib/auth";
import { useRealtime } from "@/lib/realtime";
import { ThemeSwitch } from "@/lib/theme";

// Отдельного канала для уведомлений нет: подстраховка на случай, когда ни страница, ни чат не менялись.
const POLL_MS = 60_000;
const MAX_CHATS = 8;

const ICON_BUTTON = "relative grid h-10 w-10 shrink-0 place-items-center rounded-xl text-fg-soft hover:bg-muted hover:text-fg";
const COUNTER =
  "absolute -top-0.5 -right-0.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-brand px-1 text-[11px] font-semibold text-on-brand";
// На телефоне окно привязано к шапке, а не к кнопке: иначе оно не поместится по ширине.
const PANEL = "absolute top-full right-3 left-3 mt-2 overflow-hidden rounded-xl border border-line bg-surface shadow-lg sm:right-0 sm:left-auto sm:w-96";
const PANEL_BODY = "max-h-[min(28rem,calc(100dvh-7rem))] overflow-y-auto";

/** Открытое окно шапки закрывается щелчком мимо него и клавишей Esc. */
function useDismiss(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) close();
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, close]);
  return ref;
}

/** Последние диалоги. Список приходит из layout: по нему же считается значок в боковом меню. */
export function MessagesButton({
  conversations,
  failed,
  reload,
}: {
  conversations: Conversation[] | null;
  failed: boolean;
  reload: () => void;
}) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const ref = useDismiss(open, close);
  const unread = conversations?.filter((c) => c.unread > 0).length ?? 0;
  const label = unread > 0 ? `Сообщения: чатов с непрочитанными ${unread}` : "Сообщения";

  return (
    <div ref={ref} className="sm:relative">
      <button
        type="button"
        onClick={() => {
          if (!open) reload();
          setOpen(!open);
        }}
        className={ICON_BUTTON}
        aria-label={label}
        title={label}
        aria-expanded={open}
      >
        <MessageSquare size={20} strokeWidth={1.8} aria-hidden />
        {unread > 0 && <span className={COUNTER}>{unread > 99 ? "99+" : unread}</span>}
      </button>
      {open && (
        <div className={PANEL}>
          <div className="flex items-center justify-between border-b border-line px-5 py-3">
            <h2 className="font-semibold">Сообщения</h2>
            <Link href="/dashboard/chats" onClick={close} className="text-sm text-brand-text hover:underline">
              Все сообщения
            </Link>
          </div>
          <div className={PANEL_BODY}>
            {failed && !conversations && (
              <div className="p-4">
                <Alert>Не удалось загрузить сообщения</Alert>
              </div>
            )}
            {!conversations && !failed && <p className="px-5 py-6 text-sm text-fg-soft">Загрузка…</p>}
            {conversations?.length === 0 && <p className="px-5 py-6 text-sm text-fg-soft">Чатов пока нет</p>}
            {conversations?.slice(0, MAX_CHATS).map((c) => (
              <Link
                key={c.id}
                href={`/dashboard/chats?c=${c.id}`}
                onClick={close}
                className="flex items-start gap-3 border-b border-line/60 px-4 py-3 last:border-b-0 hover:bg-muted"
              >
                <Avatar name={c.title} group={c.kind === "group"} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="truncate text-sm font-medium">{c.title}</p>
                    {c.last_message && <span className="shrink-0 text-xs text-fg-soft">{shortTime(c.last_message.created_at)}</span>}
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm text-fg-soft">{conversationPreview(c)}</p>
                    {c.unread > 0 && (
                      <span className="grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-brand px-1.5 text-xs font-medium text-on-brand">
                        {c.unread}
                      </span>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function NotificationBell() {
  const pathname = usePathname();
  const { items, unread, error, load, markAllRead, markRead } = useNotifications();
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const ref = useDismiss(open, close);

  // Новые уведомления после перехода на другую страницу (первую загрузку делает useNotifications).
  const shownPath = useRef(pathname);
  useEffect(() => {
    if (shownPath.current === pathname) return;
    shownPath.current = pathname;
    void load();
  }, [load, pathname]);

  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  useRealtime((e) => {
    if (e.type === "message" || e.type === "refresh" || e.type === "assignment" || e.type === "reconnected") void load();
  });

  const label = unread > 0 ? `Уведомления: непрочитанных ${unread}` : "Уведомления";

  return (
    <div ref={ref} className="sm:relative">
      <button
        type="button"
        onClick={() => {
          if (!open) void load();
          setOpen(!open);
        }}
        className={ICON_BUTTON}
        aria-label={label}
        title={label}
        aria-expanded={open}
      >
        <Bell size={20} strokeWidth={1.8} aria-hidden />
        {unread > 0 && <span className={COUNTER}>{unread > 99 ? "99+" : unread}</span>}
      </button>
      {open && (
        <div className={PANEL}>
          <div className="flex items-center justify-between border-b border-line px-5 py-3">
            <h2 className="font-semibold">Уведомления</h2>
            {unread > 0 && (
              <button type="button" className="text-sm text-brand-text hover:underline" onClick={() => void markAllRead()}>
                Прочитать все
              </button>
            )}
          </div>
          <div className={PANEL_BODY}>
            {error && (
              <div className="p-4">
                <Alert>{error}</Alert>
              </div>
            )}
            {items === null && !error && <p className="px-5 py-6 text-sm text-fg-soft">Загрузка…</p>}
            {items?.length === 0 && <p className="px-5 py-6 text-sm text-fg-soft">Пока нет уведомлений</p>}
            <ul className="divide-y divide-line">
              {items?.map((n) => (
                <NotificationRow
                  key={n.id}
                  n={n}
                  onOpen={() => {
                    close();
                    if (!n.read_at) void markRead(n.id);
                  }}
                />
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

export function UserMenu() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const ref = useDismiss(open, close);
  if (!user) return null;
  const initials = user.full_name
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  const name = [user.first_name, user.last_name].filter(Boolean).join(" ") || user.full_name;
  const roles = user.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ");

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex h-12 items-center gap-2 rounded-xl py-1 pr-1.5 pl-1 hover:bg-muted"
        aria-label={`Профиль: ${name}, ${roles}`}
        aria-expanded={open}
      >
        <span className="grid h-10 w-10 shrink-0 place-items-center overflow-hidden rounded-full bg-brand/15 text-sm font-semibold text-brand-text">
          {user.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={user.avatar_url} alt="" className="h-full w-full object-cover" />
          ) : (
            initials
          )}
        </span>
        <span className="ml-1 hidden max-w-56 min-w-0 text-left sm:block">
          <span className="block truncate text-sm leading-[18px] font-medium">{name}</span>
          <span className="block truncate text-xs leading-[15px] font-bold text-fg-soft/60">{roles}</span>
        </span>
        <ChevronDown size={16} strokeWidth={2} aria-hidden className={`shrink-0 text-fg-soft transition-transform sm:ml-1 ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-64 rounded-xl border border-line bg-surface p-2 shadow-lg">
          <div className="px-3 py-2">
            <p className="truncate font-medium">{user.full_name}</p>
            <p className="truncate text-sm text-fg-soft">{user.email ?? user.login}</p>
            <p className="mt-1 text-xs text-fg-soft">{roles}</p>
          </div>
          <ThemeSwitch />
          <Link href="/dashboard/account" onClick={close} className="block rounded-lg px-3 py-2 text-sm hover:bg-muted">
            Личный кабинет
          </Link>
          <button onClick={signOut} className="w-full rounded-lg px-3 py-2 text-left text-sm text-danger hover:bg-muted">
            Выйти
          </button>
        </div>
      )}
    </div>
  );
}
