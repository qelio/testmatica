"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Button, Field, Select, Spinner } from "@/components/ui";
import { admin } from "@/lib/api";
import { USER_STATUS } from "@/lib/admin";
import { ROLE_LABELS } from "@/lib/auth";
import { fmtDateTime } from "@/lib/dates";
import { useLoad } from "@/lib/hooks";

const PAGE = 50;

/** Пользователи платформы — администратору: поиск, фильтры, переход в карточку. */
export default function UsersPage() {
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const page = useLoad(() => admin.users({ q: search, role, status, limit: PAGE, offset }), [search, role, status, offset]);

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <h1 className="text-2xl font-semibold tracking-tight">Пользователи</h1>
      <form
        className="grid gap-3 sm:grid-cols-[minmax(0,2fr)_1fr_1fr_auto] sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          setOffset(0);
          setSearch(q.trim());
        }}
      >
        <Field label="Поиск" placeholder="Имя, email или логин" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select label="Роль" value={role} onChange={(e) => { setRole(e.target.value); setOffset(0); }}>
          <option value="">Все</option>
          {Object.entries(ROLE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </Select>
        <Select label="Статус" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
          <option value="">Все</option>
          {Object.entries(USER_STATUS).map(([k, v]) => (
            <option key={k} value={k}>
              {v.text}
            </option>
          ))}
        </Select>
        <Button type="submit">Найти</Button>
      </form>
      {page.error && <Alert>{page.error}</Alert>}
      {!page.data ? (
        !page.error && <Spinner />
      ) : (
        <>
          <p className="text-sm text-fg-soft">Найдено: {page.data.total}</p>
          <div className="overflow-x-auto rounded-2xl border border-line bg-surface">
            <table className="w-full min-w-[48rem] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-fg-soft">
                  <th className="px-4 py-2.5 font-medium">Пользователь</th>
                  <th className="px-3 py-2.5 font-medium">Роли</th>
                  <th className="px-3 py-2.5 font-medium">Статус</th>
                  <th className="px-3 py-2.5 font-medium">Регистрация</th>
                  <th className="px-3 py-2.5 font-medium">Был на сайте</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {page.data.items.map((u) => (
                  <tr key={u.id} className="hover:bg-muted">
                    <td className="px-4 py-2">
                      <Link href={`/dashboard/users/${u.id}`} className="font-medium hover:text-brand">
                        {u.full_name}
                      </Link>
                      <span className="block text-xs text-fg-soft">{u.email ?? u.login}</span>
                    </td>
                    <td className="px-3 py-2">{u.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ")}</td>
                    <td className="px-3 py-2">
                      <Badge tone={USER_STATUS[u.status].tone}>{USER_STATUS[u.status].text}</Badge>
                    </td>
                    <td className="px-3 py-2 text-fg-soft">{fmtDateTime(u.created_at)}</td>
                    <td className="px-3 py-2 text-fg-soft">{u.last_seen_at ? fmtDateTime(u.last_seen_at) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
              ← Назад
            </Button>
            <Button variant="secondary" disabled={offset + PAGE >= page.data.total} onClick={() => setOffset(offset + PAGE)}>
              Дальше →
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
