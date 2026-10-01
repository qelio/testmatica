"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { History } from "@/components/audit-list";
import { NameFields, nameOf } from "@/components/name-fields";
import { ReasonModal } from "@/components/reviews";
import { Alert, Badge, Button, Field, Modal, Spinner } from "@/components/ui";
import { admin, type AdminUser } from "@/lib/api";
import { USER_STATUS } from "@/lib/admin";
import { ROLE_LABELS, useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/dates";
import { fmtRub } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

/** Карточка пользователя: данные, роли, блокировка, удаление, сброс пароля, подписка, история действий. */
export default function UserPage() {
  const { id } = useParams<{ id: string }>();
  const user = useLoad(() => admin.user(id), [id]);
  if (user.error) return <Alert>{user.error}</Alert>;
  if (!user.data) return <Spinner />;
  return <UserCard key={user.data.id} initial={user.data} />;
}

function UserCard({ initial }: { initial: AdminUser }) {
  const { user: me } = useAuth();
  const [u, setU] = useState(initial);
  const [error, setError] = useState<string>();
  const [info, setInfo] = useState<string>();
  const [modal, setModal] = useState<"ban" | "delete" | null>(null);
  const [password, setPassword] = useState<string | null>(null);
  const self = me?.id === u.id;
  const st = USER_STATUS[u.status];

  async function act(action: () => Promise<AdminUser | void>, message?: string) {
    setError(undefined);
    setInfo(undefined);
    try {
      const next = await action();
      if (next) setU(next);
      if (message) setInfo(message);
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <Link href="/dashboard/users" className="text-sm text-fg-soft hover:text-fg">
        ← Пользователи
      </Link>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="min-w-0 flex-1 text-2xl font-semibold tracking-tight">{u.full_name}</h1>
        <Badge tone={st.tone}>{st.text}</Badge>
      </div>
      {error && <Alert>{error}</Alert>}
      {info && <Alert kind="success">{info}</Alert>}
      {u.status_reason && (u.status === "banned" || u.status === "deleted") && (
        <Alert kind="info">
          Причина: {u.status_reason}
          {u.restore_until && ` · восстановить можно до ${fmtDateTime(u.restore_until)}, потом данные обезличатся`}
        </Alert>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="space-y-3 rounded-2xl border border-line bg-surface p-5 text-sm">
          <h2 className="font-semibold">Аккаунт</h2>
          <dl className="grid grid-cols-[10rem_1fr] gap-x-3 gap-y-1.5">
            <dt className="text-fg-soft">Email</dt>
            <dd>{u.email ?? "—"} {u.email && (u.email_verified ? <Badge tone="ok">подтверждён</Badge> : <Badge>не подтверждён</Badge>)}</dd>
            <dt className="text-fg-soft">Логин</dt>
            <dd>{u.login ?? "—"}</dd>
            <dt className="text-fg-soft">Вход с кодом</dt>
            <dd>{u.two_factor_method === "email" ? "по email" : u.two_factor_method === "phone" ? "по телефону" : "без второго фактора"}</dd>
            <dt className="text-fg-soft">Регистрация</dt>
            <dd>{fmtDateTime(u.created_at)}</dd>
            <dt className="text-fg-soft">Был на сайте</dt>
            <dd>{u.last_seen_at ? fmtDateTime(u.last_seen_at) : "—"}</dd>
            {u.managed_by_teacher_id && (
              <>
                <dt className="text-fg-soft">Аккаунт создал</dt>
                <dd>
                  <Link href={`/dashboard/users/${u.managed_by_teacher_id}`} className="text-brand hover:underline">
                    педагог
                  </Link>
                </dd>
              </>
            )}
          </dl>
          <div className="flex flex-wrap gap-2 border-t border-line pt-3">
            {u.status === "banned" ? (
              <Button variant="secondary" onClick={() => act(() => admin.unban(u.id), "Разблокирован")}>
                Разблокировать
              </Button>
            ) : (
              u.status !== "deleted" && (
                <Button variant="secondary" disabled={self} onClick={() => setModal("ban")}>
                  Заблокировать
                </Button>
              )
            )}
            {u.status === "deleted" ? (
              u.restore_until && (
                <Button variant="secondary" onClick={() => act(() => admin.restore(u.id), "Аккаунт восстановлен")}>
                  Восстановить
                </Button>
              )
            ) : (
              <Button variant="ghost" className="text-danger" disabled={self} onClick={() => setModal("delete")}>
                Удалить
              </Button>
            )}
            {u.status !== "deleted" && u.status !== "banned" && (
              <Button
                variant="ghost"
                onClick={() =>
                  window.confirm("Сбросить пароль? Все сессии пользователя завершатся, вы получите временный пароль.") &&
                  act(async () => setPassword((await admin.resetPassword(u.id)).password))
                }
              >
                Сбросить пароль
              </Button>
            )}
          </div>
        </section>

        <div className="space-y-4">
          <EditForm u={u} onSaved={(next) => act(async () => next, "Сохранено")} />
          <RolesForm u={u} self={self} onSaved={(next) => act(async () => next, "Роли обновлены. Они вступят в силу при следующем обновлении сессии (до 15 минут).")} />
          {u.roles.includes("teacher") && <GrantForm userId={u.id} onDone={(m) => setInfo(m)} />}
        </div>
      </div>

      {u.roles.includes("teacher") && <Payments userId={u.id} />}
      <History userId={u.id} />

      <ReasonModal
        open={modal === "ban"}
        title="Заблокировать пользователя"
        label="Причина (видна администраторам)"
        hint="Все сессии завершатся, войти будет нельзя. Разблокировать можно в любой момент."
        submit="Заблокировать"
        onClose={() => setModal(null)}
        onSubmit={async (reason) => {
          setU(await admin.ban(u.id, reason));
          setModal(null);
        }}
      />
      <ReasonModal
        open={modal === "delete"}
        title="Удалить аккаунт"
        label="Причина"
        hint="30 дней аккаунт можно восстановить. Потом имя, email и телефон обезличатся; отзывы и материалы останутся от «Удалённого пользователя»."
        submit="Удалить"
        onClose={() => setModal(null)}
        onSubmit={async (reason) => {
          setU(await admin.remove(u.id, reason));
          setModal(null);
        }}
      />
      <Modal open={password !== null} onClose={() => setPassword(null)} title="Временный пароль">
        <div className="space-y-3">
          <p className="text-sm">Передайте пароль пользователю — он показывается только сейчас. После входа его стоит сменить.</p>
          <p className="rounded-xl bg-muted p-3 text-center font-mono text-lg select-all">{password}</p>
          <Button className="w-full" onClick={() => setPassword(null)}>
            Готово
          </Button>
        </div>
      </Modal>
    </div>
  );
}

function EditForm({ u, onSaved }: { u: AdminUser; onSaved: (u: AdminUser) => void }) {
  const [form, setForm] = useState({ name: nameOf(u), email: u.email ?? "", login: u.login ?? "" });
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="space-y-3 rounded-2xl border border-line bg-surface p-5"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(undefined);
        try {
          onSaved(await admin.editUser(u.id, {
            name: form.name,
            ...(form.email && form.email !== u.email ? { email: form.email } : {}),
            ...(form.login && form.login !== u.login ? { login: form.login } : {}),
          }));
        } catch (err) {
          setError(errorText(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      <h2 className="font-semibold">Данные</h2>
      {error && <Alert>{error}</Alert>}
      <NameFields value={form.name} onChange={(name) => setForm({ ...form, name })} idPrefix="admin-name" autoComplete={false} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <Field label="Логин" value={form.login} onChange={(e) => setForm({ ...form, login: e.target.value })} />
      </div>
      <Button type="submit" variant="secondary" loading={busy}>
        Сохранить
      </Button>
    </form>
  );
}

function RolesForm({ u, self, onSaved }: { u: AdminUser; self: boolean; onSaved: (u: AdminUser) => void }) {
  const [roles, setRoles] = useState(u.roles);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const changed = [...roles].sort().join() !== [...u.roles].sort().join();
  return (
    <section className="space-y-3 rounded-2xl border border-line bg-surface p-5">
      <h2 className="font-semibold">Роли</h2>
      {error && <Alert>{error}</Alert>}
      <div className="flex flex-wrap gap-3">
        {Object.entries(ROLE_LABELS).map(([role, title]) => (
          <label key={role} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={roles.includes(role)}
              disabled={self && role === "admin"}
              onChange={(e) => setRoles(e.target.checked ? [...roles, role] : roles.filter((r) => r !== role))}
              className="h-4 w-4 accent-brand"
            />
            {title}
          </label>
        ))}
      </div>
      <Button
        variant="secondary"
        loading={busy}
        disabled={!changed || !roles.length}
        onClick={async () => {
          setBusy(true);
          setError(undefined);
          try {
            onSaved(await admin.setRoles(u.id, roles));
          } catch (e) {
            setError(errorText(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        Сохранить роли
      </Button>
    </section>
  );
}

function GrantForm({ userId, onDone }: { userId: string; onDone: (message: string) => void }) {
  const [days, setDays] = useState(30);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="space-y-3 rounded-2xl border border-line bg-surface p-5"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(undefined);
        try {
          const r = await admin.grant(userId, days, reason);
          setReason("");
          onDone(`«Базовый» действует до ${fmtDateTime(r.period_end)}`);
        } catch (err) {
          setError(errorText(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      <h2 className="font-semibold">Подписка без оплаты</h2>
      <p className="text-sm text-fg-soft">Компенсация, сбой оплаты, акция — продлит «Базовый» на выбранный срок.</p>
      {error && <Alert>{error}</Alert>}
      <div className="grid gap-3 sm:grid-cols-[8rem_1fr]">
        <Field label="Дней" type="number" min={1} max={366} value={days} onChange={(e) => setDays(Number(e.target.value))} />
        <Field label="Причина" required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
      <Button type="submit" variant="secondary" loading={busy} disabled={reason.trim().length < 3}>
        Подключить
      </Button>
    </form>
  );
}

const PAY_STATUS = { pending: "ожидает", succeeded: "оплачен", canceled: "не прошёл" } as const;

function Payments({ userId }: { userId: string }) {
  const list = useLoad(() => admin.payments({ user_id: userId, limit: 20 }), [userId]);
  if (!list.data?.length) return null;
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold">Платежи</h2>
      <ul className="divide-y divide-line rounded-2xl border border-line bg-surface text-sm">
        {list.data.map((p) => (
          <li key={p.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5">
            <span className="min-w-0 flex-1">
              {p.description}
              <span className="block text-xs text-fg-soft">
                {fmtDateTime(p.paid_at ?? p.created_at)} · {p.provider === "fake" ? "тестовая оплата" : p.provider}
                {p.error && ` · ${p.error}`}
              </span>
            </span>
            <span className="tabular-nums">{fmtRub(p.amount_rub)}</span>
            <Badge tone={p.status === "succeeded" ? "ok" : p.status === "canceled" ? "warn" : "neutral"}>{PAY_STATUS[p.status]}</Badge>
          </li>
        ))}
      </ul>
    </section>
  );
}
