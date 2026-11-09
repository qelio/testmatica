"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { LegalBar } from "@/components/legal-bar";
import { Logo } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ThemeToggle } from "@/lib/theme";

const LINKS = [
  { href: "/tutors", title: "Репетиторы" },
  { href: "/groups", title: "Группы" },
  { href: "/library", title: "Библиотека" },
  { href: "/news", title: "Новости" },
];

/** Шапка публичных страниц (главная, репетиторы, группы, новости) — открыты без регистрации.
 * wide — без ограничения ширины и отступов: у главной свои полноширинные разделы. */
export function PublicShell({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  const { status } = useAuth();
  const pathname = usePathname();
  return (
    <div className="flex flex-1 flex-col">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex h-18 max-w-6xl items-center gap-4 px-4 sm:px-6">
          <Logo compact />
          {/* Разделы — по центру между логотипом и переключателем темы; на узком экране прокручиваются. */}
          <nav className="flex min-w-0 flex-1 justify-start gap-5 overflow-x-auto sm:justify-center sm:gap-8">
            {LINKS.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className={`shrink-0 font-medium hover:text-brand-text ${pathname.startsWith(l.href) ? "" : "text-fg-soft"}`}
              >
                {l.title}
              </Link>
            ))}
          </nav>
          <ThemeToggle />
          {status === "authenticated" ? (
            <Link href="/dashboard" className="rounded-xl bg-brand px-4 py-2 text-sm font-medium text-on-brand hover:bg-brand-strong">
              В кабинет
            </Link>
          ) : (
            <>
              <Link href="/login" className="shrink-0 rounded-xl px-3 py-2 text-sm font-medium text-fg-soft hover:bg-muted hover:text-fg">
                Войти
              </Link>
              <Link
                href="/register"
                className="hidden shrink-0 rounded-xl bg-brand px-4 py-2 text-sm font-medium text-on-brand hover:bg-brand-strong sm:block"
              >
                Регистрация
              </Link>
            </>
          )}
        </div>
      </header>
      {wide ? (
        <main className="flex-1">{children}</main>
      ) : (
        <>
          <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">{children}</main>
          <LegalBar />
        </>
      )}
    </div>
  );
}
