"use client";

import { Crown } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AttachButton, UploadChips, useUploads } from "@/components/files";
import { Alert, Badge, Button, Field, Modal, Select } from "@/components/ui";
import { support, type SupportTicket, type TicketCategory, type TicketStatus } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/auth";
import { fmtDateTime } from "@/lib/dates";
import { errorText } from "@/lib/hooks";

export const CATEGORY_LABELS: Record<TicketCategory, string> = {
  account: "Аккаунт и вход",
  lessons: "Занятия и расписание",
  tests: "Тесты и задания",
  tutors: "Репетиторы и заявки",
  payments: "Тариф и оплата",
  bug: "Ошибка на сайте",
  idea: "Предложение",
  other: "Другое",
};

export function StatusBadge({ status, staff }: { status: TicketStatus; staff: boolean }) {
  // Подписи — с точки зрения того, кто смотрит: пользователю «ждёт ответа», поддержке — «нужно ответить».
  if (status === "open") return <Badge tone="warn">{staff ? "нужно ответить" : "ждёт ответа"}</Badge>;
  if (status === "answered") return <Badge tone="brand">{staff ? "ответили" : "есть ответ"}</Badge>;
  return <Badge>закрыто</Badge>;
}

/** Строка обращения в списке «Мои обращения» и в очереди поддержки. */
export function TicketRow({ t, staff }: { t: SupportTicket; staff: boolean }) {
  const role = t.requester_roles.find((r) => r in ROLE_LABELS);
  return (
    <li>
      <Link href={`/dashboard/support/${t.id}`} className="flex items-start gap-3 px-5 py-4 hover:bg-muted/60">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={t.status} staff={staff} />
            {staff && t.priority && (
              <span className="inline-flex items-center gap-1 rounded-md bg-sun/20 px-2 py-0.5 text-xs font-medium text-sun" title="Подписка «Базовый» — в очереди первым">
                <Crown size={12} aria-hidden /> подписчик
              </span>
            )}
            <span className="text-xs text-fg-soft">{CATEGORY_LABELS[t.category]}</span>
          </div>
          <p className="mt-1 truncate font-medium">{t.subject}</p>
          {t.last_text && <p className="truncate text-sm text-fg-soft">{t.last_text}</p>}
          <p className="mt-1 text-xs text-fg-soft">
            {staff && (
              <>
                {t.requester_name}
                {role && ` · ${ROLE_LABELS[role].toLowerCase()}`} ·{" "}
              </>
            )}
            {fmtDateTime(t.updated_at)}
            {t.assignee_name && ` · ведёт ${t.assignee_name}`}
          </p>
        </div>
        {t.unread > 0 && (
          <span className="mt-1 grid h-6 min-w-6 place-items-center rounded-full bg-brand px-1.5 text-xs font-medium text-on-brand" aria-label="Непрочитанных">
            {t.unread}
          </span>
        )}
      </Link>
    </li>
  );
}

/** Новое обращение: категория, тема, описание, файлы (скриншоты). */
export function NewTicketModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (t: SupportTicket) => void }) {
  const [category, setCategory] = useState<TicketCategory>("other");
  const [subject, setSubject] = useState("");
  const [text, setText] = useState("");
  const uploads = useUploads("chat_attachment", 10);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      onCreated(await support.create({ category, subject: subject.trim(), text: text.trim(), attachment_ids: uploads.ids }));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Новое обращение">
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <Select label="О чём вопрос" value={category} onChange={(e) => setCategory(e.target.value as TicketCategory)}>
          {Object.entries(CATEGORY_LABELS).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </Select>
        <Field label="Тема" placeholder="Коротко: что случилось" maxLength={200} value={subject} onChange={(e) => setSubject(e.target.value)} required />
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Подробности</span>
          <textarea
            rows={5}
            maxLength={4000}
            value={text}
            onChange={(e) => setText(e.target.value)}
            required
            placeholder="Что вы делали, что ожидали увидеть и что произошло. Скриншот очень поможет."
            className="w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
          />
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <AttachButton onFiles={uploads.add} label="Прикрепить файл или скриншот" />
          <UploadChips items={uploads.items} onRemove={uploads.remove} />
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" loading={busy || uploads.busy} disabled={subject.trim().length < 3 || !text.trim()}>
            Отправить
          </Button>
        </div>
      </form>
    </Modal>
  );
}
