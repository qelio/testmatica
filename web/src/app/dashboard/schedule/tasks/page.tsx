"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Button, Spinner } from "@/components/ui";
import { schedule, type TeacherTodo } from "@/lib/api";
import { toDateInput } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

const DAY = 864e5;
const BACK_DAYS = 30;
const AHEAD_DAYS = 60;

/** «ГГГГ-ММ-ДД» по часам пользователя: n дней от сегодня. */
function dayKey(offset: number): string {
  return toDateInput(new Date(Date.now() + offset * DAY));
}

function dayLabel(key: string, today: string): string {
  const diff = Math.round((Date.parse(key) - Date.parse(today)) / DAY);
  if (diff === 0) return "Сегодня";
  if (diff === -1) return "Вчера";
  if (diff === 1) return "Завтра";
  return new Date(`${key}T12:00:00`).toLocaleDateString("ru-RU", { weekday: "short", day: "numeric", month: "long" });
}

/** Планировщик педагога (решение №54): простые дела по дням — «выставить оценки», «проверить ДЗ». Выполнено / нет. */
export default function TeacherTasksPage() {
  const today = dayKey(0);
  const list = useLoad(() => schedule.todos(dayKey(-BACK_DAYS), dayKey(AHEAD_DAYS)), []);
  const [items, setItems] = useState<TeacherTodo[] | null>(null);
  const todos = items ?? list.data ?? null;
  const [title, setTitle] = useState("");
  const [day, setDay] = useState(today);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [showPast, setShowPast] = useState(false);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !todos) return;
    setBusy(true);
    setError(undefined);
    try {
      const made = await schedule.addTodo(title.trim(), day);
      setItems([...todos, made]);
      setTitle("");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function change(t: TeacherTodo, data: { done?: boolean; day?: string }) {
    if (!todos) return;
    setItems(todos.map((x) => (x.id === t.id ? { ...x, ...data } : x)));
    try {
      const saved = await schedule.updateTodo(t.id, data);
      setItems((cur) => (cur ?? []).map((x) => (x.id === t.id ? saved : x)));
    } catch (err) {
      setError(errorText(err));
      setItems((cur) => (cur ?? []).map((x) => (x.id === t.id ? t : x)));
    }
  }

  async function remove(t: TeacherTodo) {
    if (!todos) return;
    setItems(todos.filter((x) => x.id !== t.id));
    try {
      await schedule.deleteTodo(t.id);
    } catch (err) {
      setError(errorText(err));
      setItems((cur) => [...(cur ?? []), t]);
    }
  }

  // Дни с делами: сегодня — всегда; будущие — по порядку; прошедшие — от вчера назад.
  const byDay = new Map<string, TeacherTodo[]>();
  for (const t of todos ?? []) byDay.set(t.day, [...(byDay.get(t.day) ?? []), t]);
  const upcoming = [today, ...[...byDay.keys()].filter((d) => d > today).sort()];
  const past = [...byDay.keys()].filter((d) => d < today).sort().reverse();
  const overdue = past.reduce((n, d) => n + (byDay.get(d) ?? []).filter((t) => !t.done).length, 0);

  const section = (key: string) => {
    const tasks = (byDay.get(key) ?? []).slice().sort((a, b) => Number(a.done) - Number(b.done) || a.created_at.localeCompare(b.created_at));
    const left = tasks.filter((t) => !t.done).length;
    return (
      <section key={key} className="space-y-2">
        <h2 className="flex items-baseline gap-2 text-sm font-semibold">
          <span className={key === today ? "text-brand" : ""}>{dayLabel(key, today)}</span>
          {tasks.length > 0 && (
            <span className="font-normal text-fg-soft">
              {left ? `осталось ${left} из ${tasks.length}` : "всё выполнено ✓"}
            </span>
          )}
        </h2>
        {!tasks.length ? (
          <p className="rounded-xl border border-dashed border-line px-4 py-3 text-sm text-fg-soft">На этот день дел нет.</p>
        ) : (
          <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
            {tasks.map((t) => (
              <li key={t.id} className="group flex items-center gap-3 px-4 py-2.5">
                <input
                  type="checkbox"
                  checked={t.done}
                  onChange={(e) => change(t, { done: e.target.checked })}
                  className="h-5 w-5 shrink-0 accent-brand"
                  aria-label={t.done ? `Отметить «${t.title}» невыполненной` : `Отметить «${t.title}» выполненной`}
                />
                <span className={`min-w-0 flex-1 ${t.done ? "text-fg-soft line-through" : key < today ? "text-danger" : ""}`}>{t.title}</span>
                {!t.done && key < today && (
                  <button type="button" onClick={() => change(t, { day: today })} className="shrink-0 text-xs text-brand hover:underline">
                    на сегодня
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => remove(t)}
                  className="shrink-0 px-1 text-fg-soft opacity-60 hover:text-danger hover:opacity-100"
                  aria-label={`Удалить «${t.title}»`}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    );
  };

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <Link href="/dashboard/schedule" className="text-sm text-fg-soft hover:text-fg">
        ← Расписание
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">Планировщик задач</h1>
      {(error || list.error) && <Alert>{error ?? list.error}</Alert>}

      <form onSubmit={add} className="flex flex-wrap items-center gap-2 rounded-2xl border border-line bg-surface p-3">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={300}
          placeholder="Например: выставить оценки 7А"
          aria-label="Новая задача"
          className="h-11 min-w-0 flex-1 basis-60 rounded-xl border border-line bg-surface px-3.5 outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
        />
        <input
          type="date"
          value={day}
          onChange={(e) => setDay(e.target.value || today)}
          aria-label="На какой день"
          className="h-11 rounded-xl border border-line bg-surface px-3 outline-none focus:border-brand"
        />
        <Button type="submit" loading={busy} disabled={!title.trim()} className="h-11">
          Добавить
        </Button>
      </form>

      {!todos ? (
        <Spinner />
      ) : (
        <>
          {upcoming.map(section)}
          {past.length > 0 && (
            <div className="space-y-4 border-t border-line pt-4">
              <button type="button" onClick={() => setShowPast(!showPast)} className="text-sm font-medium text-brand hover:underline">
                {showPast ? "Скрыть прошедшие дни" : "Прошедшие дни"}
                {overdue > 0 && <span className="ml-1 text-danger">· не выполнено: {overdue}</span>}
              </button>
              {(showPast || past[0] === dayKey(-1)) && (showPast ? past : past.slice(0, 1)).map(section)}
            </div>
          )}
        </>
      )}
    </div>
  );
}
