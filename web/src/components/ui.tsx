"use client";

import Link from "next/link";
import { forwardRef, useEffect, useState } from "react";

export function Logo({ className = "", compact = false }: { className?: string; compact?: boolean }) {
  return (
    <Link href="/" className={`inline-flex items-center gap-2 font-semibold tracking-tight ${className}`}>
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-brand text-sm font-bold text-white">
        Т
      </span>
      {/* compact: на узких экранах остаётся только значок */}
      <span className={`text-lg ${compact ? "hidden sm:inline" : ""}`}>Тестматика</span>
    </Link>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-line bg-surface p-6 shadow-sm sm:p-8 ${className}`}>{children}</div>
  );
}

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  loading?: boolean;
};

export function Button({ variant = "primary", loading, disabled, className = "", children, ...rest }: ButtonProps) {
  const styles = {
    primary: "bg-brand text-white hover:bg-brand-strong disabled:bg-brand/50",
    secondary: "border border-line bg-surface text-fg hover:bg-muted disabled:opacity-50",
    ghost: "text-fg-soft hover:bg-muted hover:text-fg disabled:opacity-50",
  }[variant];
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={`inline-flex h-11 items-center justify-center gap-2 rounded-xl px-4 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed ${styles} ${className}`}
    >
      {loading && (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent" />
      )}
      {children}
    </button>
  );
}

type FieldProps = React.InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string; hint?: string };

export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(
  { label, error, hint, id, className = "", ...rest },
  ref,
) {
  const inputId = id ?? rest.name;
  return (
    <label htmlFor={inputId} className="block">
      <span className="mb-1.5 block text-sm font-medium text-fg">{label}</span>
      <input
        ref={ref}
        id={inputId}
        aria-invalid={!!error}
        {...rest}
        className={`h-11 w-full rounded-xl border bg-surface px-3.5 text-[15px] text-fg outline-none transition-colors placeholder:text-fg-soft/70 focus:border-brand focus:ring-2 focus:ring-brand/20 ${error ? "border-danger" : "border-line"} ${className}`}
      />
      {error ? (
        <span className="mt-1.5 block text-sm text-danger">{error}</span>
      ) : hint ? (
        <span className="mt-1.5 block text-sm text-fg-soft">{hint}</span>
      ) : null}
    </label>
  );
});

export function Alert({ kind = "error", children }: { kind?: "error" | "info" | "success"; children: React.ReactNode }) {
  const styles = {
    error: "border-danger/30 bg-danger/10 text-danger",
    info: "border-brand/30 bg-brand/10 text-fg",
    success: "border-ok/30 bg-ok/10 text-fg",
  }[kind];
  return (
    <div role={kind === "error" ? "alert" : "status"} className={`rounded-xl border px-4 py-3 text-sm ${styles}`}>
      {children}
    </div>
  );
}

/** Шаг ввода 6-значного кода из письма с кнопкой повторной отправки. */
export function CodeStep({
  destination,
  title,
  submitLabel,
  error,
  loading,
  onSubmit,
  onResend,
  children,
}: {
  destination: string;
  title: string;
  submitLabel: string;
  error?: string;
  loading?: boolean;
  onSubmit: (code: string) => void;
  onResend: () => Promise<void>;
  children?: React.ReactNode;
}) {
  const [code, setCode] = useState("");
  const [cooldown, setCooldown] = useState(60);
  const [resendError, setResendError] = useState<string>();
  const [resent, setResent] = useState(false);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  async function resend() {
    setResendError(undefined);
    try {
      await onResend();
      setResent(true);
      setCooldown(60);
    } catch (e) {
      setResendError(e instanceof Error ? e.message : "Не удалось отправить код");
    }
  }

  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(code);
      }}
    >
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-2 text-fg-soft">
          Мы отправили 6-значный код на <span className="font-medium text-fg">{destination}</span>
        </p>
      </div>
      {error && <Alert>{error}</Alert>}
      {resent && !error && <Alert kind="success">Новый код отправлен</Alert>}
      <Field
        label="Код из письма"
        name="code"
        inputMode="numeric"
        autoComplete="one-time-code"
        autoFocus
        maxLength={6}
        pattern="\d{6}"
        placeholder="000000"
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
        className="text-center font-mono text-2xl tracking-[0.5em]"
      />
      {children}
      <Button type="submit" className="w-full" loading={loading} disabled={code.length !== 6}>
        {submitLabel}
      </Button>
      <div className="text-center text-sm text-fg-soft">
        {cooldown > 0 ? (
          <span>Отправить код повторно можно через {cooldown} с</span>
        ) : (
          <button type="button" onClick={resend} className="font-medium text-brand hover:underline">
            Отправить код ещё раз
          </button>
        )}
        {resendError && <p className="mt-2 text-danger">{resendError}</p>}
      </div>
    </form>
  );
}
