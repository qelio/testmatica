"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { CodeEditor } from "@/components/code-editor";
import { AttachButton, AttachmentView, UploadChips, useUploads } from "@/components/files";
import { Markdown } from "@/components/markdown";
import { ReviewForm } from "@/components/review-form";
import { resultText } from "@/components/task-solver";
import { Alert, Badge, Button } from "@/components/ui";
import { assessment, type Attempt, type AttemptTask, type Submission } from "@/lib/api";
import { celebrateOnce } from "@/lib/confetti";
import { fmtDateTime } from "@/lib/dates";
import { FAILURE_LABELS, TASK_TYPE_LABELS } from "@/lib/format";
import { errorText } from "@/lib/hooks";

type Answer = Submission["answer"];

// ---------- таймер ----------

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

function fmtLeft(ms: number): string {
  const s = Math.max(0, Math.ceil(ms / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

/** Обратный отсчёт с поправкой на часы сервера. Когда время вышло — onExpire (сервер сдаст работу сам). */
function Countdown({ until, offset, label, onExpire }: { until: string; offset: number; label: string; onExpire: () => void }) {
  const now = useNow(true);
  const left = new Date(until).getTime() - (now + offset);
  const fired = useRef(false);
  useEffect(() => {
    if (left <= 0 && !fired.current) {
      fired.current = true;
      // Небольшая пауза: сервер даёт несколько секунд запаса на последний ответ.
      const t = setTimeout(onExpire, 6000);
      return () => clearTimeout(t);
    }
  }, [left, onExpire]);
  const urgent = left < 60_000;
  return (
    <span className={`rounded-lg px-3 py-1.5 font-mono text-lg tabular-nums ${urgent ? "bg-danger/10 text-danger" : "bg-muted"}`} role="timer" aria-label={label}>
      {fmtLeft(left)}
    </span>
  );
}

// ---------- ответы ----------

type SaveState = "idle" | "saving" | "saved" | "error";

function AnswerInput({
  item,
  onSave,
}: {
  item: AttemptTask;
  onSave: (answer: Answer, fileIds: string[]) => Promise<AttemptTask | undefined>;
}) {
  const task = item.task;
  const [selected, setSelected] = useState<string[]>(item.answer?.option_ids ?? []);
  const [text, setText] = useState(item.answer?.text ?? "");
  const [code, setCode] = useState(item.answer?.code ?? task.starter_code);
  const [files, setFiles] = useState(item.files);
  const uploads = useUploads("answer", 5);
  const [state, setState] = useState<SaveState>(item.answer ? "saved" : "idle");
  const [error, setError] = useState<string>();
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  async function save(answer: Answer, fileIds = files.map((f) => f.id)) {
    setState("saving");
    try {
      const saved = await onSave(answer, fileIds);
      if (saved && task.type === "long") {
        // Сервер вернул прикреплённые файлы — дальше храним их как часть черновика.
        setFiles(saved.files);
        uploads.clear();
        lastUploaded.current = "";
      }
      setState("saved");
      setError(undefined);
    } catch (e) {
      setState("error");
      setError(errorText(e));
    }
  }
  function later(answer: Answer) {
    clearTimeout(timer.current);
    setState("saving");
    timer.current = setTimeout(() => save(answer), 800);
  }
  useEffect(() => () => clearTimeout(timer.current), []);

  // Файл загрузился — сохраняем черновик вместе с ним.
  const uploadedKey = uploads.ids.join(",");
  const lastUploaded = useRef("");
  useEffect(() => {
    if (!uploadedKey || uploadedKey === lastUploaded.current) return;
    lastUploaded.current = uploadedKey;
    void save({ text }, [...files.map((f) => f.id), ...uploads.ids]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uploadedKey]);

  return (
    <div className="space-y-2">
      {task.type === "choice" && (
        <fieldset className="space-y-2">
          <legend className="mb-1 text-sm text-fg-soft">{task.multiple ? "Выберите все верные варианты" : "Выберите один вариант"}</legend>
          {task.options.map((o) => (
            <label key={o.id} className={`flex cursor-pointer items-start gap-3 rounded-xl border px-4 py-3 ${selected.includes(o.id) ? "border-brand bg-brand/5" : "border-line hover:bg-muted"}`}>
              <input
                type={task.multiple ? "checkbox" : "radio"}
                name={`task-${task.id}`}
                checked={selected.includes(o.id)}
                onChange={(e) => {
                  const next = task.multiple ? (e.target.checked ? [...selected, o.id] : selected.filter((x) => x !== o.id)) : [o.id];
                  setSelected(next);
                  void save({ option_ids: next });
                }}
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
          maxLength={500}
          onChange={(e) => {
            setText(e.target.value);
            later({ text: e.target.value });
          }}
          placeholder="Ваш ответ"
          aria-label="Ответ"
          className="h-11 w-full max-w-sm rounded-xl border border-line bg-surface px-3.5 outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
        />
      )}
      {task.type === "long" && (
        <div className="space-y-2">
          <textarea
            rows={6}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              later({ text: e.target.value });
            }}
            placeholder="Ваше решение"
            aria-label="Решение"
            className="w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
          />
          {task.file_mode !== "none" && (
            <div className="flex flex-wrap items-center gap-2">
              {files.map((f) => (
                <span key={f.id} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2 py-1 text-sm">
                  {f.filename}
                  <button
                    type="button"
                    className="text-fg-soft hover:text-danger"
                    aria-label={`Убрать ${f.filename}`}
                    onClick={() => {
                      const rest = files.filter((x) => x.id !== f.id);
                      setFiles(rest);
                      void save({ text }, rest.map((x) => x.id));
                    }}
                  >
                    ✕
                  </button>
                </span>
              ))}
              <AttachButton onFiles={uploads.add} label="Прикрепить файл с решением" />
              <span className="text-sm text-fg-soft">{task.file_mode === "required" ? "Файл обязателен" : "Можно прикрепить файл"}</span>
              <UploadChips items={uploads.items.filter((u) => u.status !== "done")} onRemove={uploads.remove} />
            </div>
          )}
        </div>
      )}
      {task.type === "code" && (
        <div className="space-y-1">
          <CodeEditor
            value={code}
            onChange={(v) => {
              setCode(v);
              later({ code: v });
            }}
            minHeight="200px"
          />
          <p className="text-xs text-fg-soft">
            Python · лимит {task.time_limit_s} с, {task.memory_limit_mb} МБ · проверка тестами — после сдачи работы
          </p>
        </div>
      )}
      <p className="h-5 text-xs text-fg-soft" aria-live="polite">
        {state === "saving" ? "Сохраняю…" : state === "saved" ? "Ответ сохранён" : state === "error" ? <span className="text-danger">{error}</span> : ""}
      </p>
    </div>
  );
}

/** Ответ после сдачи: что выбрал/написал ученик, для педагога — с правильными вариантами. */
function AnswerReadonly({ item, teacher }: { item: AttemptTask; teacher: boolean }) {
  const { task, answer } = item;
  if (!answer && !item.files.length) return <p className="text-sm text-fg-soft">Нет ответа</p>;
  return (
    <div className="space-y-2">
      {task.type === "choice" && (
        <ul className="space-y-1.5">
          {task.options.map((o) => {
            const chosen = answer?.option_ids?.includes(o.id);
            return (
              <li
                key={o.id}
                className={`flex items-start gap-2 rounded-lg border px-3 py-2 ${chosen ? "border-brand bg-brand/5" : "border-line"} ${teacher && o.is_correct ? "ring-1 ring-ok/60" : ""}`}
              >
                <span className="w-16 shrink-0 text-xs text-fg-soft">
                  {chosen ? "выбрано" : ""}
                  {teacher && o.is_correct ? <span className="block text-ok">верный</span> : null}
                </span>
                <span className="min-w-0 flex-1">
                  <Markdown text={o.text} />
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {(task.type === "short" || task.type === "long") && answer?.text && (
        <p className="rounded-lg bg-muted px-3 py-2 whitespace-pre-wrap">{answer.text}</p>
      )}
      {teacher && task.type === "short" && task.answers && (
        <p className="text-sm text-fg-soft">
          Правильные ответы: {task.answers.map((a) => (a.mode === "regex" ? `/${a.value}/` : a.value)).join(", ")}
        </p>
      )}
      {item.files.map((f) => (
        <AttachmentView key={f.id} att={f} />
      ))}
      {task.type === "code" && answer?.code && <CodeEditor value={answer.code} readOnly minHeight="60px" />}
    </div>
  );
}

function RunLog({ sub }: { sub: Submission }) {
  if (!sub.run_log?.length) return null;
  return (
    <details>
      <summary className="cursor-pointer text-sm text-brand">Протокол тестов</summary>
      <table className="mt-1.5 w-full text-sm">
        <tbody>
          {sub.run_log.map((c) => (
            <tr key={c.number} className="border-t border-line align-top">
              <td className="py-1 pr-3">№{c.number}</td>
              <td className={`py-1 pr-3 ${c.status === "passed" ? "text-ok" : "text-danger"}`}>
                {c.status === "passed" ? "пройден" : (FAILURE_LABELS[c.status as keyof typeof FAILURE_LABELS] ?? c.status)}
              </td>
              <td className="py-1 pr-3 text-fg-soft">{c.time_ms} мс</td>
              <td className="py-1 font-mono text-xs whitespace-pre-wrap">{c.error || c.output}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

// ---------- экран попытки ----------

export function AttemptView({ attempt, teacher, reload }: { attempt: Attempt; teacher: boolean; reload: () => void }) {
  // Поправка на расхождение часов ученика и сервера — для точного таймера.
  const [offset] = useState(() => new Date(attempt.server_time).getTime() - Date.now());
  const inProgress = attempt.status === "in_progress";
  const checking = attempt.tasks.some((t) => t.result?.status === "checking");

  // Пока идёт проверка кода — обновляем результат.
  useEffect(() => {
    if (!checking) return;
    const t = setInterval(reload, 2000);
    return () => clearInterval(t);
  }, [checking, reload]);

  if (inProgress && !teacher) return <Solving attempt={attempt} offset={offset} reload={reload} />;

  return (
    <div className="space-y-5">
      <ResultHeader attempt={attempt} teacher={teacher} />
      <ol className="space-y-4">
        {attempt.tasks.map((item, i) => (
          <li key={item.task.id} className="space-y-3 rounded-2xl border border-line bg-surface p-5">
            <TaskHead item={item} n={i + 1} />
            <Markdown text={item.task.statement} />
            <AnswerReadonly item={item} teacher={teacher} />
            {item.result && (
              <div className="space-y-2 border-t border-line pt-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={resultText(item.result).tone}>{resultText(item.result).text}</Badge>
                  {item.earned !== null && (
                    <span className="text-sm text-fg-soft">
                      {item.earned} из {item.points} б.
                    </span>
                  )}
                  {teacher && item.result.status === "error" && (
                    <Button
                      variant="secondary"
                      className="h-8"
                      onClick={async () => {
                        await assessment.recheck(item.result!.id);
                        reload();
                      }}
                    >
                      Перепроверить
                    </Button>
                  )}
                </div>
                {item.result.teacher_comment && <p className="text-sm">Комментарий педагога: {item.result.teacher_comment}</p>}
                {teacher && <RunLog sub={item.result} />}
                {teacher && item.task.type === "long" && <ReviewForm sub={item.result} onChanged={reload} />}
              </div>
            )}
            {!item.result && !inProgress && <p className="border-t border-line pt-3 text-sm text-fg-soft">Без ответа — 0 баллов</p>}
            {!inProgress && item.task.explanation && (
              <details className="rounded-xl border border-ok/40 bg-ok/5 px-4 py-3">
                <summary className="cursor-pointer font-medium">Разбор решения</summary>
                <div className="mt-2">
                  <Markdown text={item.task.explanation} />
                </div>
              </details>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

function TaskHead({ item, n }: { item: AttemptTask; n: number }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="font-semibold">Задание {n}</span>
      <Badge>{TASK_TYPE_LABELS[item.task.type]}</Badge>
      <span className="text-fg-soft">
        {item.points} {item.points === 1 ? "балл" : item.points < 5 ? "балла" : "баллов"}
      </span>
    </div>
  );
}

function ResultHeader({ attempt, teacher }: { attempt: Attempt; teacher: boolean }) {
  const excellent = !teacher && attempt.checked && (attempt.percent ?? 0) >= 90;
  useEffect(() => {
    if (excellent) celebrateOnce(`attempt:${attempt.id}`); // отличный результат — праздник один раз
  }, [excellent, attempt.id]);
  if (attempt.status === "in_progress") {
    return <Alert kind="info">Ученик ещё решает — здесь видны его текущие ответы.</Alert>;
  }
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-2xl border border-line bg-surface px-5 py-4">
      {attempt.checked ? (
        <>
          <span className="text-3xl font-semibold">{attempt.grade}</span>
          <span>
            {attempt.score} из {attempt.max_score} баллов · {Math.round(attempt.percent ?? 0)}%
          </span>
        </>
      ) : (
        <span>
          {teacher
            ? "Итог появится, когда всё будет проверено: код проверяется автоматически, развёрнутые ответы — вами."
            : "Работа сдана. Итог появится после проверки."}
        </span>
      )}
      <span className="text-sm text-fg-soft">
        сдана {attempt.submitted_at ? fmtDateTime(attempt.submitted_at) : ""}
        {attempt.auto_submitted && " автоматически (время вышло)"}
      </span>
    </div>
  );
}

function Solving({ attempt, offset, reload }: { attempt: Attempt; offset: number; reload: () => void }) {
  const perTask = attempt.settings.time_mode === "per_task";
  const visible = perTask ? attempt.tasks.filter((t) => !t.locked) : attempt.tasks;
  const [answered, setAnswered] = useState(() => new Set(attempt.tasks.filter((t) => t.answer || t.files.length).map((t) => t.task.id)));
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const total = attempt.tasks.length;

  async function saveAnswer(taskId: string, answer: Answer, fileIds: string[]) {
    try {
      const res = await assessment.saveAnswer(attempt.id, taskId, answer, fileIds);
      if (res.status !== "in_progress") reload();
      setAnswered((s) => new Set(s).add(taskId));
      return res.tasks.find((t) => t.task.id === taskId);
    } catch (e) {
      // Время вышло или задание закрылось — показать актуальное состояние.
      reload();
      throw e;
    }
  }

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(undefined);
    try {
      await action();
      reload();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const last = perTask && attempt.current_index >= attempt.tasks.length - 1;
  const firstNumber = perTask ? attempt.current_index + 1 : 1;

  return (
    <div className="space-y-5">
      <div className="sticky top-0 z-10 -mx-4 flex flex-wrap items-center gap-3 border-b border-line bg-bg/95 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-2xl sm:border">
        <span className="text-sm text-fg-soft">
          {perTask ? `Задание ${attempt.current_index + 1} из ${total}` : `Отвечено: ${answered.size} из ${total}`}
        </span>
        <span className="ml-auto flex items-center gap-2">
          {attempt.current_ends_at && <Countdown until={attempt.current_ends_at} offset={offset} label="Осталось на задание" onExpire={reload} />}
          {attempt.ends_at && <Countdown until={attempt.ends_at} offset={offset} label="Осталось времени" onExpire={reload} />}
        </span>
      </div>
      {error && <Alert>{error}</Alert>}
      <ol className="space-y-4">
        {visible.map((item, i) => (
          <li key={item.task.id} className="space-y-3 rounded-2xl border border-line bg-surface p-5">
            <TaskHead item={item} n={firstNumber + i} />
            <Markdown text={item.task.statement} />
            <AnswerInput item={item} onSave={(answer, fileIds) => saveAnswer(item.task.id, answer, fileIds)} />
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
        {perTask && !last ? (
          <Button
            loading={busy}
            onClick={() => window.confirm("Перейти к следующему заданию? Вернуться к этому будет нельзя.") && act(() => assessment.nextTask(attempt.id))}
          >
            Следующее задание →
          </Button>
        ) : (
          <Button
            loading={busy}
            onClick={() => {
              const missing = total - answered.size;
              const warn = missing > 0 && !perTask ? `Без ответа заданий: ${missing}. ` : "";
              if (window.confirm(`${warn}Сдать работу? Изменить ответы после сдачи будет нельзя.`)) act(() => assessment.submitAttempt(attempt.id));
            }}
          >
            Сдать работу
          </Button>
        )}
        <Link href={`/dashboard/assignments/${attempt.assignment_id}`} className="text-sm text-fg-soft hover:text-fg">
          Вернуться позже — ответы сохранены
        </Link>
      </div>
    </div>
  );
}
