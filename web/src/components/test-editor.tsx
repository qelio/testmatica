"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { AssignModal } from "@/components/assign-modal";
import { ExamChips } from "@/components/exams";
import { TaskPicker } from "@/components/task-picker";
import { Alert, Badge, Button, Field, Select } from "@/components/ui";
import { assessment, type Quiz, type QuizInput, type TaskSummary, type TimeMode } from "@/lib/api";
import { TASK_TYPE_LABELS } from "@/lib/format";
import { errorText } from "@/lib/hooks";

type Item = { task_id: string; points: number; title: string; task?: TaskSummary };

const TEXTAREA =
  "w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

/** Редактор теста: задачи из банка, баллы, порядок, перемешивание, таймер. Отсюда же тест выдаётся. */
export function TestEditor({ test }: { test?: Quiz }) {
  const router = useRouter();
  const [title, setTitle] = useState(test?.title ?? "");
  const [description, setDescription] = useState(test?.description ?? "");
  const [orderMode, setOrderMode] = useState(test?.order_mode ?? "fixed");
  const [shuffle, setShuffle] = useState(test?.shuffle_options ?? false);
  const [timeMode, setTimeMode] = useState<TimeMode>(test?.time_mode ?? "none");
  const [minutes, setMinutes] = useState(test?.time_limit_s ? test.time_limit_s / 60 : 20);
  const [items, setItems] = useState<Item[]>(
    () => test?.items.map((i) => ({ task_id: i.task_id, points: i.points, title: i.task.title, task: i.task })) ?? [],
  );
  const [picking, setPicking] = useState(false);
  const [dirty, setDirty] = useState(!test);
  const [assigning, setAssigning] = useState(false);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const change = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setDirty(true);
  };
  const move = (i: number, j: number) =>
    change(setItems)(items.map((x, n) => (n === i ? items[j] : n === j ? items[i] : x)));

  async function save(e?: React.FormEvent) {
    e?.preventDefault();
    setBusy(true);
    setError(undefined);
    const body: QuizInput = {
      title,
      description,
      order_mode: orderMode,
      shuffle_options: shuffle,
      time_mode: timeMode,
      time_limit_s: timeMode === "none" ? null : Math.round(minutes * 60),
      items: items.map((i) => ({ task_id: i.task_id, points: i.points })),
    };
    try {
      const saved = test ? await assessment.updateTest(test.id, body) : await assessment.createTest(body);
      setDirty(false);
      if (!test) router.replace(`/dashboard/tests/${saved.id}`);
      else setItems(saved.items.map((i) => ({ task_id: i.task_id, points: i.points, title: i.task.title, task: i.task })));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const total = items.reduce((n, i) => n + i.points, 0);
  const hasManual = items.some((i) => i.task?.type === "long");

  return (
    <form className="space-y-6" onSubmit={save}>
      {error && <Alert>{error}</Alert>}
      <section className="space-y-4 rounded-2xl border border-line bg-surface p-5">
        <Field label="Название" required maxLength={200} value={title} onChange={(e) => change(setTitle)(e.target.value)} />
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Описание для учеников</span>
          <textarea rows={2} maxLength={5000} className={TEXTAREA} value={description} onChange={(e) => change(setDescription)(e.target.value)} />
        </label>
        <div className="grid gap-3 sm:grid-cols-3">
          <Select label="Порядок заданий" value={orderMode} onChange={(e) => change(setOrderMode)(e.target.value as "fixed" | "random")}>
            <option value="fixed">Как в списке</option>
            <option value="random">Случайный у каждого</option>
          </Select>
          <Select label="Ограничение времени" value={timeMode} onChange={(e) => change(setTimeMode)(e.target.value as TimeMode)}>
            <option value="none">Без таймера</option>
            <option value="total">На весь тест</option>
            <option value="per_task">На каждое задание</option>
          </Select>
          {timeMode !== "none" && (
            <Field
              label={timeMode === "total" ? "Минут на тест" : "Минут на задание"}
              type="number"
              min={0.5}
              max={360}
              step={0.5}
              required
              value={minutes}
              onChange={(e) => change(setMinutes)(Number(e.target.value))}
            />
          )}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={shuffle} onChange={(e) => change(setShuffle)(e.target.checked)} className="h-4 w-4 accent-brand" />
          Перемешивать варианты ответа — у каждого ученика свой порядок
        </label>
        {timeMode === "per_task" && (
          <p className="text-xs text-fg-soft">Задания открываются по одному; к пройденному вернуться нельзя. Когда время выходит — открывается следующее.</p>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-lg font-semibold">Задания</h2>
          <span className="text-sm text-fg-soft">
            {items.length} · всего баллов: {total}
          </span>
        </div>
        {items.length > 0 && (
          <ol className="divide-y divide-line rounded-2xl border border-line bg-surface">
            {items.map((item, i) => (
              <li key={item.task_id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
                <span className="w-6 text-right text-sm text-fg-soft tabular-nums">{i + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{item.title}</span>
                  {item.task && (
                    <span className="mt-0.5 flex flex-wrap items-center gap-1.5">
                      <Badge>{TASK_TYPE_LABELS[item.task.type]}</Badge>
                      <ExamChips labels={item.task.exam_items} />
                    </span>
                  )}
                </span>
                <label className="flex items-center gap-1.5 text-sm text-fg-soft">
                  баллы
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={item.points}
                    onChange={(e) => change(setItems)(items.map((x, n) => (n === i ? { ...x, points: Math.max(1, Number(e.target.value)) } : x)))}
                    className="h-9 w-16 rounded-lg border border-line bg-surface px-2 text-fg"
                    aria-label={`Баллы за задание ${i + 1}`}
                  />
                </label>
                <span className="flex">
                  <button type="button" className="px-1.5 text-fg-soft hover:text-fg disabled:opacity-30" disabled={i === 0} onClick={() => move(i, i - 1)} aria-label="Выше">
                    ↑
                  </button>
                  <button type="button" className="px-1.5 text-fg-soft hover:text-fg disabled:opacity-30" disabled={i === items.length - 1} onClick={() => move(i, i + 1)} aria-label="Ниже">
                    ↓
                  </button>
                  <button type="button" className="px-1.5 text-fg-soft hover:text-danger" onClick={() => change(setItems)(items.filter((_, n) => n !== i))} aria-label="Убрать из теста">
                    ✕
                  </button>
                </span>
              </li>
            ))}
          </ol>
        )}
        {hasManual && <p className="text-xs text-fg-soft">Развёрнутые ответы проверяете вы — итог и оценка появятся после проверки.</p>}
        {picking ? (
          <div className="space-y-2">
            <TaskPicker
              selected={null}
              autoOnly={false}
              exclude={items.map((i) => i.task_id)}
              onSelect={(id, taskTitle) => change(setItems)([...items, { task_id: id, points: 1, title: taskTitle }])}
            />
            <Button type="button" variant="ghost" onClick={() => setPicking(false)}>
              Готово
            </Button>
          </div>
        ) : (
          <Button type="button" variant="secondary" onClick={() => setPicking(true)}>
            + Добавить задачи из банка
          </Button>
        )}
      </section>

      <div className="flex flex-wrap gap-2 border-t border-line pt-4">
        <Button type="submit" loading={busy} disabled={!dirty && !!test}>
          {test ? (dirty ? "Сохранить" : "Сохранено") : "Создать тест"}
        </Button>
        {test && (
          <Button type="button" variant="secondary" disabled={dirty || !items.length} onClick={() => setAssigning(true)}>
            Выдать…
          </Button>
        )}
        {test && dirty && <span className="self-center text-sm text-fg-soft">Сохраните изменения, чтобы выдать тест</span>}
        {test && test.assignments_count === 0 && (
          <Button
            type="button"
            variant="ghost"
            className="ml-auto text-danger"
            onClick={async () => {
              if (!window.confirm("Удалить тест?")) return;
              try {
                await assessment.deleteTest(test.id);
                router.replace("/dashboard/assignments?tab=tests");
              } catch (err) {
                setError(errorText(err));
              }
            }}
          >
            Удалить
          </Button>
        )}
      </div>
      {test && (
        <AssignModal
          testId={test.id}
          open={assigning}
          onClose={() => setAssigning(false)}
          onAssigned={(a) => router.push(`/dashboard/assignments/${a.id}`)}
        />
      )}
    </form>
  );
}
