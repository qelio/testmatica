"use client";

import { ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Alert, Button } from "@/components/ui";
import { identity } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorText } from "@/lib/hooks";

/** Окно согласия при входе: ученик, которому аккаунт создал педагог, или новая редакция документов.
 * Закрыть нельзя — без согласия пользоваться платформой нельзя (152-ФЗ); можно только выйти. */
export function ConsentGate() {
  const { user, setUser, signOut } = useAuth();
  const [terms, setTerms] = useState(false);
  const [pdn, setPdn] = useState(false);
  const [age, setAge] = useState<"adult" | "parent" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  if (!user?.consent_required) return null;
  const student = user.roles.includes("student") && user.roles.length === 1;
  const ready = terms && pdn && (!student || age !== null);

  async function accept() {
    setBusy(true);
    setError(undefined);
    try {
      setUser(await identity.giveConsents(age === "parent"));
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  const doc = (href: string, text: string) => (
    <Link href={href} target="_blank" className="text-brand-text underline">
      {text}
    </Link>
  );

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="consent-title"
    >
      <div className="w-full max-w-lg space-y-4 rounded-2xl border border-line bg-surface p-6 shadow-xl">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-brand/15 text-brand-text">
            <ShieldCheck size={24} aria-hidden />
          </span>
          <h2 id="consent-title" className="text-lg font-semibold">
            {user.managed ? "Добро пожаловать в ТестМатику!" : "Документы обновились"}
          </h2>
        </div>
        <p className="text-sm text-fg-soft">
          {user.managed
            ? "Аккаунт тебе создал педагог. Прежде чем начать, нужно принять правила платформы и дать согласие на обработку данных — оценок, ответов, сообщений."
            : "Чтобы продолжить, примите пользовательское соглашение и дайте согласие на обработку персональных данных."}
        </p>
        {error && <Alert>{error}</Alert>}
        {student && (
          <fieldset className="space-y-2 rounded-xl bg-muted/60 p-3 text-sm">
            <legend className="sr-only">Возраст</legend>
            <label className="flex items-start gap-2.5">
              <input type="radio" name="age" checked={age === "adult"} onChange={() => setAge("adult")} className="mt-0.5 accent-brand" />
              Мне уже есть 14 лет — соглашаюсь сам(а)
            </label>
            <label className="flex items-start gap-2.5">
              <input type="radio" name="age" checked={age === "parent"} onChange={() => setAge("parent")} className="mt-0.5 accent-brand" />
              Мне меньше 14 лет — согласие даёт мой родитель (законный представитель), он(а) прочитал(а) документы
            </label>
          </fieldset>
        )}
        <label className="flex items-start gap-3 text-sm">
          <input type="checkbox" checked={terms} onChange={(e) => setTerms(e.target.checked)} className="mt-0.5 h-4 w-4 shrink-0 accent-brand" />
          <span>Принимаю {doc("/legal/terms", "пользовательское соглашение")}</span>
        </label>
        <label className="flex items-start gap-3 text-sm">
          <input type="checkbox" checked={pdn} onChange={(e) => setPdn(e.target.checked)} className="mt-0.5 h-4 w-4 shrink-0 accent-brand" />
          <span>
            Даю {doc("/legal/consent", "согласие на обработку персональных данных")} на условиях {doc("/legal/privacy", "политики")}
          </span>
        </label>
        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <button type="button" onClick={() => signOut()} className="text-sm text-fg-soft hover:text-fg">
            Выйти
          </button>
          <Button onClick={accept} loading={busy} disabled={!ready}>
            Продолжить
          </Button>
        </div>
      </div>
    </div>
  );
}
