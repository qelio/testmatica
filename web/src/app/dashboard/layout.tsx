"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Logo } from "@/components/ui";
import { chat } from "@/lib/api";
import { ROLE_LABELS, useAuth } from "@/lib/auth";
import { navFor } from "@/lib/navigation";
import { useRealtime } from "@/lib/realtime";

export default function DashboardLayout({ children }: LayoutProps<"/dashboard">) {
  const auth = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const unreadChats = useUnreadChats(auth.status === "authenticated", pathname);

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
  const badges = { chats: unreadChats };

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
          <Logo compact />
          <div className="flex-1" />
          <UserMenu />
        </div>
      </header>

      <div className="flex flex-1">
        <aside
          className={`${menuOpen ? "block" : "hidden"} fixed inset-x-0 top-16 bottom-0 z-10 overflow-y-auto border-r border-line bg-surface p-3 lg:static lg:block lg:w-64 lg:shrink-0`}
        >
          <nav className="space-y-1">
            {nav.map((item) =>
              item.ready ? (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMenuOpen(false)}
                  className={`block rounded-xl px-3 py-2.5 text-sm font-medium ${isActive(pathname, item.href) ? "bg-brand/10 text-brand" : "text-fg hover:bg-muted"}`}
                >
                  <span className="flex items-center justify-between">
                    {item.title}
                    {item.badge && badges[item.badge] > 0 && (
                      <span className="grid h-5 min-w-5 place-items-center rounded-full bg-brand px-1.5 text-xs text-white">
                        {badges[item.badge]}
                      </span>
                    )}
                  </span>
                </Link>
              ) : (
                <span
                  key={item.href}
                  className="flex cursor-default items-center justify-between rounded-xl px-3 py-2.5 text-sm text-fg-soft"
                >
                  {item.title}
                  <span className="rounded-md bg-muted px-1.5 py-0.5 text-[11px]">скоро</span>
                </span>
              ),
            )}
          </nav>
        </aside>
        <main className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
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
        className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand/15 text-sm font-semibold text-brand"
        aria-label="Профиль"
        aria-expanded={open}
      >
        {initials}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-64 rounded-xl border border-line bg-surface p-2 shadow-lg">
          <div className="px-3 py-2">
            <p className="truncate font-medium">{user.full_name}</p>
            <p className="truncate text-sm text-fg-soft">{user.email ?? user.login}</p>
            <p className="mt-1 text-xs text-fg-soft">{user.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ")}</p>
          </div>
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
