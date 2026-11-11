"use client";

import Link from "next/link";
import { useState } from "react";

import { ImagePicker } from "@/components/image-picker";
import { RichEditor } from "@/components/rich-editor";
import { Alert, Badge, Button, Field, Spinner } from "@/components/ui";
import { type NewsInput, site } from "@/lib/api";
import { fmtDateTime } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";
import type { NewsFull } from "@/lib/server-api";

const TEXTAREA =
  "w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

/** Новости: список, черновики, публикация. */
export function NewsTab() {
  const list = useLoad(() => site.news(), []);
  const [editing, setEditing] = useState<NewsFull | "new" | null>(null);
  const [error, setError] = useState<string>();

  if (editing) {
    return (
      <NewsEditor
        initial={editing === "new" ? null : editing}
        onClose={() => {
          setEditing(null);
          list.reload();
        }}
      />
    );
  }
  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setEditing("new")}>Новая новость</Button>
      </div>
      {(error || list.error) && <Alert>{error ?? list.error}</Alert>}
      {!list.data ? (
        <Spinner />
      ) : !list.data.length ? (
        <p className="text-sm text-fg-soft">Новостей пока нет.</p>
      ) : (
        <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
          {list.data.map((n) => (
            <li key={n.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <span className="min-w-0 flex-1">
                <span className="block font-medium">{n.title}</span>
                <span className="block text-xs text-fg-soft">
                  /news/{n.slug} · {n.published_at ? `опубликована ${fmtDateTime(n.published_at)}` : `изменена ${fmtDateTime(n.updated_at)}`}
                </span>
              </span>
              <Badge tone={n.status === "published" ? "ok" : "neutral"}>{n.status === "published" ? "опубликована" : "черновик"}</Badge>
              <Link href={`/news/${n.slug}`} target="_blank" className="text-sm text-brand-text hover:underline">
                Смотреть
              </Link>
              <button
                className="text-sm text-brand-text hover:underline"
                onClick={async () => {
                  try {
                    setEditing(await site.newsItem(n.id));
                  } catch (e) {
                    setError(errorText(e));
                  }
                }}
              >
                Изменить
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function NewsEditor({ initial, onClose }: { initial: NewsFull | null; onClose: () => void }) {
  const [form, setForm] = useState<NewsInput>(() => ({
    title: initial?.title ?? "",
    slug: initial?.slug ?? "",
    summary: initial?.summary ?? "",
    body: initial?.body ?? "",
    cover_file_id: initial?.cover_file_id ?? null,
    status: initial?.status ?? "draft",
  }));
  const [coverUrl, setCoverUrl] = useState(initial?.cover_url ?? null);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [editorBusy, setEditorBusy] = useState(false); // в тексте грузится картинка или файл
  const set = <K extends keyof NewsInput>(k: K, v: NewsInput[K]) => setForm((f) => ({ ...f, [k]: v }));

  async function save(status: NewsInput["status"]) {
    setBusy(true);
    setError(undefined);
    try {
      const data = { ...form, status, slug: form.slug?.trim() || null };
      if (initial) await site.updateNews(initial.id, data);
      else await site.createNews(data);
      onClose();
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4 rounded-2xl border border-line bg-surface p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-semibold">{initial ? "Новость" : "Новая новость"}</h2>
        <button className="text-sm text-fg-soft hover:text-fg" onClick={onClose}>
          ← К списку
        </button>
      </div>
      {error && <Alert>{error}</Alert>}
      <Field label="Заголовок" required maxLength={200} value={form.title} onChange={(e) => set("title", e.target.value)} />
      <Field
        label="Адрес"
        placeholder="будет из заголовка"
        hint="Латинские буквы, цифры и дефисы: /news/zapustili-proktoring"
        value={form.slug ?? ""}
        onChange={(e) => set("slug", e.target.value)}
      />
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium">Кратко (в карточке и для поисковиков)</span>
        <textarea rows={2} maxLength={500} className={TEXTAREA} value={form.summary} onChange={(e) => set("summary", e.target.value)} />
      </label>
      <ImagePicker
        label="Обложка"
        url={coverUrl}
        onUploaded={(id, url) => {
          set("cover_file_id", id);
          setCoverUrl(url);
        }}
        onClear={() => {
          set("cover_file_id", null);
          setCoverUrl(null);
        }}
      />
      <RichEditor label="Текст" value={form.body} onChange={(v) => set("body", v)} onBusyChange={setEditorBusy} placeholder="Текст новости" minHeight="18rem" />
      <div className="flex flex-wrap gap-2 border-t border-line pt-4">
        <Button loading={busy} disabled={!form.title.trim() || editorBusy} onClick={() => save("published")}>
          {initial?.status === "published" ? "Сохранить" : "Опубликовать"}
        </Button>
        <Button variant="secondary" disabled={busy || !form.title.trim() || editorBusy} onClick={() => save("draft")}>
          {initial?.status === "published" ? "Снять с публикации" : "Сохранить черновик"}
        </Button>
        {initial && (
          <Button
            variant="ghost"
            className="ml-auto text-danger"
            disabled={busy}
            onClick={async () => {
              if (!window.confirm("Удалить новость?")) return;
              try {
                await site.deleteNews(initial.id);
                onClose();
              } catch (e) {
                setError(errorText(e));
              }
            }}
          >
            Удалить
          </Button>
        )}
      </div>
    </div>
  );
}
