"use client";

import { useState } from "react";

import { uploadFile } from "@/lib/api";
import { errorText } from "@/lib/hooks";

/** Одна картинка для сайта (главная, обложка новости): загрузка в media с целью «site». */
export function ImagePicker({
  label,
  url,
  onUploaded,
  onClear,
}: {
  label: string;
  url: string | null;
  onUploaded: (fileId: string, url: string | null) => void;
  onClear: () => void;
}) {
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">{label}</p>
      {url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="" className="max-h-48 rounded-xl border border-line object-cover" />
      )}
      <div className="flex flex-wrap items-center gap-2">
        <label className="cursor-pointer rounded-xl border border-line px-4 py-2 text-sm font-medium hover:bg-muted">
          {busy ? "Загружаем…" : url ? "Заменить" : "Загрузить картинку"}
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            className="hidden"
            disabled={busy}
            onChange={async (e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (!file) return;
              setBusy(true);
              setError(undefined);
              try {
                const up = await uploadFile(file, "site");
                onUploaded(up.id, up.url);
              } catch (err) {
                setError(errorText(err));
              } finally {
                setBusy(false);
              }
            }}
          />
        </label>
        {url && (
          <button type="button" className="text-sm text-fg-soft hover:text-danger" onClick={onClear}>
            Убрать
          </button>
        )}
        <span className="text-xs text-fg-soft">JPG, PNG, WebP или GIF до 10 МБ</span>
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  );
}
