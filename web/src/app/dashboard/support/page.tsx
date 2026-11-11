"use client";

import { LifeBuoy } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { NewTicketModal, TicketRow } from "@/components/support";
import { Alert, Button, EmptyState, Spinner } from "@/components/ui";
import { support, type TicketStatus } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLoad } from "@/lib/hooks";
import { useRealtime } from "@/lib/realtime";

/** Поддержка: у пользователя — свои обращения, у модераторов и администраторов — очередь. */
export default function SupportPage() {
  const { user } = useAuth();
  if (!user) return null;
  const staff = user.roles.some((r) => r === "moderator" || r === "admin");
  return <div className="mx-auto max-w-4xl space-y-6">{staff ? <Queue /> : <MyTickets />}</div>;
}

function MyTickets() {
  const router = useRouter();
  const [creating, setCreating] = useState(false);
  const list = useLoad(() => support.mine(), []);
  useRealtime((e) => {
    if (e.type === "message" || e.type === "refresh") list.reload();
  });
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Поддержка</h1>
          <p className="mt-1 text-sm text-fg-soft">Напишите, если что-то не получается или есть идея. Отвечаем здесь же, придёт уведомление.</p>
        </div>
        <Button onClick={() => setCreating(true)}>Новое обращение</Button>
      </div>
      {list.error && <Alert>{list.error}</Alert>}
      {!list.data ? (
        !list.error && <Spinner />
      ) : list.data.length === 0 ? (
        <EmptyState
          title="Обращений пока нет"
          text="Если что-то пошло не так — опишите, что случилось, и приложите скриншот."
          action={<Button onClick={() => setCreating(true)}>Написать в поддержку</Button>}
        />
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
          {list.data.map((t) => (
            <TicketRow key={t.id} t={t} staff={false} />
          ))}
        </ul>
      )}
      <NewTicketModal open={creating} onClose={() => setCreating(false)} onCreated={(t) => router.push(`/dashboard/support/${t.id}`)} />
    </>
  );
}

const TABS: { value: TicketStatus; label: string }[] = [
  { value: "open", label: "Нужно ответить" },
  { value: "answered", label: "Ответили" },
  { value: "closed", label: "Закрытые" },
];

function Queue() {
  const [status, setStatus] = useState<TicketStatus>("open");
  const [mine, setMine] = useState(false);
  const list = useLoad(() => support.queue(status, mine), [status, mine]);
  useRealtime((e) => {
    if (e.type === "message" || e.type === "refresh") list.reload();
  });
  return (
    <>
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <LifeBuoy className="text-brand-text" aria-hidden /> Обращения в поддержку
        </h1>
        <p className="mt-1 text-sm text-fg-soft">
          Сначала — подписчики «Базового», дальше самые давние. Ответ в переписке сам переводит обращение в «Ответили».
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1 rounded-xl bg-muted p-1" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.value}
              role="tab"
              aria-selected={status === t.value}
              onClick={() => setStatus(t.value)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium ${status === t.value ? "bg-surface shadow-sm" : "text-fg-soft hover:text-fg"}`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} className="accent-brand" />
          Только мои
        </label>
      </div>
      {list.error && <Alert>{list.error}</Alert>}
      {!list.data ? (
        !list.error && <Spinner />
      ) : list.data.length === 0 ? (
        <EmptyState title={status === "open" ? "Все ответы даны 🎉" : "Здесь пусто"} />
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
          {list.data.map((t) => (
            <TicketRow key={t.id} t={t} staff />
          ))}
        </ul>
      )}
    </>
  );
}
