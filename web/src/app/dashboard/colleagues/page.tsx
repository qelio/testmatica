"use client";

import { useState } from "react";

import { Alert, Button, EmptyState, Spinner } from "@/components/ui";
import { type Colleagues, colleagues as api } from "@/lib/api";
import { fmtDate } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

/** Мои коллеги (решение №56): заявка педагогу по логину или почте; коллеге можно дать доступ к классу и тесту. */
export default function ColleaguesPage() {
  const load = useLoad(() => api.list(), []);
  const [data, setData] = useState<Colleagues | null>(null);
  const view = data ?? load.data;
  const [identifier, setIdentifier] = useState("");
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [busy, setBusy] = useState<string | null>(null);

  async function run(key: string, action: () => Promise<Colleagues>, message?: string) {
    setBusy(key);
    setError(undefined);
    setNotice(undefined);
    try {
      setData(await action());
      if (message) setNotice(message);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  const person = (p: { full_name: string; login: string | null }) => (
    <span className="min-w-0 flex-1">
      <span className="block font-medium">{p.full_name}</span>
      {p.login && <span className="block text-xs text-fg-soft">{p.login}</span>}
    </span>
  );

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <h1 className="text-2xl font-semibold tracking-tight">Мои коллеги</h1>
      <p className="text-sm text-fg-soft">
        Добавьте педагогов, с которыми работаете вместе. Коллеге можно дать доступ к своему классу — он сможет вести с ним свои занятия и
        тесты, — и поделиться тестом.
      </p>
      {error && <Alert>{error}</Alert>}
      {notice && <Alert kind="success">{notice}</Alert>}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (identifier.trim())
            void run("add", () => api.request(identifier.trim()), "Заявка отправлена — коллега увидит её в уведомлениях").then(() => setIdentifier(""));
        }}
        className="flex flex-wrap gap-2 rounded-2xl border border-line bg-surface p-3"
      >
        <input
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          placeholder="Логин или почта педагога"
          aria-label="Логин или почта педагога"
          className="h-11 min-w-0 flex-1 basis-60 rounded-xl border border-line bg-surface px-3.5 outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
        />
        <Button type="submit" loading={busy === "add"} disabled={!identifier.trim()} className="h-11">
          Добавить в коллеги
        </Button>
      </form>

      {!view ? (
        load.error ? <Alert>{load.error}</Alert> : <Spinner />
      ) : (
        <>
          {view.incoming.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-sm font-semibold">Хотят добавить вас в коллеги</h2>
              <ul className="divide-y divide-line rounded-2xl border border-brand/40 bg-surface">
                {view.incoming.map((r) => (
                  <li key={r.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                    {person(r)}
                    <Button className="h-9" loading={busy === `a${r.id}`} onClick={() => run(`a${r.id}`, () => api.accept(r.id), `${r.full_name} теперь ваш коллега`)}>
                      Принять
                    </Button>
                    <Button variant="ghost" className="h-9" loading={busy === `d${r.id}`} onClick={() => run(`d${r.id}`, () => api.decline(r.id))}>
                      Отклонить
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="space-y-2">
            <h2 className="text-sm font-semibold">Коллеги</h2>
            {!view.colleagues.length ? (
              <EmptyState title="Коллег пока нет" text="Введите логин или почту педагога выше — он получит заявку." />
            ) : (
              <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
                {view.colleagues.map((c) => (
                  <li key={c.user_id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                    {person(c)}
                    <span className="text-xs text-fg-soft">с {fmtDate(c.since)}</span>
                    <Button
                      variant="ghost"
                      className="h-9 text-danger"
                      loading={busy === `r${c.user_id}`}
                      onClick={() => {
                        if (window.confirm(`Убрать ${c.full_name} из коллег? Доступ к вашим классам и тестам у него закроется, сделанное останется.`))
                          void run(`r${c.user_id}`, () => api.remove(c.user_id));
                      }}
                    >
                      Убрать
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {view.outgoing.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-sm font-semibold text-fg-soft">Отправленные заявки</h2>
              <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
                {view.outgoing.map((r) => (
                  <li key={r.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                    {person(r)}
                    <span className="text-xs text-fg-soft">ждём ответа</span>
                    <Button variant="ghost" className="h-9" loading={busy === `c${r.id}`} onClick={() => run(`c${r.id}`, () => api.remove(r.user_id))}>
                      Отозвать
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
