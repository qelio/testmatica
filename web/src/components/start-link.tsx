"use client";

import Link from "next/link";

import { useAuth } from "@/lib/auth";

/** Главная кнопка лендинга. Главная рендерится на сервере и не знает, вошёл ли посетитель,
 * поэтому ссылку на регистрацию или вход уже вошедшему заменяем на кабинет. */
export function StartLink({ href, text, className }: { href: string; text: string; className: string }) {
  const { status } = useAuth();
  const toAuth = /^\/(register|login)(\/|\?|$)/.test(href);
  const authed = status === "authenticated" && toAuth;
  return (
    <Link href={authed ? "/dashboard" : href} className={className}>
      {authed ? "Перейти в кабинет" : text} →
    </Link>
  );
}
