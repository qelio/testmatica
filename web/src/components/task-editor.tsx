"use client";

import { useState } from "react";

import { CodeEditor } from "@/components/code-editor";
import { ExamItemsPicker } from "@/components/exams";
import { Markdown } from "@/components/markdown";
import { buildRubric, TopicSelect } from "@/components/topics";
import { Alert, Button, Field, Select } from "@/components/ui";
import { assessment, type TaskFull, type TaskInput, type TaskType } from "@/lib/api";
import { TASK_TYPE_LABELS } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

const TEXTAREA =
  "w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

function fromTask(t?: TaskFull): TaskInput {
  return {
    title: t?.title ?? "",
    statement: t?.statement ?? "",
    type: t?.type ?? "choice",
    subject_id: t?.subject_id ?? null,
    subject_name: t?.subject_name ?? null,
    topic_id: t?.topic_id ?? null,
    exam_item_ids: t?.exam_items.map((e) => e.id) ?? [],
    difficulty: t?.difficulty ?? 1,
    tags: t?.tags ?? [],
    explanation: t?.explanation ?? "",
    file_mode: t?.file_mode ?? "none",
    options: t?.options.map((o) => ({ text: o.text, is_correct: !!o.is_correct })) ?? [
      { text: "", is_correct: true },
      { text: "", is_correct: false },
    ],
    answers: t?.answers ?? [{ mode: "exact", value: "" }],
    starter_code: t?.starter_code ?? "",
    time_limit_s: t?.time_limit_s ?? 2,
    memory_limit_mb: t?.memory_limit_mb ?? 128,
    tests: t?.tests ?? [{ input: "", expected: "" }],
  };
}

