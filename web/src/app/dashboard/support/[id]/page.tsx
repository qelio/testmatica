"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { Thread } from "@/components/chat-thread";
import { CATEGORY_LABELS, StatusBadge } from "@/components/support";
import { Alert, Button, Spinner } from "@/components/ui";
import { chat, support, type SupportTicket } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";
import { useRealtime } from "@/lib/realtime";

/** Обращение: тема, статус, кто ведёт, и переписка с поддержкой. */
export default function TicketPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  // Сначала обращение: для сотрудника это же добавляет его в участники переписки.
  const ticket = useLoad(() => support.ticket(id), [id]);
  const conv = useLoad(async () => (ticket.data ? chat.conversation(id) : null), [id, !!ticket.data]);
  const [error, setError] = useState<string>();
  useRealtime((e) => {
    if ((e.type === "message" || e.type === "refresh") && e.conversation_id === id) ticket.reload();
  });

  if (ticket.error) return <Alert>{ticket.error}</Alert>;
  if (!ticket.data || !user) return <Spinner />;
  const t = ticket.data;
  const staff = user.roles.some((r) => r === "moderator" || r === "admin");

  async function act(fn: () => Promise<SupportTicket>) {
    setError(undefined);
    try {
      await fn();
      ticket.reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <div className="mx-auto flex h-[calc(100dvh-8.5rem)] max-w-4xl flex-col gap-4">
      <div className="space-y-2">
        <Link href="/dashboard/support" className="text-sm text-fg-soft hover:text-fg">
          ← {staff ? "Все обращения" : "Мои обращения"}
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{t.subject}</h1>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-fg-soft">
              <StatusBadge status={t.status} staff={staff} />
              <span>{CATEGORY_LABELS[t.category]}</span>
              {staff && <span>· {t.requester_name}</span>}
              <span>· создано {fmtDateTime(t.created_at)}</span>
              {t.assignee_name && <span>· ведёт {t.assignee_name}</span>}
            </p>
          </div>
          <div className="flex gap-2">
            {staff && t.assignee_id !== user.id && t.status !== "closed" && (
              <Button variant="secondary" onClick={() => act(() => support.assign(t.id))}>
                Взять себе
              </Button>
            )}
            {t.status === "closed" ? (
              <Button variant="secondary" onClick={() => act(() => support.reopen(t.id))}>
                Открыть снова
              </Button>
            ) : (
              <Button variant="secondary" onClick={() => act(() => support.close(t.id))}>
                {staff ? "Закрыть" : "Вопрос решён"}
              </Button>
            )}
          </div>
        </div>
        {error && <Alert>{error}</Alert>}
      </div>
      <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-line bg-bg">
        {conv.error && <Alert>{conv.error}</Alert>}
        {conv.data ? (
          <Thread conversation={conv.data} onBack={() => {}} onChanged={() => ticket.reload()} hideHeader />
        ) : (
          !conv.error && <Spinner />
        )}
      </section>
    </div>
  );
}
