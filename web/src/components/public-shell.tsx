"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

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

/** Разделы главной: лаймовая плашка плавно перетекает под пункт, на который навели. */
function PillNav() {
  const [pill, setPill] = useState({ left: 0, width: 0 });
  const [hovered, setHovered] = useState<number | null>(null);
  const show = (i: number, el: HTMLElement) => {
    setPill({ left: el.offsetLeft, width: el.offsetWidth });
    setHovered(i);
  };
  return (
    <nav className="relative hidden min-w-0 flex-1 justify-center min-[56.25rem]:flex" onMouseLeave={() => setHovered(null)} onBlur={() => setHovered(null)}>
      <div className="relative flex shrink-0">
        <span aria-hidden className={`absolute inset-y-0 rounded-full bg-lime transition-all duration-300 ease-out ${hovered === null ? "opacity-0" : "opacity-100"}`} style={pill} />
        {LINKS.map((l, i) => (
          <Link
            key={l.href}
            href={l.href}
            onMouseEnter={(e) => show(i, e.currentTarget)}
            onFocus={(e) => show(i, e.currentTarget)}
            className={`relative shrink-0 rounded-full px-2.5 py-2 font-medium transition-colors lg:px-4 ${hovered === i ? "text-logo-ink" : "text-fg-soft"}`}
          >
            {l.title}
          </Link>
        ))}
      </div>
    </nav>
  );
}

/** Меню главной на узких экранах: кнопка в капсуле и список под ней. */
function BurgerMenu({ guest }: { guest: boolean }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const Icon = open ? X : Menu;
  return (
    <div ref={root} className="min-[56.25rem]:hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-label={open ? "Закрыть меню" : "Открыть меню"}
        aria-expanded={open}
        className="grid h-10 w-10 place-items-center rounded-full text-fg hover:bg-muted"
      >
        <Icon size={22} strokeWidth={2} aria-hidden />
      </button>
      {open && (
        <nav className="tm-pop absolute inset-x-0 top-full mt-2 origin-top-right rounded-3xl border border-line bg-surface p-2 shadow-xl sm:left-auto sm:w-72">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} onClick={() => setOpen(false)} className="block rounded-2xl px-4 py-3 text-lg font-medium hover:bg-lime hover:text-logo-ink">
              {l.title}
            </Link>
          ))}
          {guest && (
            <Link href="/register" onClick={() => setOpen(false)} className="mt-1 block rounded-2xl bg-brand px-4 py-3 text-center text-lg font-semibold text-on-brand sm:hidden">
              Регистрация
            </Link>
          )}
        </nav>
      )}
    </div>
  );
}

/** Шапка публичных страниц (главная, репетиторы, группы, новости) — открыты без регистрации.
 * wide — главная: свои полноширинные разделы и шапка-капсула над первым экраном. Капсула не закреплена и уезжает вместе со страницей. */
export function PublicShell({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  const { status } = useAuth();
  const pathname = usePathname();
  return (
    <div className={`flex flex-1 flex-col ${wide ? "relative" : ""}`}>
      {wide && <span aria-hidden className="tm-scroll-line fixed inset-x-0 top-0 z-50 h-[3px]" />}
      <header className={wide ? "absolute inset-x-0 top-4 z-20 mx-auto max-w-[1446px] px-3 sm:px-6 lg:px-7" : "border-b border-line bg-surface"}>
        <div
          className={`flex items-center ${wide ? "h-[68px] gap-1.5 rounded-full border border-line/70 bg-surface/70 px-4 shadow-lg shadow-brand/10 backdrop-blur-xl lg:gap-4 lg:px-6" : "mx-auto h-18 max-w-6xl gap-4 px-4 sm:px-6"}`}
        >
          <Logo compact live={wide} />
          {/* Разделы — по центру между логотипом и переключателем темы; на узком экране прокручиваются. */}
          {wide ? (
            <>
              <PillNav />
              <span className="flex-1 min-[56.25rem]:hidden" />
            </>
          ) : (
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
          )}
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
          {wide && <BurgerMenu guest={status !== "authenticated"} />}
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
