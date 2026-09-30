"use client";

import { useState } from "react";

import { AvatarUploadButton } from "@/components/avatar-cropper";
import { Alert, Badge, Button, CodeStep, Field, Select, Spinner } from "@/components/ui";
import { identity, uploadFile, type UserInfo } from "@/lib/api";
import { ROLE_LABELS, useAuth } from "@/lib/auth";
import { errorText } from "@/lib/hooks";

// Часовые пояса России и соседей — чаще всего нужные; текущий пользователя добавляется, если его нет в списке.
const ZONES: [string, string][] = [
  ["Europe/Kaliningrad", "Калининград (UTC+2)"],
  ["Europe/Moscow", "Москва (UTC+3)"],
  ["Europe/Samara", "Самара (UTC+4)"],
  ["Asia/Yekaterinburg", "Екатеринбург (UTC+5)"],
  ["Asia/Omsk", "Омск (UTC+6)"],
  ["Asia/Novosibirsk", "Новосибирск (UTC+7)"],
  ["Asia/Krasnoyarsk", "Красноярск (UTC+7)"],
  ["Asia/Irkutsk", "Иркутск (UTC+8)"],
  ["Asia/Yakutsk", "Якутск (UTC+9)"],
  ["Asia/Vladivostok", "Владивосток (UTC+10)"],
  ["Asia/Magadan", "Магадан (UTC+11)"],
  ["Asia/Kamchatka", "Камчатка (UTC+12)"],
  ["Europe/Minsk", "Минск (UTC+3)"],
  ["Asia/Almaty", "Алматы (UTC+5)"],
];

/** Личный кабинет: фото, имя и часовой пояс, email, пароль, вход с кодом. Есть у всех ролей. */
export default function AccountPage() {
  const { user, setUser } = useAuth();
  if (!user) return <Spinner />;
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Личный кабинет</h1>
        <p className="mt-1 text-sm text-fg-soft">{user.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ")}</p>
      </div>
      {user.managed && (
        <Alert kind="info">
          Логин и пароль вам выдал педагог. Добавьте email — сможете сами восстановить пароль, а вход станет защищён кодом.
        </Alert>
      )}
      <AvatarBlock user={user} onChanged={setUser} />
      <ProfileBlock key={`${user.full_name}|${user.timezone}`} user={user} onChanged={setUser} />
      <EmailBlock user={user} onChanged={setUser} />
      <PasswordBlock />
      <TwoFactorBlock user={user} onChanged={setUser} />
    </div>
  );
}

