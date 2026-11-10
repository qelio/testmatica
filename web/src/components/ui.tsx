"use client";

import Link from "next/link";
import { forwardRef, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

import { LogoFull, LogoMark } from "@/components/logo-mark";

/** Логотип (решение №64). compact: на узких экранах остаётся только значок. live: геккон моргает и следит глазом за курсором. */
export function Logo({ className = "", compact = false, live = false }: { className?: string; compact?: boolean; live?: boolean }) {
  const link = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    if (!live || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const onMove = (e: PointerEvent) => {
      const root = link.current;
      // На узком экране виден только значок, поэтому берём тот глаз, у которого есть размер.
      const eye = [...(root?.querySelectorAll(".tm-gecko-eye") ?? [])].find((el) => el.getBoundingClientRect().width > 0);
      if (!root || !eye) return;
      const box = eye.getBoundingClientRect();
      const dx = e.clientX - (box.left + box.width / 2);
      const dy = e.clientY - (box.top + box.height / 2);
      const dist = Math.hypot(dx, dy) || 1;
      const reach = Math.min(1, dist / 160) * 11; // зрачок не выходит за край глаза
      // 9 и 6 — смещение зрачка от центра глаза в рисунке.
      root.style.setProperty("--gx", `${(dx / dist) * reach - 9}px`);
      root.style.setProperty("--gy", `${(dy / dist) * reach - 6}px`);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, [live]);
  return (
    <Link ref={link} href="/" aria-label="ТестМатика" className={`inline-flex items-center ${live ? "tm-live" : ""} ${className}`}>
      {compact && <LogoMark className="h-9 w-auto shrink-0 sm:hidden" />}
      <LogoFull className={`w-auto shrink-0 ${compact ? "hidden h-10 sm:block" : "h-[52px]"}`} />
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
    primary: "bg-brand text-on-brand hover:bg-brand-strong disabled:bg-brand/50",
    secondary: "border border-line bg-surface text-fg hover:bg-muted disabled:opacity-50",
    ghost: "text-fg-soft hover:bg-muted hover:text-fg disabled:opacity-50",
  }[variant];
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={`tm-btn tm-btn-${variant} inline-flex h-11 items-center justify-center gap-2 rounded-xl px-4 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed ${styles} ${className}`}
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
          <button type="button" onClick={resend} className="font-medium text-brand-text hover:underline">
            Отправить код ещё раз
          </button>
        )}
        {resendError && <p className="mt-2 text-danger">{resendError}</p>}
      </div>
    </form>
  );
}

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "brand" | "warn" | "ok";
  children: React.ReactNode;
}) {
  const styles = {
    neutral: "bg-muted text-fg-soft",
    brand: "bg-brand/10 text-brand-text",
    warn: "bg-tutor/10 text-tutor",
    ok: "bg-ok/10 text-ok",
  }[tone];
  return <span className={`tm-badge tm-badge-${tone} inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${styles}`}>{children}</span>;
}

/** Модальное окно на нативном <dialog>: фокус, Esc и затемнение фона — из коробки. */
export function Modal({
  open,
  onClose,
  title,
  children,
  wide = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  /** Шире обычного — когда в окне много кнопок в ряд. */
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  // Окно рендерится в конец <body> (портал): так форма внутри окна не окажется вложенной в форму страницы.
  const mounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open, mounted]);
  if (!mounted) return null;
  return createPortal(
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className={`m-auto w-[calc(100%-2rem)] ${wide ? "max-w-2xl" : "max-w-lg"} rounded-2xl border border-line bg-surface p-0 text-fg shadow-xl backdrop:bg-black/50`}
    >
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <h2 className="text-lg font-semibold">{title}</h2>
        <button onClick={onClose} aria-label="Закрыть" className="rounded-lg p-1.5 text-fg-soft hover:bg-muted">
          <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      <div className="p-5">{open && children}</div>
    </dialog>,
    document.body,
  );
}

export function Select({
  label,
  children,
  ...rest
}: React.SelectHTMLAttributes<HTMLSelectElement> & { label: string }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium">{label}</span>
      <select
        {...rest}
        className="h-11 w-full rounded-xl border border-line bg-surface px-3 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
      >
        {children}
      </select>
    </label>
  );
}

export function EmptyState({ title, text, action }: { title: string; text?: string; action?: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-line px-6 py-10 text-center">
      <p className="font-medium">{title}</p>
      {text && <p className="mx-auto mt-1 max-w-md text-sm text-fg-soft">{text}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Spinner() {
  return <span className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-brand border-r-transparent" />;
}
