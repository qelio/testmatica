"use client";

import Link from "next/link";
import { useState } from "react";

import { UploadChips, useUploads } from "@/components/files";
import { Markdown } from "@/components/markdown";
import { KIND_LABELS, MaterialView } from "@/components/material-view";
import { Alert, Button, Field, Select, Spinner } from "@/components/ui";
import { content, type Material, type MaterialKind } from "@/lib/api";
import { errorText, useLoad } from "@/lib/hooks";

const ACCEPT: Partial<Record<MaterialKind, string>> = {
  video: ".mp4,.webm,.mov",
  pdf: ".pdf",
  file: ".doc,.docx,.odt,.rtf,.txt,.xls,.xlsx,.ods,.csv,.ppt,.pptx,.odp,.zip,.7z,.rar,.png,.jpg,.jpeg",
};

export function ModuleView({ id, base }: { id: string; base: string }) {
  const mod = useLoad(() => content.module(id, true), [id]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState<string>();

  async function act(action: () => Promise<unknown>) {
    setError(undefined);
    try {
      await action();
      mod.reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  if (mod.error) return <Alert>{mod.error}</Alert>;
  const m = mod.data;
  if (!m) return <Spinner />;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <nav className="text-sm text-fg-soft">
        <Link href={`${base}/course/${m.course_id}`} className="hover:text-fg">
          {m.course_title}
        </Link>
        <span> / {m.section_title}</span>
      </nav>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{m.title}</h1>
        {m.description && <p className="mt-2 text-fg-soft">{m.description}</p>}
      </div>
      {error && <Alert>{error}</Alert>}

      {m.materials.length === 0 && <p className="text-fg-soft">В модуле пока нет материалов.</p>}
      {m.materials.map((mat) => (
        <div key={mat.id} className="space-y-2">
          {editingId === mat.id ? (
            <MaterialEditor
              material={mat}
              onCancel={() => setEditingId(null)}
              onSaved={() => {
                setEditingId(null);
                mod.reload();
              }}
            />
          ) : (
            <MaterialView material={mat} />
          )}
          {m.can_edit && editingId !== mat.id && (
            <div className="flex justify-end gap-1 text-sm">
              <button onClick={() => act(() => content.moveMaterial(mat.id, "up"))} className="rounded-lg px-2 py-1 text-fg-soft hover:bg-muted">
                ↑
              </button>
              <button onClick={() => act(() => content.moveMaterial(mat.id, "down"))} className="rounded-lg px-2 py-1 text-fg-soft hover:bg-muted">
                ↓
              </button>
              <button onClick={() => setEditingId(mat.id)} className="rounded-lg px-2 py-1 text-fg-soft hover:bg-muted">
                Изменить
              </button>
              <button
                onClick={() => window.confirm(`Удалить «${mat.title}»?`) && act(() => content.deleteMaterial(mat.id))}
                className="rounded-lg px-2 py-1 text-danger hover:bg-muted"
              >
                Удалить
              </button>
            </div>
          )}
        </div>
      ))}

      {m.can_edit && <NewMaterial moduleId={m.id} onAdded={() => mod.reload()} />}

      <div className="flex justify-between gap-3 border-t border-line pt-4">
        {m.prev_module_id ? (
          <Link href={`${base}/module/${m.prev_module_id}`} className="font-medium text-brand hover:underline">
            ← Предыдущий модуль
          </Link>
        ) : (
          <span />
        )}
        {m.next_module_id ? (
          <Link href={`${base}/module/${m.next_module_id}`} className="font-medium text-brand hover:underline">
            Следующий модуль →
          </Link>
        ) : (
          <Link href={`${base}/course/${m.course_id}`} className="font-medium text-brand hover:underline">
            К оглавлению курса
          </Link>
        )}
      </div>
    </div>
  );
}

function MarkdownEditor({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [preview, setPreview] = useState(false);
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-sm font-medium">Текст</span>
        <button type="button" onClick={() => setPreview((p) => !p)} className="text-sm text-brand hover:underline">
          {preview ? "Редактировать" : "Предпросмотр"}
        </button>
      </div>
      {preview ? (
        <div className="min-h-40 rounded-xl border border-line p-4">
          <Markdown text={value || "_Пусто_"} />
        </div>
      ) : (
        <textarea
          rows={10}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={"## Заголовок\n\nТекст, **жирный**, *курсив*, списки, таблицы.\nФормулы: $x^2 + y^2 = r^2$ или отдельной строкой $$\\frac{a}{b}$$"}
          className="w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 font-mono text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
        />
      )}
      <p className="mt-1 text-xs text-fg-soft">Markdown: # заголовки, **жирный**, списки, таблицы, ссылки. Формулы — в формате LaTeX между $…$.</p>
    </div>
  );
}

function NewMaterial({ moduleId, onAdded }: { moduleId: string; onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<MaterialKind>("text");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [url, setUrl] = useState("");
  const uploads = useUploads("material", 1);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const needsFile = kind === "video" || kind === "pdf" || kind === "file";

  if (!open) {
    return (
      <Button variant="secondary" className="w-full border-dashed" onClick={() => setOpen(true)}>
        + Добавить материал
      </Button>
    );
  }

  return (
    <form
      className="space-y-4 rounded-2xl border border-line bg-surface p-5"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(undefined);
        try {
          await content.addMaterial(moduleId, {
            kind,
            title,
            body: kind === "text" || kind === "card" ? body : undefined,
            url: kind === "link" ? url : undefined,
            file_id: needsFile ? uploads.ids[0] : undefined,
          });
          setTitle("");
          setBody("");
          setUrl("");
          uploads.clear();
          setOpen(false);
          onAdded();
        } catch (err) {
          setError(errorText(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      <h3 className="font-semibold">Новый материал</h3>
      {error && <Alert>{error}</Alert>}
      <Select
        label="Тип"
        value={kind}
        onChange={(e) => {
          setKind(e.target.value as MaterialKind);
          uploads.clear();
        }}
      >
        {(Object.keys(KIND_LABELS) as MaterialKind[]).map((k) => (
          <option key={k} value={k}>
            {KIND_LABELS[k]}
          </option>
        ))}
      </Select>
      <Field label="Название" required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
      {(kind === "text" || kind === "card") && <MarkdownEditor value={body} onChange={setBody} />}
      {kind === "link" && (
        <Field label="Ссылка" type="url" required placeholder="https://www.youtube.com/watch?v=…" value={url} onChange={(e) => setUrl(e.target.value)} />
      )}
      {needsFile && (
        <div className="space-y-2">
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-line px-4 py-2.5 text-sm font-medium hover:bg-muted">
            {uploads.items.length ? "Заменить файл" : "Выбрать файл"}
            <input
              type="file"
              hidden
              accept={ACCEPT[kind]}
              onChange={(e) => {
                if (e.target.files?.length) {
                  uploads.clear();
                  uploads.add(e.target.files);
                }
                e.target.value = "";
              }}
            />
          </label>
          <p className="text-xs text-fg-soft">{kind === "video" ? "MP4, WebM или MOV, до 500 МБ" : "До 500 МБ"}</p>
          <UploadChips items={uploads.items} onRemove={uploads.remove} />
        </div>
      )}
      <div className="flex gap-2">
        <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
          Отмена
        </Button>
        <Button type="submit" loading={busy || uploads.busy} disabled={!title.trim() || (needsFile && !uploads.ids.length)} className="flex-1">
          Добавить
        </Button>
      </div>
    </form>
  );
}

function MaterialEditor({ material, onCancel, onSaved }: { material: Material; onCancel: () => void; onSaved: () => void }) {
  const [title, setTitle] = useState(material.title);
  const [body, setBody] = useState(material.body);
  const [url, setUrl] = useState(material.url ?? "");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="space-y-4 rounded-2xl border border-brand/40 bg-surface p-5"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(undefined);
        try {
          await content.updateMaterial(material.id, {
            title,
            ...(material.kind === "text" || material.kind === "card" ? { body } : {}),
            ...(material.kind === "link" ? { url } : {}),
          });
          onSaved();
        } catch (err) {
          setError(errorText(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      {error && <Alert>{error}</Alert>}
      <Field label="Название" required value={title} onChange={(e) => setTitle(e.target.value)} />
      {(material.kind === "text" || material.kind === "card") && <MarkdownEditor value={body} onChange={setBody} />}
      {material.kind === "link" && <Field label="Ссылка" type="url" required value={url} onChange={(e) => setUrl(e.target.value)} />}
      {material.file && <p className="text-sm text-fg-soft">Файл: {material.file.filename}. Чтобы заменить файл, удалите материал и добавьте заново.</p>}
      <div className="flex gap-2">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Отмена
        </Button>
        <Button type="submit" loading={busy} className="flex-1">
          Сохранить
        </Button>
      </div>
    </form>
  );
}
