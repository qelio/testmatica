"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Logo } from "@/components/ui";
import { useAuth } from "@/lib/auth";

const FEATURES = [
  { title: "Школьный учитель", text: "Классы, журнал, КТП, домашние задания и расписание в одном месте." },
  { title: "Репетитор", text: "Публичный профиль, заявки учеников, безопасная оплата через платформу." },
  { title: "Библиотека", text: "Материалы и задания с автопроверкой — включая задачи на Python." },
];

export default function Home() {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated") router.replace("/dashboard");
  }, [status, router]);

  return (
    <div className="flex flex-1 flex-col">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
        <Logo />
        <nav className="flex items-center gap-2">
          <Link href="/login" className="rounded-xl px-4 py-2 text-sm font-medium text-fg-soft hover:bg-muted hover:text-fg">
            Войти
          </Link>
          <Link href="/register" className="rounded-xl bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-strong">
            Регистрация
          </Link>
        </nav>
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col justify-center px-4 py-16 sm:px-6">
        <h1 className="max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
          Учите, учитесь и находите друг друга на одной платформе
        </h1>
        <p className="mt-5 max-w-2xl text-lg text-fg-soft">
          Тестматика объединяет инструменты школьного учителя, маркетплейс репетиторов и библиотеку знаний с
          заданиями.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link href="/register" className="rounded-xl bg-brand px-5 py-3 font-medium text-white hover:bg-brand-strong">
            Начать бесплатно
          </Link>
          <Link href="/login" className="rounded-xl border border-line bg-surface px-5 py-3 font-medium hover:bg-muted">
            У меня уже есть аккаунт
          </Link>
        </div>

        <div className="mt-16 grid gap-4 sm:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-2xl border border-line bg-surface p-5">
              <h2 className="font-semibold">{f.title}</h2>
              <p className="mt-2 text-sm text-fg-soft">{f.text}</p>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
