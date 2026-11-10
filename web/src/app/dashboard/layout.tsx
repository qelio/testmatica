"use client";

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ConsentGate } from "@/components/consent-gate";
import { MessagesButton, NotificationBell, UserMenu } from "@/components/header-menus";
import { HeaderSearch } from "@/components/header-search";
import { Logo } from "@/components/ui";
import { APP_VERSION } from "@/lib/version";
import { chat, CHAT_READ, type Conversation, support, type UserInfo } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { navFor } from "@/lib/navigation";
import { useRealtime } from "@/lib/realtime";

export default function DashboardLayout({ children }: LayoutProps<"/dashboard">) {
  const auth = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  // Свёрнутое меню (только иконки) — на широком экране; запоминается в браузере.
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const chats = useConversations(auth.status === "authenticated", pathname);
  const supportBadge = useSupportBadge(auth.status === "authenticated" ? auth.user : null, pathname);

  useEffect(() => {
    if (auth.status === "anonymous") router.replace("/login");
  }, [auth.status, router]);

  if (auth.status !== "authenticated") {
    return (
      <div className="grid flex-1 place-items-center">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-brand border-r-transparent" />
      </div>
    );
  }

  const { user } = auth;
  const nav = navFor(user.roles);
  const badges = { chats: chats.list?.filter((c) => c.unread > 0).length ?? 0, support: supportBadge };

  return (
    <div className="flex flex-1 flex-col">
      <header className="sticky top-0 z-20 border-b border-line bg-surface/90 backdrop-blur">
        <div className="flex h-18 items-center gap-2 px-3 sm:gap-3 sm:px-6">
          <button
            className="rounded-lg p-2 text-fg-soft hover:bg-muted lg:hidden"
            aria-label="Меню"
            onClick={() => setMenuOpen((v) => !v)}
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M3 5h14M3 10h14M3 15h14" strokeLinecap="round" />
            </svg>
          </button>
          <button
            className="hidden rounded-lg p-2 text-fg-soft hover:bg-muted lg:block"
            aria-label={collapsed ? "Развернуть меню" : "Свернуть меню"}
            title={collapsed ? "Развернуть меню" : "Свернуть меню"}
            aria-expanded={!collapsed}
            onClick={() => {
              setCollapsed(!collapsed);
              saveCollapsed(!collapsed);
            }}
          >
            {collapsed ? <PanelLeftOpen size={20} strokeWidth={1.8} /> : <PanelLeftClose size={20} strokeWidth={1.8} />}
          </button>
          <Logo compact className="ml-1 sm:ml-4" />
          <HeaderSearch roles={user.roles} />
          <div className="flex items-center">
            <MessagesButton conversations={chats.list} failed={chats.failed} reload={chats.reload} />
            <NotificationBell />
          </div>
          <UserMenu />
        </div>
      </header>

      <div className="flex flex-1">
        <aside
          className={`${menuOpen ? "block" : "hidden"} fixed inset-x-0 top-18 bottom-0 z-10 overflow-y-auto border-r border-line bg-surface p-3 lg:sticky lg:block lg:h-[calc(100dvh-4.5rem-1px)] lg:shrink-0 lg:transition-[width] ${collapsed ? "lg:w-[4.25rem] lg:px-2.5" : "lg:w-64"}`}
        >
          <nav>
            {(() => {
              let n = 0; // сквозной счётчик — цвета иконок идут по кругу через все группы
              return nav.map((section, si) => (
                <div key={section.title ?? si} className={si ? "mt-4" : ""}>
                  {section.title &&
                    (collapsed ? (
                      <hr className="mx-2 mb-2 hidden border-line lg:block" />
                    ) : null)}
                  {section.title && (
                    <p className={`mb-1 px-3 text-[11px] font-semibold tracking-wider text-fg-soft uppercase ${collapsed ? "lg:hidden" : ""}`}>
                      {section.title}
                    </p>
                  )}
                  <div className="space-y-1">
                    {section.items.map((item) => {
                      const i = n++;
                      const Icon = item.icon;
                      const count = item.badge ? badges[item.badge] : 0;
                      // В свёрнутом меню подпись — во всплывающей подсказке, счётчик — точкой на иконке.
                      const tip = collapsed ? `${item.title}${item.ready ? "" : " — скоро"}${count ? ` (${count})` : ""}` : undefined;
                      const icon = (
                        <span className={`relative grid h-7 w-7 shrink-0 place-items-center rounded-lg ${ICON_TONES[i % ICON_TONES.length]}`}>
                          <Icon size={16} strokeWidth={2.2} aria-hidden />
                          {collapsed && count > 0 && <span className="absolute -top-1 -right-1 hidden h-2 w-2 rounded-full bg-brand lg:block" />}
                        </span>
                      );
                      const label = <span className={`min-w-0 flex-1 truncate ${collapsed ? "lg:sr-only" : ""}`}>{item.title}</span>;
                      return item.ready ? (
                        <Link
                          key={item.href}
                          href={item.href}
                          title={tip}
                          onClick={() => setMenuOpen(false)}
                          className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium ${collapsed ? "lg:justify-center lg:px-0" : ""} ${isActive(pathname, item.href) ? "bg-brand/10 text-brand-text" : "text-fg hover:bg-muted"}`}
                        >
                          {icon}
                          {label}
                          {count > 0 && (
                            <span className={`grid h-5 min-w-5 place-items-center rounded-full bg-brand px-1.5 text-xs text-on-brand ${collapsed ? "lg:hidden" : ""}`}>
                              {count}
                            </span>
                          )}
                        </Link>
                      ) : (
                        <span
                          key={item.href}
                          title={tip}
                          className={`flex cursor-default items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-fg-soft ${collapsed ? "lg:justify-center lg:px-0 lg:opacity-60" : ""}`}
                        >
                          {icon}
                          {label}
                          <span className={`rounded-md bg-muted px-1.5 py-0.5 text-[11px] ${collapsed ? "lg:hidden" : ""}`}>скоро</span>
                        </span>
                      );
                    })}
                  </div>
                </div>
              ));
            })()}
          </nav>
          {APP_VERSION && <p className={`mt-4 px-3 text-xs text-fg-soft ${collapsed ? "lg:hidden" : ""}`}>Версия {APP_VERSION}</p>}
        </aside>
        <main className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8">{children}</main>
        <ConsentGate />
      </div>
    </div>
  );
}

const COLLAPSED_KEY = "tm:sidebar-collapsed";

// Цветные плашки иконок меню — по кругу; классы целиком, чтобы Tailwind их нашёл.
const ICON_TONES = [
  "bg-brand/15 text-brand-text",
  "bg-pink/15 text-pink",
  "bg-sky/15 text-sky",
  "bg-sun/20 text-sun",
  "bg-mint/15 text-mint",
  "bg-grape/15 text-grape",
];

function readCollapsed(): boolean {
  try {
    return typeof window !== "undefined" && window.localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

function saveCollapsed(value: boolean): void {
  try {
    window.localStorage.setItem(COLLAPSED_KEY, value ? "1" : "0");
  } catch {
    /* хранилище недоступно — просто не запомним */
  }
}

/** Чаты пользователя: для значка в меню и окна сообщений в шапке. */
function useConversations(enabled: boolean, pathname: string) {
  const [list, setList] = useState<Conversation[] | null>(null);
  const [failed, setFailed] = useState(false);
  const reload = useCallback(() => {
    if (!enabled) return;
    chat
      .conversations()
      .then((data) => {
        setList(data);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, [enabled]);
  useEffect(() => {
    // Обновляем при смене страницы (например, после чтения чата).
    reload();
  }, [reload, pathname]);
  useEffect(() => {
    window.addEventListener(CHAT_READ, reload);
    return () => window.removeEventListener(CHAT_READ, reload);
  }, [reload]);
  useRealtime((e) => {
    if (e.type === "message" || e.type === "deleted" || e.type === "refresh" || e.type === "reconnected") reload();
  });
  return { list, failed, reload };
}

/** Значок «Поддержки»: у поддержки — сколько обращений ждут ответа, у пользователя — сколько с непрочитанным ответом. */
function useSupportBadge(user: UserInfo | null, pathname: string): number {
  const [count, setCount] = useState(0);
  const staff = !!user?.roles.some((r) => r === "moderator" || r === "admin");
  const enabled = !!user;
  const refresh = useCallback(() => {
    if (!enabled) return;
    (staff ? support.counts().then((c) => c.open) : support.mine().then((list) => list.filter((t) => t.unread > 0).length))
      .then(setCount)
      .catch(() => {});
  }, [enabled, staff]);
  useEffect(() => {
    refresh();
  }, [refresh, pathname]);
  useRealtime((e) => {
    if (e.type === "message" || e.type === "refresh" || e.type === "reconnected") refresh();
  });
  return count;
}

function isActive(pathname: string, href: string): boolean {
  return pathname === href || (href !== "/dashboard" && pathname.startsWith(`${href}/`));
}
