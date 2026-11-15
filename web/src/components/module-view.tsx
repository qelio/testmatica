"use client";

import { Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";

import { UploadChips, useUploads } from "@/components/files";
import { KIND_LABELS, MaterialView } from "@/components/material-view";
import { ModuleWorks } from "@/components/module-works";
import { RichEditor } from "@/components/rich-editor";
import { TaskPicker } from "@/components/task-picker";
import { ThemeScope } from "@/components/theme-scope";
import { Alert, Button, Field, Select, Spinner } from "@/components/ui";
import { content, type Material, type MaterialKind } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorText, useLoad } from "@/lib/hooks";

const ACCEPT: Partial<Record<MaterialKind, string>> = {
  video: ".mp4,.webm,.mov",
  pdf: ".pdf",
  file: ".doc,.docx,.odt,.rtf,.txt,.xls,.xlsx,.ods,.csv,.ppt,.pptx,.odp,.zip,.7z,.rar,.png,.jpg,.jpeg",
};

function isTheory(material: Material) {
  return material.kind === "text" || material.kind === "card";
}

export function ModuleView({ id, base }: { id: string; base: string }) {
  const { user } = useAuth();
  return <ModulePage key={`${id}:${user?.id ?? ""}`} id={id} base={base} />;
}

function ModulePage({ id, base }: { id: string; base: string }) {
  const mod = useLoad(() => content.module(id, true), [id]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [changingSteps, setChangingSteps] = useState(false);
  const [error, setError] = useState<string>();
  const [completed, setCompleted] = useState<Set<string>>(() => new Set());
  const markCompleted = useCallback((materialId: string) => {
    setCompleted((current) => current.has(materialId) ? current : new Set([...current, materialId]));
  }, []);

  async function act(action: () => Promise<unknown>) {
    setError(undefined);
    try {
      await action();
      await mod.reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  if (mod.error) return <Alert>{mod.error}</Alert>;
  const m = mod.data;
  if (!m) return <Spinner />;
  const numbered = m.course_layout === "steps";
  const steps = [null, ...(m.steps ?? [])];
  const active = numbered && steps.includes(selected) ? selected : null;
  const materials = numbered ? m.materials.filter((mat) => mat.step_id === active) : m.materials;
  const progress = new Map<string | null, boolean>();
  if (numbered) {
    for (const material of m.materials) {
      if (!isTheory(material) && material.kind !== "task") continue;
      const done = completed.has(material.id) || (material.kind === "task" ? material.solved : material.viewed);
      progress.set(material.step_id, (progress.get(material.step_id) ?? true) && done);
    }
  }

  async function changeSteps(action: () => Promise<void>) {
    setChangingSteps(true);
    await act(action);
    setChangingSteps(false);
  }

  // В черновике изменений тесты относятся к модулю опубликованной версии.
  const awaitingPublication = !!(m.revision_of && !m.origin_id);
  const works = !awaitingPublication && (
    <ModuleWorks moduleId={m.origin_id ?? m.id} courseId={m.revision_of ?? m.course_id} inModal={numbered} />
  );

  return (
    <ThemeScope page theme={m.course_theme} className="mx-auto w-full max-w-4xl">
    <div className="space-y-6">
      <nav className="tm-eyebrow text-sm text-fg-soft">
        <Link href={`${base}/course/${m.course_id}`} className="hover:text-fg">
          {m.course_title}
        </Link>
        <span> / {m.section_title}</span>
      </nav>
      <div>
        <div className="flex items-center justify-between gap-3">
          <h1 className="min-w-0 break-words text-2xl font-semibold tracking-tight sm:text-3xl">{m.title}</h1>
          {numbered && works}
        </div>
        {m.description && <p className="mt-2 text-fg-soft">{m.description}</p>}
      </div>
      {error && <Alert>{error}</Alert>}

      {numbered && (
        <nav aria-label="Подразделы модуля" className="flex flex-wrap justify-center gap-2">
          {steps.map((step, index) => {
            const done = progress.get(step) === true;
            return (
              <button
                key={step ?? "first"}
                type="button"
                aria-label={`Подраздел ${index + 1}${done ? ", выполнен" : ""}`}
                aria-current={active === step ? "true" : undefined}
                disabled={changingSteps}
                onClick={() => { setEditingId(null); setSelected(step); }}
                className={`flex size-10 items-center justify-center gap-0.5 rounded-xl border text-sm font-semibold tabular-nums ${done ? "border-ok bg-ok text-surface" : active === step ? "border-brand bg-brand text-on-brand" : "border-line bg-surface hover:bg-muted"} ${done && active === step ? "ring-2 ring-ok ring-offset-2 ring-offset-surface" : ""}`}
              >
                {index + 1}
              </button>
            );
          })}
          {m.can_edit && (
            <>
              <button
                type="button"
                aria-label="Добавить подраздел"
                title="Добавить подраздел"
                disabled={changingSteps}
                className="grid size-10 place-items-center rounded-xl border border-line bg-surface text-fg-soft hover:bg-muted hover:text-fg disabled:opacity-50"
                onClick={() => changeSteps(async () => {
                  setEditingId(null);
                  setSelected(await content.addModuleStep(id));
                })}
              >
                <Plus size={18} aria-hidden="true" />
              </button>
              {active && materials.length === 0 && (
                <button
                  type="button"
                  aria-label="Удалить пустой подраздел"
                  title="Удалить пустой подраздел"
                  disabled={changingSteps}
                  className="grid size-10 place-items-center rounded-xl border border-line bg-surface text-danger hover:bg-muted disabled:opacity-50"
                  onClick={() => changeSteps(async () => {
                    await content.deleteModuleStep(id, active);
                    setSelected(steps[steps.indexOf(active) - 1] ?? null);
                  })}
                >
                  <Trash2 size={16} aria-hidden="true" />
                </button>
              )}
            </>
          )}
        </nav>
      )}
      {materials.length === 0 && <p className="text-fg-soft">{numbered ? "В подразделе пока нет материалов." : "В модуле пока нет материалов."}</p>}
      {materials.map((mat, n) => (
        <div key={mat.id} className="space-y-2">
          {editingId === mat.id ? (
            <MaterialEditor
              material={mat}
              steps={numbered ? steps : undefined}
              onCancel={() => setEditingId(null)}
              onSaved={() => {
                setEditingId(null);
                mod.reload();
              }}
            />
          ) : (
            <MaterialView
              material={numbered && isTheory(mat) && completed.has(mat.id) ? { ...mat, viewed: true } : mat}
              n={numbered ? undefined : n + 1}
              numbered={numbered}
              onStudied={numbered && isTheory(mat) ? markCompleted : undefined}
              onSolved={numbered && mat.kind === "task" ? markCompleted : undefined}
            />
          )}
          {m.can_edit && editingId !== mat.id && (
            <div className="flex justify-end gap-1 text-sm">
              <button aria-label="Переместить выше" disabled={n === 0} onClick={() => act(() => content.moveMaterial(mat.id, "up"))} className="rounded-lg px-2 py-1 text-fg-soft hover:bg-muted disabled:opacity-40">
                ↑
              </button>
              <button aria-label="Переместить ниже" disabled={n === materials.length - 1} onClick={() => act(() => content.moveMaterial(mat.id, "down"))} className="rounded-lg px-2 py-1 text-fg-soft hover:bg-muted disabled:opacity-40">
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

      {m.can_edit && <NewMaterial key={active ?? "first"} numbered={numbered} moduleId={m.id} stepId={active ?? undefined} onAdded={() => mod.reload()} />}

      {awaitingPublication && (
        <p className="text-sm text-fg-soft">Тесты к новому модулю можно будет привязать, когда модератор примет изменения курса.</p>
      )}
      {!numbered && works}

      <div className="flex justify-between gap-3 border-t border-line pt-4">
        {m.prev_module_id ? (
          <Link href={`${base}/module/${m.prev_module_id}`} className="font-medium text-brand-text hover:underline">
            ← Предыдущий модуль
          </Link>
        ) : (
          <span />
        )}
        {m.next_module_id ? (
          <Link href={`${base}/module/${m.next_module_id}`} className="font-medium text-brand-text hover:underline">
            Следующий модуль →
          </Link>
        ) : (
          <Link href={`${base}/course/${m.course_id}`} className="font-medium text-brand-text hover:underline">
            К оглавлению курса
          </Link>
        )}
      </div>
    </div>
    </ThemeScope>
  );
}

function MarkdownEditor({ value, onChange, onBusyChange }: { value: string; onChange: (v: string) => void; onBusyChange: (busy: boolean) => void }) {
  return (
    <RichEditor
      label="Текст"
      value={value}
      onChange={onChange}
      onBusyChange={onBusyChange}
      placeholder="Объясните тему: текст, формулы, таблицы, картинки, файлы"
      minHeight="14rem"
    />
  );
}

function NewMaterial({ moduleId, stepId, numbered, onAdded }: { moduleId: string; stepId?: string; numbered: boolean; onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [kind, setKind] = useState<MaterialKind>("text");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [url, setUrl] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);
  const uploads = useUploads("material", 1);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const needsFile = kind === "video" || kind === "pdf" || kind === "file";
  const [editorBusy, setEditorBusy] = useState(false); // в тексте грузится картинка или файл

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
            step_id: stepId,
            collapsed_by_default: numbered && kind === "card" ? collapsed : undefined,
            title,
            body: kind === "text" || kind === "card" ? body : undefined,
            url: kind === "link" ? url : undefined,
            file_id: needsFile ? uploads.ids[0] : undefined,
            task_id: kind === "task" ? taskId : undefined,
          });
          setCollapsed(false);
          setTitle("");
          setBody("");
          setUrl("");
          setTaskId(null);
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
      {kind === "task" ? (
        <>
          <TaskPicker selected={taskId} onSelect={(id, t) => { setTaskId(id); if (!title) setTitle(t); }} />
          <Field label="Название в курсе (по умолчанию — название задачи)" maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
        </>
      ) : (
        <Field label="Название" required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
      )}
      {(kind === "text" || kind === "card") && <MarkdownEditor value={body} onChange={setBody} onBusyChange={setEditorBusy} />}
      {numbered && kind === "card" && <CollapsedOption checked={collapsed} onChange={setCollapsed} />}
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
        <Button type="submit" loading={busy || uploads.busy} disabled={(kind === "task" ? !taskId : !title.trim()) || (needsFile && !uploads.ids.length) || editorBusy} className="flex-1">
          Добавить
        </Button>
      </div>
    </form>
  );
}

function CollapsedOption({ checked, onChange }: { checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
      <input type="checkbox" className="size-4 accent-brand" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      Свёрнута по умолчанию
    </label>
  );
}

function MaterialEditor({ material, steps, onCancel, onSaved }: { material: Material; steps?: (string | null)[]; onCancel: () => void; onSaved: () => void }) {
  const [collapsed, setCollapsed] = useState(material.collapsed_by_default);
  const [step, setStep] = useState(material.step_id ?? "");
  const [title, setTitle] = useState(material.title);
  const [body, setBody] = useState(material.body);
  const [url, setUrl] = useState(material.url ?? "");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [editorBusy, setEditorBusy] = useState(false); // в тексте грузится картинка или файл
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
            ...(steps ? { step_id: step || null } : {}),
            ...(steps && material.kind === "card" ? { collapsed_by_default: collapsed } : {}),
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
      {steps && (
        <Select label="Подраздел" value={step} onChange={(e) => setStep(e.target.value)}>
          {steps.map((id, index) => <option key={id ?? "first"} value={id ?? ""}>{index + 1}</option>)}
        </Select>
      )}
      {(material.kind === "text" || material.kind === "card") && <MarkdownEditor value={body} onChange={setBody} onBusyChange={setEditorBusy} />}
      {steps && material.kind === "card" && <CollapsedOption checked={collapsed} onChange={setCollapsed} />}
      {material.kind === "link" && <Field label="Ссылка" type="url" required value={url} onChange={(e) => setUrl(e.target.value)} />}
      {material.file && <p className="text-sm text-fg-soft">Файл: {material.file.filename}. Чтобы заменить файл, удалите материал и добавьте заново.</p>}
      <div className="flex gap-2">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Отмена
        </Button>
        <Button type="submit" loading={busy} disabled={editorBusy} className="flex-1">
          Сохранить
        </Button>
      </div>
    </form>
  );
}
