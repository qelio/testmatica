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

/** Проверка кода по кнопке (решение №49): сколько угодно раз, ученик видит только, сколько тестов не прошло. */
function CodeCheckButton({ attemptId, item, code, beforeCheck }: { attemptId: string; item: AttemptTask; code: string; beforeCheck: () => void }) {
  const [check, setCheck] = useState(item.check);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const checking = check?.status === "checking";

  // Пока песочница проверяет — спрашиваем результат.
  useEffect(() => {
    if (!checking) return;
    const t = setInterval(async () => {
      try {
        const fresh = await assessment.attempt(attemptId);
        setCheck(fresh.tasks.find((x) => x.task.id === item.task.id)?.check ?? null);
      } catch {
        // сеть мигнула — спросим ещё раз
      }
    }, 2000);
    return () => clearInterval(t);
  }, [checking, attemptId, item.task.id]);

  async function run() {
    beforeCheck();
    setBusy(true);
    setError(undefined);
    try {
      const res = await assessment.checkCode(attemptId, item.task.id, code);
      setCheck(res.tasks.find((x) => x.task.id === item.task.id)?.check ?? null);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  let text: React.ReactNode = null;
  if (checking) text = <span className="text-fg-soft">Проверяю…</span>;
  else if (check?.status === "error") text = <span className="text-danger">Не удалось проверить — попробуйте ещё раз</span>;
  else if (check?.status === "correct") text = <span className="text-ok">Все тесты пройдены ✓</span>;
  else if (check?.status === "incorrect")
    text = (
      <span className="text-danger">
        Не прошли тесты: {check.failed} из {check.total}
      </span>
    );

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <Button type="button" variant="secondary" onClick={run} loading={busy || checking} disabled={!code.trim()} className="h-9">
        Проверить
      </Button>
      <span className="text-sm" aria-live="polite">
        {text}
      </span>
      {check && check.count > 0 && (
        <span className="text-xs text-fg-soft">
          проверок: {check.count}
          {check.passed_once && check.status !== "correct" && " · уже было решено верно — это и засчитается"}
        </span>
      )}
      {error && <span className="w-full text-sm text-danger">{error}</span>}
    </div>
  );
}

function AnswerInput({
  item,
  attemptId,
  onSave,
}: {
  item: AttemptTask;
  attemptId: string;
  onSave: (answer: Answer, fileIds: string[]) => Promise<AttemptTask | undefined>;
}) {
  const task = item.task;
  const [selected, setSelected] = useState<string[]>(item.answer?.option_ids ?? []);
  const [text, setText] = useState(item.answer?.text ?? "");
  const [code, setCode] = useState(item.answer?.code ?? task.starter_code);
  const [files, setFiles] = useState(item.files);
  const uploads = useUploads("answer", 5);
  const [state, setState] = useState<SaveState>(item.answer || item.files.length ? "saved" : "idle");
  const [error, setError] = useState<string>();
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  // Файлы: развёрнутый ответ (если задача разрешает) или файл с решением, который запросил педагог.
  const withFiles = (task.type === "long" && task.file_mode !== "none") || item.solution_file;

  function current(): Answer {
    if (task.type === "choice") return { option_ids: selected };
    if (task.type === "code") return { code };
    return { text };
  }

  async function save(answer: Answer, fileIds = files.map((f) => f.id)) {
    setState("saving");
    try {
      const saved = await onSave(answer, fileIds);
      if (saved && withFiles) {
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
    void save(current(), [...files.map((f) => f.id), ...uploads.ids]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uploadedKey]);

  return (
    <div className="space-y-2">
      {task.type === "choice" && (
        <fieldset className="space-y-2">
          <legend className="mb-1 text-sm text-fg-soft">{task.multiple ? "Выберите все верные варианты" : "Выберите один вариант"}</legend>
          {task.options.map((o) => (
            <label key={o.id} className={`tm-opt flex cursor-pointer items-start gap-3 rounded-xl border px-4 py-3 ${selected.includes(o.id) ? "tm-opt-on border-brand bg-brand/5" : "border-line hover:bg-muted"}`}>
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
            Python ·{" "}
            {item.code_check === "manual"
              ? "код проверит педагог"
              : `лимит ${task.time_limit_s} с, ${task.memory_limit_mb} МБ · ${
                  item.code_check === "live"
                    ? "проверяйте сколько угодно раз — в оценку пойдёт лучшая проверка"
                    : "проверка тестами — после сдачи работы"
                }`}
          </p>
          {item.code_check === "live" && (
            <CodeCheckButton attemptId={attemptId} item={item} code={code} beforeCheck={() => clearTimeout(timer.current)} />
          )}
        </div>
      )}
      {withFiles && (
        <div className={`flex flex-wrap items-center gap-2 ${item.solution_file ? "rounded-xl border border-dashed border-line px-3 py-2.5" : ""}`}>
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
                  void save(current(), rest.map((x) => x.id));
                }}
              >
                ✕
              </button>
            </span>
          ))}
          <AttachButton onFiles={uploads.add} label="Прикрепить файл с решением" />
          <span className="text-sm text-fg-soft">
            {item.solution_file
              ? "Нужно прикрепить фото или файл с ходом решения — его проверит педагог"
              : task.file_mode === "required"
                ? "Файл обязателен"
                : "Можно прикрепить файл"}
          </span>
          <UploadChips items={uploads.items.filter((u) => u.status !== "done")} onRemove={uploads.remove} />
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
  // Выбранный вариант после проверки — зелёный или красный (виден в игровом оформлении).
  const checked = ["correct", "incorrect", "reviewed"].includes(item.result?.status ?? "");
  const verdict = checked ? (isCorrect(item) ? "tm-opt-ok" : "tm-opt-bad") : "";
  return (
    <div className="space-y-2">
      {task.type === "choice" && (
        <ul className="space-y-1.5">
          {task.options.map((o) => {
            const chosen = answer?.option_ids?.includes(o.id);
            return (
              <li
                key={o.id}
                className={`tm-opt flex items-start gap-2 rounded-lg border px-3 py-2 ${chosen ? `tm-opt-on ${verdict} border-brand bg-brand/5` : "border-line"} ${teacher && o.is_correct ? "ring-1 ring-ok/60" : ""}`}
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

  // Проверка педагогом: какие задания он засчитал или нет (только изменённые).
  const [marks, setMarks] = useState<Record<string, boolean>>({});
  // Самостоятельную работу (решение №44) педагоги ученика только смотрят.
  const reviewing = teacher && attempt.status === "submitted" && !attempt.self_study;

  if (inProgress && !teacher) return <Solving attempt={attempt} offset={offset} reload={reload} />;

  return (
    <div className="space-y-5">
      <ResultHeader attempt={attempt} teacher={teacher} />
      {reviewing && (
        <TeacherReview
          key={`${attempt.reviewed_at}-${attempt.grade_override}`}
          attempt={attempt}
          marks={marks}
          onSaved={() => {
            setMarks({});
            reload();
          }}
        />
      )}
      <ol className="space-y-4">
        {attempt.tasks.map((item, i) => (
          <li key={item.task.id} className="tm-card space-y-3 rounded-2xl border border-line bg-surface p-5">
            <TaskHead item={item} n={i + 1} />
            <Markdown text={item.task.statement} />
            <AnswerReadonly item={item} teacher={teacher} />
            {teacher && item.check && (
              <p className="text-xs text-fg-soft">
                Проверял по кнопке «Проверить»: {item.check.count} раз
                {item.check.passed_once ? " · хоть раз прошёл все тесты" : " · все тесты ни разу не прошли"}
              </p>
            )}
            {item.result && (
              <div className="space-y-2 border-t border-line pt-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={resultText(item.result).tone}>
                    {/* В работе результат — в баллах (рядом), а не в процентах. */}
                    {item.result.status === "reviewed" ? "Проверено" : resultText(item.result).text}
                  </Badge>
                  {item.earned !== null && (
                    <span className="text-sm text-fg-soft">
                      {item.earned} из {item.points} б.
                    </span>
                  )}
                  {item.result.reviewed_at && item.task.type !== "long" && <span className="text-xs text-fg-soft">решение педагога</span>}
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
                {teacher && item.task.type === "long" && <ReviewForm sub={item.result} points={item.points} onChanged={reload} />}
              </div>
            )}
            {!item.result && !inProgress && !attempt.results_hidden && (
              <p className="border-t border-line pt-3 text-sm text-fg-soft">Без ответа — 0 баллов</p>
            )}
            {reviewing && item.task.type !== "long" && (
              <CountToggle
                value={marks[item.task.id] ?? isCorrect(item)}
                changed={item.task.id in marks}
                onChange={(v) =>
                  setMarks((m) => {
                    const next = { ...m };
                    if (v === isCorrect(item)) delete next[item.task.id];
                    else next[item.task.id] = v;
                    return next;
                  })
                }
              />
            )}
            {!inProgress && item.task.explanation && (
              <details className="tm-expl rounded-xl border border-ok/40 bg-ok/5 px-4 py-3">
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

function isCorrect(item: AttemptTask): boolean {
  const r = item.result;
  return !!r && (r.status === "correct" || (r.status === "reviewed" && (r.score ?? 0) >= 1));
}

function gradeFor(percent: number, scale: Attempt["grade_scale"]): number {
  return percent >= scale["5"] ? 5 : percent >= scale["4"] ? 4 : percent >= scale["3"] ? 3 : 2;
}

/** Засчитать задание или нет — педагог может изменить и автоматическую проверку. */
function CountToggle({ value, changed, onChange }: { value: boolean; changed: boolean; onChange: (v: boolean) => void }) {
  const btn = (active: boolean, tone: string) =>
    `rounded-lg border px-3 py-1.5 text-sm ${active ? tone : "border-line text-fg-soft hover:text-fg"}`;
  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3" role="radiogroup" aria-label="Засчитать задание">
      <span className="text-sm text-fg-soft">Ваше решение:</span>
      <button type="button" role="radio" aria-checked={value} onClick={() => onChange(true)} className={btn(value, "border-ok bg-ok/10 text-ok")}>
        ✓ Верно
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={!value}
        onClick={() => onChange(false)}
        className={btn(!value, "border-danger bg-danger/10 text-danger")}
      >
        ✗ Неверно
      </button>
      {changed && <span className="text-xs text-brand">изменено — сохраните проверку</span>}
    </div>
  );
}

/** Итог проверки педагогом: пересчёт с его отметками, оценка по критериям или своя, подтверждение. */
function TeacherReview({ attempt, marks, onSaved }: { attempt: Attempt; marks: Record<string, boolean>; onSaved: () => void }) {
  const [grade, setGrade] = useState(attempt.grade_override ? String(attempt.grade_override) : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const earned = attempt.tasks.reduce((n, t) => n + (t.task.id in marks ? (marks[t.task.id] ? t.points : 0) : (t.earned ?? 0)), 0);
  const percent = attempt.max_score ? (earned / attempt.max_score) * 100 : 0;
  const auto = gradeFor(percent, attempt.grade_scale);
  const changes = Object.keys(marks).length;
  const gradeChanged = (grade ? Number(grade) : null) !== attempt.grade_override;
  const confirm = attempt.needs_review && !attempt.reviewed_at;
  const pendingLong = attempt.tasks.filter((t) => t.result?.status === "pending_review" && t.task.type === "long").length;
  const pendingCode = attempt.tasks.filter((t) => t.result?.status === "pending_review" && t.task.type === "code").length;
  const s = attempt.grade_scale;

  async function save() {
    setBusy(true);
    setError(undefined);
    try {
      await assessment.reviewAttempt(attempt.id, marks, grade ? Number(grade) : null);
      onSaved();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-2xl border border-brand/40 bg-surface px-5 py-4">
      {error && <Alert>{error}</Alert>}
      <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
        <div className="min-w-0 flex-1 text-sm">
          <p className="font-medium">
            {confirm ? "Проверьте решения и подтвердите — тогда ученик увидит итог" : "Проверка работы"}
          </p>
          <p className="text-fg-soft">
            {earned} из {attempt.max_score} б. · {Math.round(percent)}% · по критериям — {auto} (5 от {s["5"]}%, 4 от {s["4"]}%, 3 от {s["3"]}%)
          </p>
          {pendingLong > 0 && <p className="text-tutor">Развёрнутых ответов ждут оценки: {pendingLong} — оцените их в карточках ниже.</p>}
          {pendingCode > 0 && <p className="text-tutor">Код ждёт вашей проверки: {pendingCode} — отметьте «Верно» или «Неверно» ниже.</p>}
        </div>
        <label className="text-sm">
          <span className="mb-1 block font-medium">Оценка</span>
          <select
            value={grade}
            onChange={(e) => setGrade(e.target.value)}
            className="h-10 rounded-xl border border-line bg-surface px-3 outline-none focus:border-brand"
          >
            <option value="">По критериям: {auto}</option>
            {[5, 4, 3, 2, 1].map((g) => (
              <option key={g} value={g}>
                {g} — вручную
              </option>
            ))}
          </select>
        </label>
        <Button onClick={save} loading={busy} disabled={!confirm && !changes && !gradeChanged} className="h-10">
          {confirm ? "Подтвердить проверку" : "Сохранить проверку"}
        </Button>
      </div>
    </div>
  );
}

function TaskHead({ item, n }: { item: AttemptTask; n: number }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="tm-title flex items-center gap-2 font-semibold">
        {/* В игровом оформлении номер — в кружке, в классике — текстом. */}
        <span className="tm-only tm-num">{n}</span>
        Задание<span className="tm-dot"> {n}</span>
      </span>
      <Badge>{TASK_TYPE_LABELS[item.task.type]}</Badge>
      {item.solution_file && <Badge tone="warn">нужен файл с решением</Badge>}
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
  const correct = attempt.tasks.filter(isCorrect).length;
  return (
    <div className="tm-card flex flex-wrap items-center gap-x-5 gap-y-2 rounded-2xl border border-line bg-surface px-5 py-4">
      {attempt.self_study && !attempt.checked ? (
        <span>
          Работа сдана. Верно: {correct} из {attempt.tasks.length}. Это самостоятельное прохождение — развёрнутые ответы и файлы
          педагог не проверяет, сверьтесь с разбором решений.
        </span>
      ) : attempt.results_hidden ? (
        <span>Работа сдана. Результаты и оценку вы увидите, когда педагог проверит работу.</span>
      ) : attempt.checked ? (
        <>
          <span className="tm-grade text-3xl font-semibold">{attempt.grade}</span>
          <span>
            {attempt.score} из {attempt.max_score} баллов · {Math.round(attempt.percent ?? 0)}%
            {attempt.grade_override !== null && <span className="text-fg-soft"> · оценку поставил педагог</span>}
          </span>
        </>
      ) : attempt.needs_review ? (
        <span>
          {teacher
            ? "Ученик прикладывал файлы с решением — посмотрите их и подтвердите проверку. До этого ученик не видит итог и оценку."
            : `Работа сдана. Верно: ${correct} из ${attempt.tasks.length}. Итоговую оценку педагог поставит после проверки решений.`}
        </span>
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
  const [withFile, setWithFile] = useState(() => new Set(attempt.tasks.filter((t) => t.files.length).map((t) => t.task.id)));
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const total = attempt.tasks.length;

  async function saveAnswer(taskId: string, answer: Answer, fileIds: string[]) {
    try {
      const res = await assessment.saveAnswer(attempt.id, taskId, answer, fileIds);
      if (res.status !== "in_progress") reload();
      setAnswered((s) => new Set(s).add(taskId));
      const saved = res.tasks.find((t) => t.task.id === taskId);
      setWithFile((s) => {
        const next = new Set(s);
        if (saved?.files.length) next.add(taskId);
        else next.delete(taskId);
        return next;
      });
      return saved;
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
      <div className="tm-bar sticky top-16 z-10 -mx-4 flex flex-wrap items-center gap-3 border-b border-line bg-bg/95 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-2xl sm:border">
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
          <li key={item.task.id} className="tm-card space-y-3 rounded-2xl border border-line bg-surface p-5">
            <TaskHead item={item} n={firstNumber + i} />
            <Markdown text={item.task.statement} />
            <AnswerInput item={item} attemptId={attempt.id} onSave={(answer, fileIds) => saveAnswer(item.task.id, answer, fileIds)} />
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
        {perTask && !last ? (
          <Button
            loading={busy}
            onClick={() => {
              const cur = attempt.tasks[attempt.current_index];
              const warn = cur?.solution_file && !withFile.has(cur.task.id) ? "Вы не прикрепили файл с решением. " : "";
              if (window.confirm(`${warn}Перейти к следующему заданию? Вернуться к этому будет нельзя.`)) act(() => assessment.nextTask(attempt.id));
            }}
          >
            Следующее задание →
          </Button>
        ) : (
          <Button
            loading={busy}
            onClick={() => {
              const missing = total - answered.size;
              const noFile = attempt.tasks.flatMap((t, n) => (t.solution_file && !withFile.has(t.task.id) ? [n + 1] : []));
              const warn =
                (missing > 0 && !perTask ? `Без ответа заданий: ${missing}. ` : "") +
                (noFile.length && !perTask ? `Не прикреплено решение к заданиям: ${noFile.join(", ")}. ` : "");
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
