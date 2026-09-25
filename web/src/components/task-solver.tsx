"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { CodeEditor } from "@/components/code-editor";
import { AttachButton, AttachmentView, UploadChips, useUploads } from "@/components/files";
import { Markdown } from "@/components/markdown";
import { Alert, Badge, Button, Spinner } from "@/components/ui";
import { assessment, type SolveView, type Submission } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/dates";
import { DIFFICULTY_LABELS, FAILURE_LABELS, TASK_TYPE_LABELS } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

export function resultText(s: Submission): { text: string; tone: "ok" | "warn" | "neutral" | "brand" } {
  switch (s.status) {
    case "correct":
      return { text: "Верно", tone: "ok" };
    case "incorrect":
      return s.failed_case
        ? { text: `Тест №${s.failed_case}: ${s.failure ? FAILURE_LABELS[s.failure] : "ошибка"}`, tone: "warn" }
        : { text: "Неверно", tone: "warn" };
    case "checking":
      return { text: "Проверяется…", tone: "brand" };
    case "error":
      return { text: "Не удалось проверить — отправьте ещё раз", tone: "neutral" };
    case "pending_review":
      return { text: "Ждёт проверки педагогом", tone: "brand" };
    case "reviewed":
      return { text: `Проверено: ${Math.round((s.score ?? 0) * 100)}%`, tone: (s.score ?? 0) >= 0.5 ? "ok" : "warn" };
  }
}

/** Решение задачи прямо на странице (задача в модуле курса). */
export function TaskSolver({
  taskId,
  contextId,
  contextType = "practice",
}: {
  taskId: string;
  contextId: string;
  contextType?: "practice" | "assignment";
}) {
  const { status } = useAuth();
  const view = useLoad(() => assessment.solve(taskId, contextId, contextType), [taskId, contextId, status]);
  if (view.error) return <Alert>{view.error}</Alert>;
  if (!view.data) return <Spinner />;
  return <Solver key={view.data.task.id} view={view.data} reload={view.reload} contextId={contextId} contextType={contextType} />;
}

