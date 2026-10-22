"use client";

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ConsentGate } from "@/components/consent-gate";
import { Logo } from "@/components/ui";
import { chat, support, type UserInfo } from "@/lib/api";
import { ROLE_LABELS, useAuth } from "@/lib/auth";
import { navFor } from "@/lib/navigation";
import { useRealtime } from "@/lib/realtime";
import { ThemeToggle } from "@/lib/theme";

export default function DashboardLayout({ children }: LayoutProps<"/dashboard">) {
  const auth = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  // Свёрнутое меню (только иконки) — на широком экране; запоминается в браузере.
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const unreadChats = useUnreadChats(auth.status === "authenticated", pathname);
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
  const badges = { chats: unreadChats, support: supportBadge };

  return (
    <div className="flex flex-1 flex-col">
      <header className="sticky top-0 z-20 border-b border-line bg-surface/90 backdrop-blur">
        <div className="flex h-16 items-center gap-2 px-3 sm:gap-3 sm:px-6">
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
          <Logo compact />
          <div className="flex-1" />
          <ThemeToggle />
          <UserMenu />
        </div>
      </header>

      <div className="flex flex-1">
        <aside
          className={`${menuOpen ? "block" : "hidden"} fixed inset-x-0 top-16 bottom-0 z-10 overflow-y-auto border-r border-line bg-surface p-3 lg:sticky lg:block lg:h-[calc(100dvh-4rem-1px)] lg:shrink-0 lg:transition-[width] ${collapsed ? "lg:w-[4.25rem] lg:px-2.5" : "lg:w-64"}`}
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
                          className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium ${collapsed ? "lg:justify-center lg:px-0" : ""} ${isActive(pathname, item.href) ? "bg-brand/10 text-brand" : "text-fg hover:bg-muted"}`}
                        >
                          {icon}
                          {label}
                          {count > 0 && (
                            <span className={`grid h-5 min-w-5 place-items-center rounded-full bg-brand px-1.5 text-xs text-white ${collapsed ? "lg:hidden" : ""}`}>
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
  "bg-brand/15 text-brand",
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

/** Сколько чатов с непрочитанными сообщениями — для значка в меню. */
function useUnreadChats(enabled: boolean, pathname: string): number {
  const [count, setCount] = useState(0);
  const refresh = useCallback(() => {
    if (!enabled) return;
    chat
      .conversations()
      .then((list) => setCount(list.filter((c) => c.unread > 0).length))
      .catch(() => {});
  }, [enabled]);
  useEffect(() => {
    // Обновляем при смене страницы (например, после чтения чата).
    refresh();
  }, [refresh, pathname]);
  useRealtime((e) => {
    if (e.type === "message" || e.type === "reconnected") refresh();
  });
  return count;
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

function UserMenu() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  if (!user) return null;
  const initials = user.full_name
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-full bg-brand/15 text-sm font-semibold text-brand"
        aria-label="Профиль"
        aria-expanded={open}
      >
        {user.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={user.avatar_url} alt="" className="h-full w-full object-cover" />
        ) : (
          initials
        )}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-64 rounded-xl border border-line bg-surface p-2 shadow-lg">
          <div className="px-3 py-2">
            <p className="truncate font-medium">{user.full_name}</p>
            <p className="truncate text-sm text-fg-soft">{user.email ?? user.login}</p>
            <p className="mt-1 text-xs text-fg-soft">{user.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ")}</p>
          </div>
          <Link
            href="/dashboard/account"
            onClick={() => setOpen(false)}
            className="block rounded-lg px-3 py-2 text-sm hover:bg-muted"
          >
            Личный кабинет
          </Link>
          <button
            onClick={signOut}
            className="w-full rounded-lg px-3 py-2 text-left text-sm text-danger hover:bg-muted"
          >
            Выйти
          </button>
        </div>
      )}
    </div>
  );
}
