"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Alert, Button, CodeStep, Field } from "@/components/ui";
import { ApiError, identity, type TwoFactorRequired } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { nextPath } from "@/lib/next-path";

type Step =
  | { kind: "credentials" }
  | { kind: "code"; challenge: TwoFactorRequired }
  | { kind: "verify-email"; challengeId: string; destination: string };

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}

/** ?login= — логин подставляется (QR-код с карточки ученика). */
function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { status, signIn } = useAuth();
  const [step, setStep] = useState<Step>({ kind: "credentials" });
  const [identifier, setIdentifier] = useState(() => params.get("login") ?? "");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (status === "authenticated") router.replace(nextPath());
  }, [status, router]);

  async function run(action: () => Promise<void>) {
    setError(undefined);
    setLoading(true);
    try {
      await action();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Что-то пошло не так");
      return e;
    } finally {
      setLoading(false);
    }
  }

  async function submitCredentials(e: React.FormEvent) {
    e.preventDefault();
    const err = await run(async () => {
      const result = await identity.login(identifier, password);
      if (result.status === "authenticated") {
        signIn(result);
      } else {
        setStep({ kind: "code", challenge: result });
      }
    });
    if (err instanceof ApiError && err.code === "email_not_verified") {
      setError(undefined);
      setStep({
        kind: "verify-email",
        challengeId: String(err.details.challenge_id),
        destination: String(err.details.destination),
      });
    }
  }

  if (step.kind === "code") {
    return (
      <CodeStep
        title="Подтвердите вход"
        submitLabel="Войти"
        destination={step.challenge.destination}
        error={error}
        loading={loading}
        onSubmit={(code) => run(async () => signIn(await identity.loginVerify(step.challenge.challenge_id, code)))}
        onResend={async () => void (await identity.resendCode(step.challenge.challenge_id))}
      />
    );
  }

  if (step.kind === "verify-email") {
    return (
      <CodeStep
        title="Подтвердите email"
        submitLabel="Подтвердить и войти"
        destination={step.destination}
        error={error}
        loading={loading}
        onSubmit={(code) =>
          run(async () => signIn(await identity.verifyEmail(step.challengeId, code)))
        }
        onResend={async () => void (await identity.resendCode(step.challengeId))}
      />
    );
  }

  return (
    <form className="space-y-5" onSubmit={submitCredentials}>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Вход</h1>
        <p className="mt-2 text-fg-soft">
          Нет аккаунта?{" "}
          <Link href="/register" className="font-medium text-brand-text hover:underline">
            Зарегистрируйтесь
          </Link>
        </p>
      </div>
      {error && <Alert>{error}</Alert>}
      <Field
        label="Email или логин"
        name="identifier"
        autoComplete="username"
        autoFocus
        required
        value={identifier}
        onChange={(e) => setIdentifier(e.target.value)}
      />
      <div>
        <Field
          label="Пароль"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Link href="/forgot-password" className="mt-2 inline-block text-sm text-brand-text hover:underline">
          Забыли пароль?
        </Link>
      </div>
      <Button type="submit" className="w-full" loading={loading}>
        Продолжить
      </Button>
    </form>
  );
}