function Solver({
  view,
  reload,
  contextId,
  contextType,
}: {
  view: SolveView;
  reload: () => void;
  contextId: string;
  contextType: "practice" | "assignment";
}) {
  const { status } = useAuth();
  const task = view.task;
  const last = view.submissions[0];
  const [selected, setSelected] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [code, setCode] = useState(last?.answer.code ?? task.starter_code);
  const uploads = useUploads("answer", 5);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const checking = view.submissions.some((s) => s.status === "checking");

  // Пока код проверяется в песочнице — опрашиваем статус.
  useEffect(() => {
    if (!checking) return;
    const t = setInterval(reload, 1200);
    return () => clearInterval(t);
  }, [checking, reload]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const answer =
        task.type === "choice" ? { option_ids: selected } : task.type === "code" ? { code } : { text };
      await assessment.answer(task.id, contextId, answer, uploads.ids, contextType);
      if (task.type !== "code") {
        setText("");
        uploads.clear();
      }
      reload();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const disabled =
    busy ||
    checking ||
    uploads.busy ||
    (task.type === "choice" && !selected.length) ||
    (task.type === "short" && !text.trim()) ||
    (task.type === "code" && !code.trim()) ||
    (task.type === "long" && !text.trim() && !uploads.ids.length) ||
    (task.type === "long" && task.file_mode === "required" && !uploads.ids.length);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge tone="brand">{TASK_TYPE_LABELS[task.type]}</Badge>
        <Badge>{DIFFICULTY_LABELS[task.difficulty]}</Badge>
        {view.solved && <Badge tone="ok">решено ✓</Badge>}
      </div>
      <Markdown text={task.statement} />

      {status !== "authenticated" ? (
        <Alert kind="info">
          Чтобы решить задачу, <Link href="/login" className="font-medium underline">войдите</Link> или{" "}
          <Link href="/register" className="font-medium underline">зарегистрируйтесь</Link>.
        </Alert>
      ) : (
        <form onSubmit={submit} className="space-y-3">
          {error && <Alert>{error}</Alert>}
          {task.type === "choice" && (
            <fieldset className="space-y-2">
              <legend className="mb-1 text-sm text-fg-soft">{task.multiple ? "Выберите все верные варианты" : "Выберите один вариант"}</legend>
              {task.options.map((o) => (
                <label key={o.id} className={`flex cursor-pointer items-start gap-3 rounded-xl border px-4 py-3 ${selected.includes(o.id) ? "border-brand bg-brand/5" : "border-line hover:bg-muted"}`}>
                  <input
                    type={task.multiple ? "checkbox" : "radio"}
                    name={`task-${task.id}`}
                    checked={selected.includes(o.id)}
                    onChange={(e) =>
                      setSelected(task.multiple ? (e.target.checked ? [...selected, o.id] : selected.filter((x) => x !== o.id)) : [o.id])
                    }
                    className="mt-1 accent-brand"
                  />
                  <span className="min-w-0 flex-1">
                    <Markdown text={o.text} />
                  </span>
                </label>
              ))}
            </fieldset>
          )}
          {task.type === "short" && (
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Ваш ответ"
              aria-label="Ответ"
              maxLength={500}
              className="h-11 w-full max-w-sm rounded-xl border border-line bg-surface px-3.5 outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
            />
          )}
          {task.type === "long" && (
            <div className="space-y-2">
              <textarea
                rows={6}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Ваше решение"
                aria-label="Решение"
                className="w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
              />
              {task.file_mode !== "none" && (
                <div className="flex flex-wrap items-center gap-2">
                  <AttachButton onFiles={uploads.add} label="Прикрепить файл с решением" />
                  <span className="text-sm text-fg-soft">{task.file_mode === "required" ? "Файл обязателен" : "Можно прикрепить файл"}</span>
                  <UploadChips items={uploads.items} onRemove={uploads.remove} />
                </div>
              )}
            </div>
          )}
          {task.type === "code" && (
            <div className="space-y-1">
              <CodeEditor value={code} onChange={setCode} minHeight="220px" />
              <p className="text-xs text-fg-soft">
                Python · лимит {task.time_limit_s} с, {task.memory_limit_mb} МБ · чтение — input(), вывод — print()
              </p>
            </div>
          )}
          <Button type="submit" loading={busy || checking} disabled={disabled}>
            {task.type === "code" ? "Отправить на проверку" : "Ответить"}
          </Button>
        </form>
      )}

      {view.explanation && (
        <details className="rounded-xl border border-ok/40 bg-ok/5 px-4 py-3" open={view.solved}>
          <summary className="cursor-pointer font-medium">Разбор решения</summary>
          <div className="mt-2">
            <Markdown text={view.explanation} />
          </div>
        </details>
      )}

      {view.submissions.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-medium text-fg-soft">Мои попытки</h3>
          <ul className="space-y-1.5">
            {view.submissions.slice(0, 10).map((s) => {
              const r = resultText(s);
              return (
                <li key={s.id} className="rounded-lg bg-muted px-3 py-2 text-sm">
                  <div className="flex items-center justify-between gap-3">
                    <Badge tone={r.tone}>{r.text}</Badge>
                    <span className="text-xs text-fg-soft">{fmtDateTime(s.created_at)}</span>
                  </div>
                  {s.answer.text && <p className="mt-1 text-fg-soft">«{s.answer.text}»</p>}
                  {s.teacher_comment && <p className="mt-1">Комментарий педагога: {s.teacher_comment}</p>}
                  {s.files.map((f) => (
                    <div key={f.id} className="mt-1.5">
                      <AttachmentView att={f} />
                    </div>
                  ))}
                  {s.answer.code && (
                    <details className="mt-1">
                      <summary className="cursor-pointer text-xs text-brand">Код этой попытки</summary>
                      <div className="mt-1">
                        <CodeEditor value={s.answer.code} readOnly minHeight="60px" />
                      </div>
                    </details>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
