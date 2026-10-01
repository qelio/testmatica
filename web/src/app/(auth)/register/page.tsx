"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { EMPTY_NAME, NameFields } from "@/components/name-fields";
import { Alert, Button, CodeStep, Field } from "@/components/ui";
import { ApiError, identity } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { nextPath } from "@/lib/next-path";

type Role = "student" | "teacher";

const ROLE_OPTIONS: { value: Role; title: string; text: string }[] = [
  { value: "student", title: "Я ученик", text: "Занятия, задания и оценки от всех педагогов" },
  { value: "teacher", title: "Я педагог", text: "Школьный учитель и/или репетитор" },
];

export default function RegisterPage() {
  const router = useRouter();
  const { status, signIn } = useAuth();
  const [form, setForm] = useState({ ...EMPTY_NAME, email: "", password: "", role: "student" as Role, consent: false, terms: false });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [challenge, setChallenge] = useState<{ id: string; destination: string } | null>(null);

  // Уже вошли (например, по кнопке на главной) — сразу в кабинет.
  useEffect(() => {
    if (status === "authenticated") router.replace(nextPath());
  }, [status, router]);

  function update<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setFieldErrors((errs) => ({ ...errs, [key]: "" }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    setFieldErrors({});
    setLoading(true);
    try {
      const res = await identity.register({
        last_name: form.last_name,
        first_name: form.first_name,
        middle_name: form.middle_name,
        email: form.email,
        password: form.password,
        role: form.role,
        consent_pdn: form.consent,
        accept_terms: form.terms,
      });
      if ("access_token" in res) {
        // Почты пока нет — подтверждать нечего, сразу в кабинет.
        signIn(res);
        router.replace(nextPath());
        return;
      }
      setChallenge({ id: res.challenge_id, destination: res.destination });
    } catch (e) {
      if (e instanceof ApiError) {
        setFieldErrors(e.fieldErrors());
        setError(e.code === "validation_error" ? "Проверьте поля формы" : e.message);
      } else {
        setError("Что-то пошло не так");
      }
    } finally {
      setLoading(false);
    }
  }

  async function verify(code: string) {
    if (!challenge) return;
    setError(undefined);
    setLoading(true);
    try {
      signIn(await identity.verifyEmail(challenge.id, code));
      router.replace(nextPath());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Что-то пошло не так");
    } finally {
      setLoading(false);
    }
  }

  if (challenge) {
    return (
      <CodeStep
        title="Подтвердите email"
        submitLabel="Подтвердить"
        destination={challenge.destination}
        error={error}
        loading={loading}
        onSubmit={verify}
        onResend={async () => void (await identity.resendCode(challenge.id))}
      />
    );
  }

  return (
    <form className="space-y-5" onSubmit={submit} noValidate>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Регистрация</h1>
        <p className="mt-2 text-fg-soft">
          Уже есть аккаунт?{" "}
          <Link href="/login" className="font-medium text-brand hover:underline">
            Войдите
          </Link>
        </p>
      </div>
      {error && <Alert>{error}</Alert>}

      <fieldset>
        <legend className="mb-1.5 text-sm font-medium">Кто вы</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {ROLE_OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className={`cursor-pointer rounded-xl border p-3 transition-colors ${form.role === opt.value ? "border-brand bg-brand/5 ring-2 ring-brand/20" : "border-line hover:bg-muted"}`}
            >
              <input
                type="radio"
                name="role"
                value={opt.value}
                checked={form.role === opt.value}
                onChange={() => update("role", opt.value)}
                className="sr-only"
              />
              <span className="block font-medium">{opt.title}</span>
              <span className="mt-0.5 block text-xs text-fg-soft">{opt.text}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <NameFields
        value={{ last_name: form.last_name, first_name: form.first_name, middle_name: form.middle_name }}
        errors={fieldErrors}
        onChange={(n) => {
          setForm((f) => ({ ...f, ...n }));
          setFieldErrors((errs) => ({ ...errs, last_name: "", first_name: "", middle_name: "" }));
        }}
      />
      <Field
        label="Email"
        name="email"
        type="email"
        autoComplete="email"
        required
        value={form.email}
        error={fieldErrors.email}
        onChange={(e) => update("email", e.target.value)}
      />
      <Field
        label="Пароль"
        name="password"
        type="password"
        autoComplete="new-password"
        required
        hint="Не меньше 8 символов, буквы и цифры"
        value={form.password}
        error={fieldErrors.password}
        onChange={(e) => update("password", e.target.value)}
      />

      {/* Две отдельные галочки: согласие на обработку ПД не может быть частью другого документа (152-ФЗ). */}
      <div className="space-y-2.5">
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            checked={form.terms}
            onChange={(e) => update("terms", e.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 accent-brand"
          />
          <span className={fieldErrors.accept_terms ? "text-danger" : "text-fg-soft"}>
            Принимаю{" "}
            <Link href="/legal/terms" target="_blank" className="text-brand underline">
              пользовательское соглашение
            </Link>
          </span>
        </label>
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            checked={form.consent}
            onChange={(e) => update("consent", e.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 accent-brand"
          />
          <span className={fieldErrors.consent_pdn ? "text-danger" : "text-fg-soft"}>
            Даю{" "}
            <Link href="/legal/consent" target="_blank" className="text-brand underline">
              согласие на обработку персональных данных
            </Link>{" "}
            на условиях{" "}
            <Link href="/legal/privacy" target="_blank" className="text-brand underline">
              политики
            </Link>
          </span>
        </label>
        <p className="pl-7 text-xs text-fg-soft">Если вам меньше 14 лет, регистрацию и согласие оформляет родитель или законный представитель.</p>
      </div>

      <Button type="submit" className="w-full" loading={loading} disabled={!form.consent || !form.terms}>
        Зарегистрироваться
      </Button>
    </form>
  );
}