function Block({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 rounded-2xl border border-line bg-surface p-5">
      <div>
        <h2 className="font-semibold">{title}</h2>
        {hint && <p className="text-sm text-fg-soft">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

function useAction() {
  const [error, setError] = useState<string>();
  const [info, setInfo] = useState<string>();
  const [busy, setBusy] = useState(false);
  async function run(action: () => Promise<string | void>) {
    setBusy(true);
    setError(undefined);
    setInfo(undefined);
    try {
      const message = await action();
      if (message) setInfo(message);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  const feedback = error ? <Alert>{error}</Alert> : info ? <Alert kind="success">{info}</Alert> : null;
  return { run, busy, feedback };
}

function AvatarBlock({ user, onChanged }: { user: UserInfo; onChanged: (u: UserInfo) => void }) {
  const { run, busy, feedback } = useAction();
  const initials = user.full_name
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return (
    <Block
      title="Фото профиля"
      hint={
        user.roles.includes("teacher")
          ? "Видно в шапке кабинета и в профиле репетитора. После выбора можно выбрать кадр и масштаб."
          : "Видно в шапке кабинета. После выбора можно выбрать кадр и масштаб."
      }
    >
      {feedback}
      <div className="flex flex-wrap items-center gap-4">
        <span className="grid h-20 w-20 shrink-0 place-items-center overflow-hidden rounded-full bg-brand/15 text-2xl font-semibold text-brand">
          {user.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={user.avatar_url} alt="" className="h-full w-full object-cover" />
          ) : (
            initials
          )}
        </span>
        <AvatarUploadButton
          label={busy ? "Загружаем…" : user.avatar_url ? "Заменить фото" : "Загрузить фото"}
          disabled={busy}
          onCropped={(file) =>
            void run(async () => {
              const up = await uploadFile(file, "avatar");
              onChanged(await identity.setAvatar(up.id));
              return "Фото обновлено";
            })
          }
        />
        {user.avatar_url && (
          <button
            type="button"
            className="text-sm text-fg-soft hover:text-danger"
            disabled={busy}
            onClick={() => run(async () => onChanged(await identity.setAvatar(null)))}
          >
            Убрать фото
          </button>
        )}
      </div>
    </Block>
  );
}

function ProfileBlock({ user, onChanged }: { user: UserInfo; onChanged: (u: UserInfo) => void }) {
  const [name, setName] = useState(user.full_name);
  const [tz, setTz] = useState(user.timezone);
  const { run, busy, feedback } = useAction();
  const zones = ZONES.some(([z]) => z === user.timezone) ? ZONES : [[user.timezone, user.timezone] as [string, string], ...ZONES];
  return (
    <Block title="Данные">
      {feedback}
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            onChanged(await identity.updateMe({ full_name: name, timezone: tz }));
            return "Сохранено";
          });
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Имя и фамилия" required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
          <Select label="Часовой пояс" value={tz} onChange={(e) => setTz(e.target.value)}>
            {zones.map(([z, title]) => (
              <option key={z} value={z}>
                {title}
              </option>
            ))}
          </Select>
        </div>
        {user.login && (
          <p className="text-sm text-fg-soft">
            Логин для входа: <b className="text-fg">{user.login}</b>
          </p>
        )}
        <Button type="submit" variant="secondary" loading={busy} disabled={name.trim() === user.full_name && tz === user.timezone}>
          Сохранить
        </Button>
      </form>
    </Block>
  );
}

function EmailBlock({ user, onChanged }: { user: UserInfo; onChanged: (u: UserInfo) => void }) {
  const [editing, setEditing] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [challenge, setChallenge] = useState<{
    challenge_id: string;
    destination: string;
  } | null>(null);
  const { run, busy, feedback } = useAction();
  const [codeError, setCodeError] = useState<string>();

  return (
    <Block title="Email" hint="На него приходят коды для входа и восстановления пароля.">
      {feedback}
      <p className="flex flex-wrap items-center gap-2">
        {user.email ? <b>{user.email}</b> : <span className="text-fg-soft">не указан</span>}
        {user.email && (user.email_verified ? <Badge tone="ok">подтверждён</Badge> : <Badge>не подтверждён</Badge>)}
        {user.email_codes === false && <Badge>смена email — скоро</Badge>}
        {!editing && !challenge && user.email_codes !== false && user.email && !user.email_verified && (
          // Зарегистрировался, пока почты не было, — подтвердить тот же адрес кодом.
          <Button
            variant="ghost"
            className="h-8"
            onClick={() => {
              setEmail(user.email ?? "");
              setEditing(true);
            }}
          >
            Подтвердить
          </Button>
        )}
        {!editing && !challenge && user.email_codes !== false && (
          <Button variant="ghost" className="h-8" onClick={() => setEditing(true)}>
            {user.email ? "Изменить" : "Добавить email"}
          </Button>
        )}
      </p>
      {challenge ? (
        <CodeStep
          destination={challenge.destination}
          title="Подтвердите новый email"
          submitLabel="Подтвердить"
          error={codeError}
          loading={busy}
          onSubmit={(code) =>
            run(async () => {
              setCodeError(undefined);
              try {
                onChanged(await identity.confirmEmail(challenge.challenge_id, code));
              } catch (e) {
                setCodeError(errorText(e));
                return;
              }
              setChallenge(null);
              setEditing(false);
              setEmail("");
              setPassword("");
              return "Email изменён";
            })
          }
          onResend={async () => {
            setChallenge(await identity.changeEmail(email, password));
          }}
        />
      ) : (
        editing && (
          <form
            className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
            onSubmit={(e) => {
              e.preventDefault();
              void run(async () => setChallenge(await identity.changeEmail(email, password)));
            }}
          >
            <Field label="Новый email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            <Field
              label="Текущий пароль"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <div className="flex gap-2">
              <Button type="submit" loading={busy}>
                Получить код
              </Button>
              <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
                Отмена
              </Button>
            </div>
          </form>
        )
      )}
    </Block>
  );
}

function PasswordBlock() {
  const [form, setForm] = useState({ current: "", next: "", repeat: "" });
  const { run, busy, feedback } = useAction();
  const mismatch = form.repeat.length > 0 && form.next !== form.repeat;
  return (
    <Block title="Пароль" hint="После смены пароля на других устройствах нужно будет войти заново.">
      {feedback}
      <form
        className="grid gap-3 sm:grid-cols-3"
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            await identity.changePassword(form.current, form.next);
            setForm({ current: "", next: "", repeat: "" });
            return "Пароль изменён";
          });
        }}
      >
        <Field
          label="Текущий пароль"
          type="password"
          required
          autoComplete="current-password"
          value={form.current}
          onChange={(e) => setForm({ ...form, current: e.target.value })}
        />
        <Field
          label="Новый пароль"
          type="password"
          required
          minLength={8}
          autoComplete="new-password"
          hint="Не короче 8 символов"
          value={form.next}
          onChange={(e) => setForm({ ...form, next: e.target.value })}
        />
        <Field
          label="Повторите"
          type="password"
          required
          autoComplete="new-password"
          error={mismatch ? "Пароли не совпадают" : undefined}
          value={form.repeat}
          onChange={(e) => setForm({ ...form, repeat: e.target.value })}
        />
        <div className="sm:col-span-3">
          <Button type="submit" variant="secondary" loading={busy} disabled={mismatch || !form.next}>
            Сменить пароль
          </Button>
        </div>
      </form>
    </Block>
  );
}

