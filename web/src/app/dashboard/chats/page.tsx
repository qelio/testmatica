"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Fragment, Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { Alert, Badge, Button, EmptyState, Modal, Spinner } from "@/components/ui";
import { chat, type ChatMessage, type Conversation } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtTime, sameDay } from "@/lib/dates";
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
    if (e.type === "message" || e.type === "deleted" || e.type === "reconnected") list.reload();
  });

  // Новый личный диалог без сообщений в общий список не попадает — загружаем его отдельно.
  const inList = list.data?.find((c) => c.id === openId) ?? null;
  const single = useLoad(
    () => (openId && list.data && !inList ? chat.conversation(openId) : Promise.resolve(null)),
    [openId, !!list.data, !!inList],
  );
  const current = inList ?? single.data;

  return (
    <div className="-m-4 flex h-[calc(100dvh-4rem)] sm:-m-6 lg:-m-8">
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
                      ? `${c.kind === "group" ? `${c.last_message.author_name.split(" ")[0]}: ` : ""}${c.last_message.text}`
                      : "Нет сообщений"}
                  </p>
                  {c.unread > 0 && (
                    <span className="grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-brand px-1.5 text-xs font-medium text-white">
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

function shortTime(iso: string): string {
  const d = new Date(iso);
  return sameDay(d, new Date()) ? fmtTime(d) : fmtDate(d, { day: "numeric", month: "short" });
}

function Avatar({ name, group }: { name: string; group?: boolean }) {
  const initials = name
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return (
    <span
      className={`grid h-10 w-10 shrink-0 place-items-center rounded-full text-sm font-semibold ${group ? "bg-school/20 text-school" : "bg-brand/15 text-brand"}`}
    >
      {initials}
    </span>
  );
}

/** Ссылки в тексте сообщения делаем кликабельными. */
function Linkified({ text }: { text: string }) {
  const parts = text.split(/(https?:\/\/[^\s]+)/g);
  return (
    <>
      {parts.map((part, i) =>
        /^https?:\/\//.test(part) ? (
          <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="break-all underline">
            {part}
          </a>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}

function Thread({
  conversation,
  onBack,
  onChanged,
}: {
  conversation: Conversation;
  onBack: () => void;
  onChanged: () => void;
}) {
  const { user } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [text, setText] = useState("");
  const [announcement, setAnnouncement] = useState(false);
  const [error, setError] = useState<string>();
  const [sending, setSending] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const isTeacher = conversation.my_role === "teacher";
  // onChanged приходит новой функцией на каждый рендер — держим в ref, чтобы не перезагружать историю.
  const changed = useRef(onChanged);
  useEffect(() => {
    changed.current = onChanged;
  });

  const load = useCallback(async () => {
    try {
      const page = await chat.messages(conversation.id);
      setMessages(page.reverse());
      setHasMore(page.length === 50);
      stickToBottom.current = true;
      await chat.read(conversation.id);
      changed.current();
    } catch (e) {
      setError(errorText(e));
    }
  }, [conversation.id]);

  useEffect(() => {
    // Загрузка истории при открытии чата.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  useRealtime((e) => {
    if (e.type === "reconnected") load();
    if (e.type === "message" && e.conversation_id === conversation.id) {
      setMessages((prev) => (prev && !prev.some((m) => m.id === e.message.id) ? [...prev, e.message] : prev));
      const el = scroller.current;
      stickToBottom.current = !el || el.scrollHeight - el.scrollTop - el.clientHeight < 120;
      if (e.message.author_id !== user?.id) chat.read(conversation.id).then(() => changed.current()).catch(() => {});
    }
    if (e.type === "deleted" && e.conversation_id === conversation.id) {
      setMessages((prev) => prev?.map((m) => (m.id === e.message_id ? { ...m, deleted: true, text: "Сообщение удалено" } : m)) ?? prev);
    }
  });

  async function loadOlder() {
    if (!messages?.length) return;
    const el = scroller.current;
    const before = el?.scrollHeight ?? 0;
    const page = await chat.messages(conversation.id, messages[0].created_at);
    setHasMore(page.length === 50);
    stickToBottom.current = false;
    setMessages([...page.reverse(), ...messages]);
    requestAnimationFrame(() => {
      if (el) el.scrollTop = el.scrollHeight - before;
    });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const value = text.trim();
    if (!value) return;
    setSending(true);
    setError(undefined);
    try {
      const msg = await chat.send(conversation.id, value, announcement);
      stickToBottom.current = true;
      setMessages((prev) => (prev && !prev.some((m) => m.id === msg.id) ? [...prev, msg] : prev));
      setText("");
      setAnnouncement(false);
      onChanged();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <header className="flex items-center gap-3 border-b border-line bg-surface px-4 py-3">
        <button onClick={onBack} className="rounded-lg p-1.5 text-fg-soft hover:bg-muted md:hidden" aria-label="К списку чатов">
          ←
        </button>
        <Avatar name={conversation.title} group={conversation.kind === "group"} />
        <div className="min-w-0">
          <p className="truncate font-semibold">{conversation.title}</p>
          <p className="text-xs text-fg-soft">{conversation.kind === "group" ? "групповой чат" : "личный диалог"}</p>
        </div>
      </header>

      {conversation.pinned && (
        <div className="flex items-start gap-3 border-b border-line bg-brand/5 px-4 py-2.5 text-sm">
          <Badge tone="brand">объявление</Badge>
          <p className="min-w-0 flex-1 whitespace-pre-wrap">
            <Linkified text={conversation.pinned.text} />
          </p>
          {isTeacher && (
            <button
              onClick={async () => {
                await chat.unpin(conversation.id);
                onChanged();
              }}
              className="shrink-0 text-xs text-fg-soft hover:text-fg"
            >
              Открепить
            </button>
          )}
        </div>
      )}

      <div ref={scroller} className="flex-1 overflow-y-auto px-4 py-4">
        {!messages && !error && <Spinner />}
        {hasMore && messages && messages.length > 0 && (
          <div className="mb-3 text-center">
            <button onClick={loadOlder} className="text-sm text-brand hover:underline">
              Показать более ранние
            </button>
          </div>
        )}
        {messages?.length === 0 && <p className="text-center text-sm text-fg-soft">Сообщений пока нет — напишите первым.</p>}
        <div className="space-y-1.5">
          {messages?.map((m, i) => {
            const mine = m.author_id === user?.id;
            const prev = messages[i - 1];
            const newDay = !prev || !sameDay(new Date(prev.created_at), new Date(m.created_at));
            const showAuthor = conversation.kind === "group" && !mine && (newDay || prev.author_id !== m.author_id);
            return (
              <Fragment key={m.id}>
                {newDay && (
                  <p className="py-2 text-center text-xs text-fg-soft">{fmtDate(m.created_at, { day: "numeric", month: "long" })}</p>
                )}
                <div className={`group flex ${mine ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[80%] rounded-2xl px-3.5 py-2 text-[15px] ${
                      m.deleted
                        ? "border border-dashed border-line text-fg-soft italic"
                        : m.is_announcement
                          ? "border border-brand/40 bg-brand/10"
                          : mine
                            ? "bg-brand text-white"
                            : "bg-surface"
                    }`}
                  >
                    {showAuthor && <p className="mb-0.5 text-xs font-semibold text-brand">{m.author_name}</p>}
                    {m.is_announcement && !m.deleted && <p className="mb-0.5 text-xs font-semibold text-brand">Объявление</p>}
                    <p className="whitespace-pre-wrap break-words">
                      <Linkified text={m.text} />
                    </p>
                    <p className={`mt-0.5 text-right text-[11px] ${mine && !m.deleted && !m.is_announcement ? "text-white/70" : "text-fg-soft"}`}>
                      {fmtTime(m.created_at)}
                      {mine && !m.deleted && (
                        <button
                          onClick={() => chat.deleteMessage(m.id).catch((err) => setError(errorText(err)))}
                          className="ml-2 hidden underline group-hover:inline"
                        >
                          удалить
                        </button>
                      )}
                    </p>
                  </div>
                </div>
              </Fragment>
            );
          })}
        </div>
      </div>

      {error && (
        <div className="px-4 pb-2">
          <Alert>{error}</Alert>
        </div>
      )}
      {conversation.can_write ? (
        <form onSubmit={submit} className="border-t border-line bg-surface p-3">
          {isTeacher && conversation.kind === "group" && (
            <label className="mb-2 flex items-center gap-2 text-sm text-fg-soft">
              <input type="checkbox" checked={announcement} onChange={(e) => setAnnouncement(e.target.checked)} className="accent-brand" />
              Объявление — закрепить для всей группы
            </label>
          )}
          <div className="flex items-end gap-2">
            <textarea
              rows={1}
              value={text}
              maxLength={4000}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  e.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder="Сообщение…"
              aria-label="Сообщение"
              className="max-h-40 min-h-11 flex-1 resize-none rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
            />
            <Button type="submit" loading={sending} disabled={!text.trim()}>
              Отправить
            </Button>
          </div>
        </form>
      ) : (
        <p className="border-t border-line bg-surface p-4 text-center text-sm text-fg-soft">
          В этот чат больше нельзя писать — история сохранена.
        </p>
      )}
    </>
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
