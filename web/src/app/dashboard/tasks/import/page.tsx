"use client";

import { ExternalLink, FileUp, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { TaskEditor } from "@/components/task-editor";
import { Alert, Button } from "@/components/ui";
import { ApiError, assessment, contentFileUrl, importEgeFile, uploadFile, type EgePdfDraft, type TaskInput } from "@/lib/api";
import { IMPORTED_TASKS_KEY } from "@/lib/imported-tasks";
import { errorText, useLoad } from "@/lib/hooks";

const IMAGE = /!\[Иллюстрация из PDF\]\(ege-pdf-image-(\d+)\)/g;
const EGE_FILE = /\[([^\]\n]+)\]\((https:\/\/(?:[a-z0-9-]+-)?(?:ege|oge)\.sdamgia\.ru\/get_file\?id=\d+)\)/g;
type Editor = { collect: () => TaskInput | null };

export default function ImportEgePage() {
  const { data: topics, error: topicsError, reload: reloadTopics } = useLoad(() => assessment.topics(), []);
  const [file, setFile] = useState<File>();
  const [drafts, setDrafts] = useState<EgePdfDraft[]>([]);
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>();
  const editors = useRef(new Map<number, Editor>());
  const uploaded = useRef(new Map<number, string>());
  const importedFiles = useRef(new Map<string, string>());

  async function parsePdf(event: React.FormEvent) {
    event.preventDefault();
    if (!file || busy) return;
    setError(undefined);
    if (file.size > 10 * 1024 * 1024) {
      setError("PDF должен занимать не больше 10 МБ");
      return;
    }
    setBusy(true);
    try {
      const { tasks, images } = await assessment.parseEgePdf(file);
      for (const [index, image] of images.entries()) {
        if (uploaded.current.has(index)) continue;
        const bytes = Uint8Array.from(atob(image), (char) => char.charCodeAt(0));
        const picture = new File([bytes], `ege-${index + 1}.png`, { type: "image/png" });
        uploaded.current.set(index, contentFileUrl((await uploadFile(picture, "content")).id));
      }
      const links = tasks.flatMap((task) => [task.statement, task.explanation].flatMap((text) => [...text.matchAll(EGE_FILE)]));
      for (const [, , url] of links) {
        if (importedFiles.current.has(url)) continue;
        try {
          importedFiles.current.set(url, contentFileUrl((await importEgeFile(url)).id));
        } catch (err) {
          const task = tasks.find((item) => item.statement.includes(url) || item.explanation.includes(url));
          throw new ApiError(422, "ege_file_import_failed", `Задача ${task?.number}: ${errorText(err)}. Повторите импорт.`);
        }
      }
      const replaceAssets = (text: string) => text.replace(IMAGE, (_, index: string) =>
        `![Иллюстрация из PDF](${uploaded.current.get(Number(index))})`,
      ).replace(EGE_FILE, (_, label: string, url: string) => `[📎 ${label}](${importedFiles.current.get(url)})`);
      setDrafts(tasks.map((task) => ({
        ...task, statement: replaceAssets(task.statement), explanation: replaceAssets(task.explanation),
      })));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function saveAll() {
    if (saving) return;
    setError(undefined);
    const tasks: TaskInput[] = [];
    for (const draft of drafts) {
      const task = editors.current.get(draft.number)?.collect();
      if (!task) {
        document.getElementById(`import-task-${draft.number}`)?.scrollIntoView({ block: "start" });
        return;
      }
      tasks.push(task);
    }
    setSaving(true);
    try {
      const saved = await assessment.saveEgeTasks(tasks);
      const selection = saved.map(({ id, title, type, subject_id, subject_name }) => ({ id, title, type, subject_id, subject_name }));
      try {
        sessionStorage.setItem(IMPORTED_TASKS_KEY, JSON.stringify(selection));
      } catch {
        // Задачи уже сохранены. Возвращаемся в банк и при недоступном хранилище браузера.
        router.replace("/dashboard/tasks");
        return;
      }
      router.replace("/dashboard/tasks?imported=1");
      return;
    } catch (err) {
      const fields = err instanceof ApiError && Array.isArray(err.details.fields) ? err.details.fields : [];
      const first = fields[0];
      const number = first ? /^(\d+)(?:\.|$)/.exec(first.field)?.[1] : undefined;
      const message = errorText(err).replace(/^Задача (\d+):/, (prefix, position: string) => {
        const draft = drafts[Number(position) - 1];
        return draft ? `Задача ${draft.number}:` : prefix;
      });
      setError(number !== undefined
        ? `Задача ${drafts[Number(number)]?.number ?? Number(number) + 1}: ${first.message.replace(/^Value error, /, "")}`
        : message);
      setSaving(false);
    }
  }

  function chooseFile(next?: File) {
    uploaded.current.clear();
    importedFiles.current.clear();
    setError(undefined);
    setFile(next);
  }

  function removeDraft(number: number) {
    setError(undefined);
    setDrafts((current) => current.filter((draft) => draft.number !== number));
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <Link href="/dashboard/tasks" className="text-sm text-brand-text hover:underline">← Банк задач</Link>
      <h1 className="text-2xl font-semibold tracking-tight">Импорт из «РЕШУ ОГЭ/ЕГЭ»</h1>
      {drafts.length ? (
        <>
          <p role="status" className="text-sm text-fg-soft">Задач в списке — {drafts.length}.</p>
          {topicsError && (
            <div className="space-y-2">
              <Alert>{topicsError}</Alert>
              <Button type="button" variant="secondary" onClick={reloadTopics}>Повторить загрузку рубрикатора</Button>
            </div>
          )}
          {topics && (
            <ol className="space-y-5">
              {drafts.map((draft) => (
                <li key={draft.number} id={`import-task-${draft.number}`} className="scroll-mt-24 space-y-4 rounded-2xl border border-line bg-surface p-5 sm:p-6">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
                    <h2 className="font-semibold">Задача {draft.number}</h2>
                    <div className="flex flex-wrap items-center gap-3">
                      <a href={draft.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-sm text-brand-text hover:underline">
                        {draft.source_name} <ExternalLink size={14} aria-hidden="true" />
                      </a>
                      <button type="button" disabled={saving} onClick={() => removeDraft(draft.number)}
                        aria-label={`Убрать из списка задачу ${draft.number}`}
                        className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm text-fg-soft hover:bg-muted hover:text-danger disabled:opacity-50">
                        <Trash2 size={15} aria-hidden="true" /> Убрать из списка
                      </button>
                    </div>
                  </div>
                  <fieldset disabled={saving}>
                    <TaskEditor imported={draft} importTopics={topics} batchRef={(editor) => {
                      if (editor) editors.current.set(draft.number, editor);
                      else editors.current.delete(draft.number);
                    }} />
                  </fieldset>
                </li>
              ))}
            </ol>
          )}
          {topics && (
            <div className="sticky bottom-3 z-10 space-y-2 rounded-2xl border border-line bg-surface p-3 shadow-sm">
              {error && <Alert>{error}</Alert>}
              <Button type="button" loading={saving} className="w-full" onClick={saveAll}>Сохранить все задачи</Button>
            </div>
          )}
        </>
      ) : (
        <form className="space-y-4 rounded-2xl border border-line bg-surface p-5 sm:p-6" onSubmit={parsePdf}>
          {error && <Alert>{error}</Alert>}
          <p className="rounded-xl bg-muted/50 px-4 py-3 text-sm text-fg-soft">
            На «РЕШУ ЕГЭ» или «РЕШУ ОГЭ» перед печатью отметьте{" "}
            <strong>«№№ заданий»</strong>, <strong>«Решения»</strong> и <strong>«Ответы»</strong>.
            Затем сохраните вариант как PDF и загрузите сюда.
          </p>
          <label className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed border-line bg-muted/50 px-5 py-8 text-center hover:border-brand focus-within:ring-2 focus-within:ring-brand/30">
            <span className="grid size-11 place-items-center rounded-xl bg-brand/10 text-brand-text">
              <FileUp size={22} aria-hidden="true" />
            </span>
            <span className="max-w-full break-all font-medium">{file?.name ?? "Выберите PDF"}</span>
            <span className="text-sm text-fg-soft">Печатный вариант с решениями · до 10 МБ</span>
            <input type="file" accept=".pdf,application/pdf" disabled={busy}
              onChange={(event) => chooseFile(event.target.files?.[0])}
              aria-label="Выберите PDF" className="sr-only" />
          </label>
          <Button type="submit" loading={busy} disabled={!file} className="w-full">Распознать задачи</Button>
        </form>
      )}
    </div>
  );
}
