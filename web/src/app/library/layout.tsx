"use client";

import Link from "next/link";

import { Logo } from "@/components/ui";
import { useAuth } from "@/lib/auth";

/** Публичная библиотека — доступна без регистрации (ТЗ, раздел 9). */
export default function PublicLibraryLayout({ children }: LayoutProps<"/library">) {
  const { status } = useAuth();
  return (
    <div className="flex flex-1 flex-col">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 sm:px-6">
          <Logo compact />
          <Link href="/library" className="font-medium hover:text-brand">
            Библиотека
          </Link>
          <div className="flex-1" />
          {status === "authenticated" ? (
            <Link href="/dashboard/library" className="rounded-xl bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-strong">
              В кабинет
            </Link>
          ) : (
            <Link href="/login" className="rounded-xl px-4 py-2 text-sm font-medium text-fg-soft hover:bg-muted hover:text-fg">
              Войти
            </Link>
          )}
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">{children}</main>
    </div>
  );
}
