"use client";

import { useCallback, useRef, useState } from "react";

import { type Attachment, type FilePurpose, fmtSize, type UploadedFile, uploadFile } from "@/lib/api";
import { errorText } from "@/lib/hooks";

const IMAGE = /^image\//;

export type Upload = {
  key: string;
  name: string;
  size: number;
  status: "uploading" | "done" | "error";
  file?: UploadedFile;
  error?: string;
};

/** Загрузка файлов сразу при выборе; в сообщение/ответ уходят только id загруженных. */
export function useUploads(purpose: FilePurpose, max = 10) {
  const [items, setItems] = useState<Upload[]>([]);

  const add = useCallback(
    (files: FileList | File[]) => {
      const list = Array.from(files).slice(0, Math.max(0, max - items.length));
      for (const f of list) {
        const key = `${f.name}-${f.size}-${Math.random()}`;
        setItems((prev) => [...prev, { key, name: f.name, size: f.size, status: "uploading" }]);
        uploadFile(f, purpose)
          .then((file) => setItems((prev) => prev.map((u) => (u.key === key ? { ...u, status: "done", file } : u))))
          .catch((e) => setItems((prev) => prev.map((u) => (u.key === key ? { ...u, status: "error", error: errorText(e) } : u))));
      }
    },
    [purpose, max, items.length],
  );

  return {
    items,
    add,
    remove: (key: string) => setItems((prev) => prev.filter((u) => u.key !== key)),
    clear: () => setItems([]),
    ids: items.filter((u) => u.status === "done").map((u) => u.file!.id),
    busy: items.some((u) => u.status === "uploading"),
  };
}

export function AttachButton({ onFiles, disabled, label = "Прикрепить файл" }: { onFiles: (f: FileList) => void; disabled?: boolean; label?: string }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <button
        type="button"
        disabled={disabled}
        onClick={() => input.current?.click()}
        aria-label={label}
        title={label}
        className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-line text-fg-soft hover:bg-muted hover:text-fg disabled:opacity-50"
      >
        <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7">
          <path d="M14.5 9.5l-5.3 5.3a3.2 3.2 0 01-4.5-4.5l6.4-6.4a2.1 2.1 0 013 3l-6.3 6.3a1 1 0 01-1.5-1.5l5.6-5.6" strokeLinecap="round" />
        </svg>
      </button>
      <input
        ref={input}
        type="file"
        multiple
        hidden
        onChange={(e) => {
          if (e.target.files?.length) onFiles(e.target.files);
          e.target.value = "";
        }}
      />
    </>
  );
}

export function UploadChips({ items, onRemove }: { items: Upload[]; onRemove: (key: string) => void }) {
  if (!items.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((u) => (
        <span
          key={u.key}
          className={`inline-flex max-w-full items-center gap-2 rounded-lg border px-2.5 py-1 text-sm ${u.status === "error" ? "border-danger/40 text-danger" : "border-line bg-muted"}`}
          title={u.error}
        >
          {u.status === "uploading" && <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-r-transparent" />}
          <span className="truncate">{u.name}</span>
          <span className="shrink-0 text-xs text-fg-soft">{u.status === "error" ? u.error : fmtSize(u.size)}</span>
          <button type="button" onClick={() => onRemove(u.key)} aria-label={`Убрать ${u.name}`} className="text-fg-soft hover:text-fg">
            ×
          </button>
        </span>
      ))}
    </div>
  );
}

/** Вложение: картинка — превью, остальное — карточка файла. Если ссылка истекла, getFresh выдаст новую. */
export function AttachmentView({ att, getFresh, dark }: { att: Attachment; getFresh?: () => Promise<Attachment>; dark?: boolean }) {
  async function open(e: React.MouseEvent) {
    if (!getFresh) return;
    e.preventDefault();
    const fresh = await getFresh().catch(() => null);
    const url = fresh?.url ?? att.url;
    if (url) window.open(url, "_blank", "noopener");
  }

  if (IMAGE.test(att.mime) && att.url) {
    return (
      <a href={att.url} target="_blank" rel="noopener noreferrer" onClick={open} className="block">
        {/* eslint-disable-next-line @next/next/no-img-element -- временные ссылки S3, оптимизация Next не нужна */}
        <img src={att.url} alt={att.filename} className="max-h-60 max-w-full rounded-lg object-contain" loading="lazy" />
      </a>
    );
  }
  return (
    <a
      href={att.url ?? "#"}
      target="_blank"
      rel="noopener noreferrer"
      onClick={open}
      className={`flex max-w-72 items-center gap-2.5 rounded-lg border px-3 py-2 text-sm ${dark ? "border-white/30 hover:bg-white/10" : "border-line hover:bg-muted"}`}
    >
      <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-md text-[10px] font-bold uppercase ${dark ? "bg-white/20" : "bg-brand/10 text-brand-text"}`}>
        {att.filename.split(".").pop()?.slice(0, 4)}
      </span>
      <span className="min-w-0">
        <span className="block truncate font-medium">{att.filename}</span>
        <span className={`block text-xs ${dark ? "text-white/70" : "text-fg-soft"}`}>{fmtSize(att.size)}</span>
      </span>
    </a>
  );
}
