"use client";

import Link from "next/link";
import { useState } from "react";

import { ExamItemsField } from "@/components/exams";
import { Alert, Button, Field, Select } from "@/components/ui";
import { assessment, content, type PlanItem, type PlanLessonInput } from "@/lib/api";
import { errorText, useLoad } from "@/lib/hooks";

const TEXTAREA =
  "w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

export const ITEM_LABELS: Record<PlanItem["kind"], string> = { module: "Модуль", test: "Тест", link: "Ссылка", note: "Заметка" };

export const EMPTY_LESSON: PlanLessonInput = { topic: "", goals: "", class_items: [], home_items: [], exam_item_ids: [] };

/** Куда ведёт материал: модуль библиотеки, тест педагога или внешняя ссылка. */
export function itemHref(item: PlanItem): string | null {
  if (item.kind === "module" && item.ref_id) return `/dashboard/library/module/${item.ref_id}`;
  if (item.kind === "test" && item.ref_id) return `/dashboard/tests/${item.ref_id}`;
  if (item.kind === "link" && item.url) return item.url;
  return null;
}

/** Список материалов для показа (в таблице КТП и в карточке урока). */
export function PlanItems({ items }: { items: PlanItem[] }) {
  if (!items.length) return <span className="text-fg-soft">—</span>;
  return (
    <ul className="space-y-0.5">
      {items.map((item, i) => {
        const href = itemHref(item);
        return (
          <li key={i} className="text-sm">
            <span className="text-fg-soft">{ITEM_LABELS[item.kind]}: </span>
            {href ? (
              <Link href={href} target={item.kind === "link" ? "_blank" : undefined} className="text-brand hover:underline">
                {item.title}
              </Link>
            ) : (
              item.title
            )}
          </li>
        );
      })}
    </ul>
  );
}

function ModulePicker({ onPick }: { onPick: (item: PlanItem) => void }) {
  const courses = useLoad(() => content.myCourses(), []);
  const [courseId, setCourseId] = useState("");
  const course = useLoad(async () => (courseId ? content.course(courseId, true) : null), [courseId]);
  const modules = course.data?.sections.flatMap((s) => s.modules.map((m) => ({ ...m, section: s.title }))) ?? [];
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      <Select label="Курс" value={courseId} onChange={(e) => setCourseId(e.target.value)}>
        <option value="">{courses.data?.length === 0 ? "В библиотеке нет своих курсов" : "Выберите курс"}</option>
        {courses.data?.map((c) => (
          <option key={c.id} value={c.id}>
            {c.title}
          </option>
        ))}
      </Select>
      <Select
        label="Модуль"
        value=""
        disabled={!modules.length}
        onChange={(e) => {
          const m = modules.find((x) => x.id === e.target.value);
          if (m) onPick({ kind: "module", ref_id: m.id, title: m.title });
        }}
      >
        <option value="">Выберите модуль</option>
        {modules.map((m) => (
          <option key={m.id} value={m.id}>
            {m.section} › {m.title}
          </option>
        ))}
      </Select>
    </div>
  );
}

function TestPicker({ onPick }: { onPick: (item: PlanItem) => void }) {
  const tests = useLoad(() => assessment.tests(), []);
  return (
    <Select
      label="Тест"
      value=""
      onChange={(e) => {
        const t = tests.data?.find((x) => x.id === e.target.value);
        if (t) onPick({ kind: "test", ref_id: t.id, title: t.title });
      }}
    >
      <option value="">{tests.data?.length === 0 ? "Тестов пока нет — создайте в разделе «Тесты»" : "Выберите тест"}</option>
      {tests.data?.map((t) => (
        <option key={t.id} value={t.id}>
          {t.title}
        </option>
      ))}
    </Select>
  );
}