/** Форма задачи. types — какие типы доступны (в курсы — только с автопроверкой). */
export function TaskEditor({
  task,
  types = ["choice", "short", "long", "code"],
  onSaved,
  onCancel,
}: {
  task?: TaskFull;
  types?: TaskType[];
  onSaved: (t: TaskFull) => void;
  onCancel?: () => void;
}) {
  const topics = useLoad(() => assessment.topics(), []);
  const exams = useLoad(() => assessment.exams(), []);
  const [form, setForm] = useState<TaskInput>(() => fromTask(task));
  const [tags, setTags] = useState((task?.tags ?? []).join(", "));
  const [preview, setPreview] = useState(false);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof TaskInput>(k: K, v: TaskInput[K]) => setForm((f) => ({ ...f, [k]: v }));

  async function save(e: React.FormEvent) {
    e.preventDefault();
    // Форма может стоять в окне поверх другой формы: React-события всплывают и через портал.
    e.stopPropagation();
    setBusy(true);
    setError(undefined);
    const body: TaskInput = {
      ...form,
      tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
      options: form.options.filter((o) => o.text.trim()),
      answers: form.answers.filter((a) => a.value.trim()),
    };
    try {
      onSaved(task ? await assessment.update(task.id, body) : await assessment.create(body));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="space-y-5" onSubmit={save}>
      {error && <Alert>{error}</Alert>}
      <div className="grid gap-3 sm:grid-cols-4">
        <Select label="Тип" value={form.type} onChange={(e) => set("type", e.target.value as TaskType)} disabled={!!task}>
          {types.map((t) => (
            <option key={t} value={t}>
              {TASK_TYPE_LABELS[t]}
            </option>
          ))}
        </Select>
        <div className="sm:col-span-2">
          <TopicSelect
            rubric={buildRubric(topics.data ?? [])}
            value={form.topic_id ?? ""}
            onChange={(id) => set("topic_id", id || null)}
            label="Раздел и тема"
            empty="Выберите тему…"
          />
        </div>
        <Select label="Сложность" value={form.difficulty} onChange={(e) => set("difficulty", Number(e.target.value))}>
          <option value={1}>Базовая</option>
          <option value={2}>Средняя</option>
          <option value={3}>Сложная</option>
        </Select>
      </div>
      {exams.data && exams.data.length > 0 && (
        <ExamItemsPicker exams={exams.data} value={form.exam_item_ids} onChange={(ids) => set("exam_item_ids", ids)} />
      )}
      <Field label="Название" required maxLength={200} value={form.title} onChange={(e) => set("title", e.target.value)} />
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-sm font-medium">Условие</span>
          <button type="button" onClick={() => setPreview((p) => !p)} className="text-sm text-brand hover:underline">
            {preview ? "Редактировать" : "Предпросмотр"}
          </button>
        </div>
        {preview ? (
          <div className="min-h-32 rounded-xl border border-line p-4">
            <Markdown text={form.statement || "_Пусто_"} />
            {form.type === "choice" && (
              <ul className="mt-3 space-y-1.5">
                {form.options.filter((o) => o.text.trim()).map((o, i) => (
                  <li key={i} className={`flex items-start gap-2 rounded-lg border px-3 py-2 ${o.is_correct ? "border-ok/50 bg-ok/10" : "border-line"}`}>
                    <span className={`w-4 shrink-0 ${o.is_correct ? "text-ok" : ""}`}>{o.is_correct ? "✓" : ""}</span>
                    <div className="min-w-0 flex-1">
                      <Markdown text={o.text} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <textarea rows={6} required className={`${TEXTAREA} font-mono text-sm`} value={form.statement} onChange={(e) => set("statement", e.target.value)} placeholder="Текст задачи. Формулы — $x^2$" />
        )}
      </div>

      {form.type === "choice" && (
        <fieldset className="space-y-2">
          <legend className="mb-1.5 text-sm font-medium">Варианты ответа (отметьте правильные — можно несколько)</legend>
          <p className="text-xs text-fg-soft">Формулы — как в условии: <code>{"$\\frac{3}{5}$"}</code>. Как они выглядят — в «Предпросмотре».</p>
          {form.options.map((o, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={o.is_correct}
                aria-label={`Вариант ${i + 1} правильный`}
                onChange={(e) => set("options", form.options.map((x, j) => (j === i ? { ...x, is_correct: e.target.checked } : x)))}
                className="h-5 w-5 accent-ok"
              />
              <input
                value={o.text}
                placeholder={`Вариант ${i + 1}`}
                onChange={(e) => set("options", form.options.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))}
                className={`${TEXTAREA} h-10 py-0`}
              />
              <button type="button" onClick={() => set("options", form.options.filter((_, j) => j !== i))} className="px-2 text-fg-soft hover:text-danger" aria-label="Удалить вариант">
                ✕
              </button>
            </div>
          ))}
          <button type="button" onClick={() => set("options", [...form.options, { text: "", is_correct: false }])} className="text-sm text-brand hover:underline">
            + вариант
          </button>
        </fieldset>
      )}

      {form.type === "short" && (
        <fieldset className="space-y-2">
          <legend className="mb-1.5 text-sm font-medium">Правильные ответы</legend>
          <p className="text-xs text-fg-soft">Регистр, лишние пробелы, «ё/е» и запятая/точка в числах не учитываются. Шаблон — регулярное выражение для сложных случаев.</p>
          {form.answers.map((a, i) => (
            <div key={i} className="flex items-center gap-2">
              <select
                value={a.mode}
                onChange={(e) => set("answers", form.answers.map((x, j) => (j === i ? { ...x, mode: e.target.value as "exact" | "regex" } : x)))}
                className="h-10 rounded-xl border border-line bg-surface px-2 text-sm"
              >
                <option value="exact">Точно</option>
                <option value="regex">Шаблон</option>
              </select>
              <input
                value={a.value}
                onChange={(e) => set("answers", form.answers.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))}
                className={`${TEXTAREA} h-10 py-0 ${a.mode === "regex" ? "font-mono" : ""}`}
              />
              <button type="button" onClick={() => set("answers", form.answers.filter((_, j) => j !== i))} className="px-2 text-fg-soft hover:text-danger" aria-label="Удалить ответ">
                ✕
              </button>
            </div>
          ))}
          <button type="button" onClick={() => set("answers", [...form.answers, { mode: "exact", value: "" }])} className="text-sm text-brand hover:underline">
            + ещё вариант ответа
          </button>
        </fieldset>
      )}

      {form.type === "long" && (
        <Select label="Файл с ответом" value={form.file_mode} onChange={(e) => set("file_mode", e.target.value as TaskInput["file_mode"])}>
          <option value="none">Не нужен — только текст</option>
          <option value="optional">Можно прикрепить</option>
          <option value="required">Обязательно прикрепить</option>
        </Select>
      )}

      {form.type === "code" && (
        <div className="space-y-4">
          <div>
            <span className="mb-1.5 block text-sm font-medium">Заготовка кода для ученика</span>
            <CodeEditor value={form.starter_code} onChange={(v) => set("starter_code", v)} minHeight="80px" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Лимит времени, с" type="number" min={0.5} max={10} step={0.5} value={form.time_limit_s} onChange={(e) => set("time_limit_s", Number(e.target.value))} />
            <Field label="Лимит памяти, МБ" type="number" min={32} max={512} step={32} value={form.memory_limit_mb} onChange={(e) => set("memory_limit_mb", Number(e.target.value))} />
          </div>
          <fieldset className="space-y-2">
            <legend className="mb-1.5 text-sm font-medium">Тест-кейсы (ученик не видит входные данные)</legend>
            {form.tests.map((c, i) => (
              <div key={i} className="grid grid-cols-[auto_1fr_1fr_auto] items-start gap-2">
                <span className="pt-2 text-sm text-fg-soft">{i + 1}</span>
                <textarea rows={2} placeholder="Ввод" value={c.input} onChange={(e) => set("tests", form.tests.map((x, j) => (j === i ? { ...x, input: e.target.value } : x)))} className={`${TEXTAREA} font-mono text-sm`} />
                <textarea rows={2} placeholder="Ожидаемый вывод" value={c.expected} onChange={(e) => set("tests", form.tests.map((x, j) => (j === i ? { ...x, expected: e.target.value } : x)))} className={`${TEXTAREA} font-mono text-sm`} />
                <button type="button" onClick={() => set("tests", form.tests.filter((_, j) => j !== i))} className="px-2 pt-2 text-fg-soft hover:text-danger" aria-label="Удалить тест">
                  ✕
                </button>
              </div>
            ))}
            <button type="button" onClick={() => set("tests", [...form.tests, { input: "", expected: "" }])} className="text-sm text-brand hover:underline">
              + тест-кейс
            </button>
          </fieldset>
        </div>
      )}

      <label className="block">
        <span className="mb-1.5 block text-sm font-medium">Разбор решения</span>
        <textarea rows={3} className={TEXTAREA} value={form.explanation} onChange={(e) => set("explanation", e.target.value)} placeholder="Ученик увидит разбор после верного ответа или нескольких попыток" />
      </label>
      <Field label="Теги через запятую" placeholder="уравнения, 7 класс" value={tags} onChange={(e) => setTags(e.target.value)} />

      <div className="flex gap-2">
        {onCancel && (
          <Button type="button" variant="secondary" onClick={onCancel}>
            Отмена
          </Button>
        )}
        <Button type="submit" loading={busy} className="flex-1">
          {task ? "Сохранить" : "Создать задачу"}
        </Button>
      </div>
    </form>
  );
}
