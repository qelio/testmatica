"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { Avatar, shortTime, Thread } from "@/components/chat-thread";
import { Alert, Button, EmptyState, Modal, Spinner } from "@/components/ui";
import { chat, type Conversation } from "@/lib/api";
import { errorText, useLoad } from "@/lib/hooks";
import { useRealtime } from "@/lib/realtime";

export default function ChatsPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Chats />
    </Suspense>
  );
}

function Chats() {
  const params = useSearchParams();
  const router = useRouter();
  const openId = params.get("c");
  const list = useLoad(() => chat.conversations(), []);
  const [picking, setPicking] = useState(false);

  const open = useCallback((id: string | null) => router.replace(id ? `/dashboard/chats?c=${id}` : "/dashboard/chats"), [router]);

  // Новое сообщение в любом чате — обновить список (порядок, превью, счётчики).
  useRealtime((e) => {
    if (e.type === "message" || e.type === "deleted" || e.type === "reconnected" || e.type === "refresh") list.reload();
  });

  // Новый личный диалог без сообщений в общий список не попадает — загружаем его отдельно.
  const inList = list.data?.find((c) => c.id === openId) ?? null;
  const single = useLoad(
    () => (openId && list.data && !inList ? chat.conversation(openId) : Promise.resolve(null)),
    [openId, !!list.data, !!inList],
  );
  const current = inList ?? single.data;
  // Чат переговоров создаётся по событию через секунду-две после заявки — если его ещё нет, пробуем снова.
  const retry = list.reload;
  useEffect(() => {
    if (!openId || !single.error) return;
    const t = setTimeout(retry, 1500);
    return () => clearTimeout(t);
  }, [openId, single.error, retry]);

  return (
    <div className="-m-4 flex h-[calc(100dvh-4.5rem)] sm:-m-6 lg:-m-8">
      <aside className={`${openId ? "hidden md:flex" : "flex"} w-full flex-col border-r border-line bg-surface md:w-80 md:shrink-0`}>
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <h1 className="text-lg font-semibold">Сообщения</h1>
          <Button variant="secondary" className="h-9" onClick={() => setPicking(true)}>
            Написать
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {list.error && (
            <div className="p-4">
              <Alert>{list.error}</Alert>
            </div>
          )}
          {!list.data && !list.error && (
            <div className="p-4">
              <Spinner />
            </div>
          )}
          {list.data?.length === 0 && (
            <p className="p-4 text-sm text-fg-soft">Чатов пока нет. Групповые чаты появятся вместе с классами и группами.</p>
          )}
          {list.data?.map((c) => (
            <button
              key={c.id}
              onClick={() => open(c.id)}
              className={`flex w-full items-start gap-3 border-b border-line/60 px-4 py-3 text-left hover:bg-muted ${c.id === openId ? "bg-muted" : ""}`}
            >
              <Avatar name={c.title} group={c.kind === "group"} />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="truncate font-medium">{c.title}</p>
                  {c.last_message && <span className="shrink-0 text-xs text-fg-soft">{shortTime(c.last_message.created_at)}</span>}
                </div>
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm text-fg-soft">
                    {c.last_message
                      ? `${c.kind === "group" ? `${c.last_message.author_name.split(" ")[0]}: ` : ""}${c.last_message.text || `📎 ${c.last_message.attachments.map((a) => a.filename).join(", ")}`}`
                      : "Нет сообщений"}
                  </p>
                  {c.unread > 0 && (
                    <span className="grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-brand px-1.5 text-xs font-medium text-on-brand">
                      {c.unread}
                    </span>
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>
      </aside>

      <section className={`${openId ? "flex" : "hidden md:flex"} min-w-0 flex-1 flex-col bg-bg`}>
        {current ? (
          <Thread key={current.id} conversation={current} onBack={() => open(null)} onChanged={() => list.reload()} />
        ) : (
          <div className="grid flex-1 place-items-center p-6">
            <EmptyState title="Выберите чат" text="Или начните новый диалог кнопкой «Написать»." />
          </div>
        )}
      </section>

      <NewChatModal
        open={picking}
        onClose={() => setPicking(false)}
        onOpened={(c) => {
          setPicking(false);
          list.reload();
          open(c.id);
        }}
      />
    </div>
  );
}

function NewChatModal({
  open,
  onClose,
  onOpened,
}: {
  open: boolean;
  onClose: () => void;
  onOpened: (c: Conversation) => void;
}) {
  return (
    <Modal open={open} onClose={onClose} title="Новый диалог">
      {open && <ContactList onOpened={onOpened} />}
    </Modal>
  );
}

function ContactList({ onOpened }: { onOpened: (c: Conversation) => void }) {
  const contacts = useLoad(() => chat.contacts(), []);
  const [error, setError] = useState<string>();
  if (contacts.error) return <Alert>{contacts.error}</Alert>;
  if (!contacts.data) return <Spinner />;
  if (!contacts.data.length) {
    return <p className="text-sm text-fg-soft">Писать можно своим педагогам, ученикам и одногруппникам — пока их нет.</p>;
  }
  return (
    <div className="space-y-3">
      {error && <Alert>{error}</Alert>}
      <ul className="max-h-96 divide-y divide-line overflow-y-auto rounded-xl border border-line">
        {contacts.data.map((c) => (
          <li key={c.id}>
            <button
              onClick={async () => {
                try {
                  onOpened(await chat.openDirect(c.id));
                } catch (e) {
                  setError(errorText(e));
                }
              }}
              className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-muted"
            >
              <Avatar name={c.full_name} />
              <span className="flex-1">{c.full_name}</span>
              <span className="text-xs text-fg-soft">{c.relation}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
