"use client";

import { Fragment, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { DealBar } from "@/components/deal-bar";
import { AttachButton, AttachmentView, UploadChips, useUploads } from "@/components/files";
import { Alert, Badge, Button, Spinner } from "@/components/ui";
import { chat, type ChatMessage, type Conversation } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtTime, sameDay } from "@/lib/dates";
import { errorText } from "@/lib/hooks";
import { useRealtime } from "@/lib/realtime";

export function shortTime(iso: string): string {
  const d = new Date(iso);
  return sameDay(d, new Date()) ? fmtTime(d) : fmtDate(d, { day: "numeric", month: "short" });
}

export function Avatar({ name, group }: { name: string; group?: boolean }) {
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

/** Переписка одного чата: история, живые сообщения, вложения, ответ. Используется в «Сообщениях» и в поддержке. */
export function Thread({
  conversation,
  onBack,
  onChanged,
  hideHeader = false,
}: {
  conversation: Conversation;
  onBack: () => void;
  onChanged: () => void;
  hideHeader?: boolean;
}) {
  const { user } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [text, setText] = useState("");
  const [announcement, setAnnouncement] = useState(false);
  const uploads = useUploads("chat_attachment");
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
    if (e.type === "reconnected" || (e.type === "refresh" && e.conversation_id === conversation.id)) load();
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
    if ((!value && !uploads.ids.length) || uploads.busy) return;
    setSending(true);
    setError(undefined);
    try {
      const msg = await chat.send(conversation.id, value, uploads.ids, announcement);
      stickToBottom.current = true;
      setMessages((prev) => (prev && !prev.some((m) => m.id === msg.id) ? [...prev, msg] : prev));
      setText("");
      uploads.clear();
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
{!hideHeader && (
      <header className="flex items-center gap-3 border-b border-line bg-surface px-4 py-3">
        <button onClick={onBack} className="rounded-lg p-1.5 text-fg-soft hover:bg-muted md:hidden" aria-label="К списку чатов">
          ←
        </button>
        <Avatar name={conversation.title} group={conversation.kind === "group"} />
        <div className="min-w-0">
          <p className="truncate font-semibold">{conversation.title}</p>
          <p className="text-xs text-fg-soft">
            {
              {
                group: "групповой чат",
                deal: "переговоры по заявке",
                support: "поддержка",
                direct: "личный диалог",
              }[conversation.kind]
            }
          </p>
        </div>
      </header>
      )}
      {conversation.kind === "deal" && <DealBar responseId={conversation.id} />}

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
                {m.is_system ? (
                  <p className="mx-auto max-w-[90%] rounded-xl bg-muted px-3 py-1.5 text-center text-sm text-fg-soft">
                    {m.text} <span className="text-[11px]">{fmtTime(m.created_at)}</span>
                  </p>
                ) : (
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
                    {m.text && (
                      <p className="whitespace-pre-wrap break-words">
                        <Linkified text={m.text} />
                      </p>
                    )}
                    {m.attachments.length > 0 && (
                      <div className="mt-1.5 space-y-1.5">
                        {m.attachments.map((a) => (
                          <AttachmentView
                            key={a.id}
                            att={a}
                            dark={mine && !m.is_announcement}
                            getFresh={() => chat.attachment(conversation.id, a.id)}
                          />
                        ))}
                      </div>
                    )}
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
                )}
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
          <div className="mb-2">
            <UploadChips items={uploads.items} onRemove={uploads.remove} />
          </div>
          <div className="flex items-end gap-2">
            <AttachButton onFiles={uploads.add} disabled={uploads.items.length >= 10} />
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
            <Button type="submit" loading={sending || uploads.busy} disabled={!text.trim() && !uploads.ids.length}>
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
