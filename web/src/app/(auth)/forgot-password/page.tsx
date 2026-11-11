"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Button, CodeStep, Field } from "@/components/ui";
import { ApiError, identity } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [challengeId, setChallengeId] = useState<string>();
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string>();
  const [passwordError, setPasswordError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const features = useLoad(() => identity.features(), []);

  async function requestCode(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    setLoading(true);
    try {
      setChallengeId((await identity.forgotPassword(email)).challenge_id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Что-то пошло не так");
    } finally {
      setLoading(false);
    }
  }

  async function reset(code: string) {
    if (!challengeId) return;
    setError(undefined);
    setPasswordError(undefined);
    setLoading(true);
    try {
      await identity.resetPassword(challengeId, code, password);
      setDone(true);
    } catch (e) {
      if (e instanceof ApiError && e.fieldErrors().new_password) {
        setPasswordError(e.fieldErrors().new_password);
      } else {
        setError(e instanceof ApiError ? e.message : "Что-то пошло не так");
      }
    } finally {
      setLoading(false);
    }
  }

  if (features.data?.email_codes === false) {
    // Почтового сервера пока нет (решение №29): код не отправить.
    return (
      <div className="space-y-5">
        <h1 className="text-2xl font-semibold tracking-tight">Восстановление пароля — скоро</h1>
        <p className="text-fg-soft">
          Письма с кодами пока не отправляются. Напишите на{" "}
          <a href="mailto:info@testmatica.ru" className="text-brand-text underline">
            info@testmatica.ru
          </a>{" "}
          с адреса, указанного при регистрации, — администратор выдаст временный пароль. Ученику, которого добавил педагог, новый пароль
          выдаёт педагог.
        </p>
        <Link href="/login" className="text-brand-text hover:underline">
          ← Ко входу
        </Link>
      </div>
    );
  }

  if (done) {
    return (
      <div className="space-y-5">
        <h1 className="text-2xl font-semibold tracking-tight">Пароль изменён</h1>
        <Alert kind="success">Все сеансы на других устройствах завершены. Войдите с новым паролем.</Alert>
        <Link
          href="/login"
          className="flex h-11 items-center justify-center rounded-xl bg-brand font-medium text-on-brand hover:bg-brand-strong"
        >
          Войти
        </Link>
      </div>
    );
  }

  if (challengeId) {
    return (
      <CodeStep
        title="Новый пароль"
        submitLabel="Сменить пароль"
        destination={email}
        error={error}
        loading={loading}
        onSubmit={reset}
        onResend={async () => void (await identity.resendCode(challengeId))}
      >
        <Field
          label="Новый пароль"
          name="new_password"
          type="password"
          autoComplete="new-password"
          required
          hint="Не меньше 8 символов, буквы и цифры"
          error={passwordError}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </CodeStep>
    );
  }

  return (
    <form className="space-y-5" onSubmit={requestCode}>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Восстановление пароля</h1>
        <p className="mt-2 text-fg-soft">Если аккаунт с таким email существует, мы отправим на него код.</p>
      </div>
      {error && <Alert>{error}</Alert>}
      <Field
        label="Email"
        name="email"
        type="email"
        autoComplete="email"
        autoFocus
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <Button type="submit" className="w-full" loading={loading}>
        Получить код
      </Button>
      <p className="text-center text-sm">
        <Link href="/login" className="text-brand-text hover:underline">
          Вернуться ко входу
        </Link>
      </p>
    </form>
  );
}