function TwoFactorBlock({ user, onChanged }: { user: UserInfo; onChanged: (u: UserInfo) => void }) {
  const enabled = user.two_factor_method !== null;
  const [password, setPassword] = useState("");
  const [asking, setAsking] = useState(false);
  const { run, busy, feedback } = useAction();
  const canEnable = !!user.email && !!user.email_verified;
  const locked = enabled && user.two_factor_required;

  return (
    <Block
      title="Вход с кодом (двухфакторная защита)"
      hint="При входе, кроме пароля, нужен код из письма — так аккаунт не украдут, даже если узнают пароль."
    >
      {feedback}
      {user.email_codes === false ? (
        // Почтового сервера пока нет (решение №29): коды не отправляются, вход — по паролю.
        <p className="flex flex-wrap items-center gap-2 text-sm text-fg-soft">
          <Badge tone="brand">скоро</Badge> Вход с кодом из письма появится, когда заработает почта. Пока вход — по паролю.
        </p>
      ) : (
      <p className="flex flex-wrap items-center gap-2">
        Сейчас: {enabled ? <Badge tone="ok">включён</Badge> : <Badge tone="warn">выключен</Badge>}
      </p>
      )}
      {user.email_codes === false ? null : locked ? (
        <p className="text-sm text-fg-soft">Модераторам и администраторам вход с кодом обязателен — выключить нельзя.</p>
      ) : !enabled && !canEnable ? (
        <p className="text-sm text-fg-soft">Чтобы включить, сначала добавьте и подтвердите email — на него будут приходить коды.</p>
      ) : asking ? (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              onChanged(await identity.setTwoFactor(!enabled, password));
              setPassword("");
              setAsking(false);
              return enabled ? "Вход с кодом выключен" : "Вход с кодом включён";
            });
          }}
        >
          <div className="min-w-60">
            <Field
              label="Подтвердите паролем"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <Button type="submit" loading={busy} variant={enabled ? "secondary" : "primary"}>
            {enabled ? "Выключить" : "Включить"}
          </Button>
          <Button type="button" variant="ghost" onClick={() => setAsking(false)}>
            Отмена
          </Button>
        </form>
      ) : (
        <div className="space-y-2">
          <Button variant={enabled ? "secondary" : "primary"} onClick={() => setAsking(true)}>
            {enabled ? "Выключить вход с кодом" : "Включить вход с кодом"}
          </Button>
          {enabled && <p className="text-xs text-fg-soft">Без кода войти сможет любой, кто узнает ваш пароль.</p>}
        </div>
      )}
    </Block>
  );
}
