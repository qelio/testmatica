import type { Conversation } from "@/lib/api";
import { fmtDate, fmtTime, sameDay } from "@/lib/dates";

// Строка списка чатов: общая для страницы сообщений и окна в шапке (там нельзя тянуть весь chat-thread).

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
      className={`grid h-10 w-10 shrink-0 place-items-center rounded-full text-sm font-semibold ${group ? "bg-school/20 text-school" : "bg-brand/15 text-brand-text"}`}
    >
      {initials}
    </span>
  );
}

/** Последнее сообщение одной строкой. */
export function conversationPreview(c: Conversation): string {
  if (!c.last_message) return "Нет сообщений";
  const author = c.kind === "group" ? `${c.last_message.author_name.split(" ")[0]}: ` : "";
  return `${author}${c.last_message.text || `📎 ${c.last_message.attachments.map((a) => a.filename).join(", ")}`}`;
}