function ItemsEditor({ label, items, onChange }: { label: string; items: PlanItem[]; onChange: (items: PlanItem[]) => void }) {
  const [kind, setKind] = useState<PlanItem["kind"] | "">("");
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const add = (item: PlanItem) => {
    onChange([...items, item]);
    setKind("");
    setTitle("");
    setUrl("");
  };
  return (
    <fieldset className="space-y-2 rounded-xl border border-line p-3">
      <legend className="px-1 text-sm font-medium">{label}</legend>
      {items.length > 0 && (
        <ul className="space-y-1">
          {items.map((item, i) => (
            <li key={i} className="flex items-center gap-2 text-sm">
              <span className="text-fg-soft">{ITEM_LABELS[item.kind]}:</span>
              <span className="min-w-0 flex-1 truncate">{item.title}</span>
              <button type="button" className="px-1 text-fg-soft hover:text-danger" onClick={() => onChange(items.filter((_, j) => j !== i))} aria-label={`Убрать «${item.title}»`}>
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
      {items.length < 20 && (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-1.5">
            {(Object.keys(ITEM_LABELS) as PlanItem["kind"][]).map((k) => (
              <button
                key={k}
                type="button"
                aria-pressed={kind === k}
                onClick={() => setKind(kind === k ? "" : k)}
                className={`rounded-lg border px-2.5 py-1 text-sm ${kind === k ? "border-brand bg-brand/10 text-brand" : "border-line text-fg-soft hover:text-fg"}`}
              >
                + {ITEM_LABELS[k].toLowerCase()}
              </button>
            ))}
          </div>
          {kind === "module" && <ModulePicker onPick={add} />}
          {kind === "test" && <TestPicker onPick={add} />}
          {(kind === "link" || kind === "note") && (
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-48 flex-1">
                <Field label={kind === "link" ? "Название" : "Текст"} value={title} maxLength={300} onChange={(e) => setTitle(e.target.value)} />
              </div>
              {kind === "link" && (
                <div className="min-w-48 flex-1">
                  <Field label="Адрес" type="url" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
                </div>
              )}
              <Button
                type="button"
                variant="secondary"
                className="h-11"
                disabled={!title.trim() || (kind === "link" && !/^https?:\/\//.test(url))}
                onClick={() => add(kind === "link" ? { kind, title: title.trim(), url } : { kind, title: title.trim() })}
              >
                Добавить
              </Button>
            </div>
          )}
        </div>
      )}
    </fieldset>
  );
}

/** Форма урока КТП: тема, планируемые результаты, материалы к уроку и на дом, задания ЕГЭ/ОГЭ. */
export function LessonForm({
  initial = EMPTY_LESSON,
  onSubmit,
  onCancel,
  submitLabel = "Сохранить",
}: {
  initial?: PlanLessonInput;
  onSubmit: (lesson: PlanLessonInput) => Promise<unknown>;
  onCancel?: () => void;
  submitLabel?: string;
}) {
  const [lesson, setLesson] = useState<PlanLessonInput>(initial);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof PlanLessonInput>(k: K, v: PlanLessonInput[K]) => setLesson((l) => ({ ...l, [k]: v }));

  return (
    <form
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        e.stopPropagation();
        setBusy(true);
        setError(undefined);
        try {
          await onSubmit(lesson);
        } catch (err) {
          setError(errorText(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      {error && <Alert>{error}</Alert>}
      <Field label="Тема урока" required maxLength={300} value={lesson.topic} onChange={(e) => set("topic", e.target.value)} />
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium">Планируемые результаты</span>
        <textarea rows={2} maxLength={5000} className={TEXTAREA} value={lesson.goals} onChange={(e) => set("goals", e.target.value)} />
      </label>
      <div className="grid gap-3 md:grid-cols-2">
        <ItemsEditor label="К уроку" items={lesson.class_items} onChange={(v) => set("class_items", v)} />
        <ItemsEditor label="На дом" items={lesson.home_items} onChange={(v) => set("home_items", v)} />
      </div>
      <ExamItemsField value={lesson.exam_item_ids} onChange={(v) => set("exam_item_ids", v)} />
      <div className="flex gap-2">
        <Button type="submit" loading={busy}>
          {submitLabel}
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel}>
            Отмена
          </Button>
        )}
      </div>
    </form>
  );
}
