"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AdminContentActions } from "@/components/admin-content";
import { STATUS_LABELS } from "@/components/course-view";
import { ExamItemsByIds } from "@/components/exams";
import { LessonForm, PlanItems } from "@/components/plan-lesson-form";
import { Alert, Badge, Button, Field } from "@/components/ui";
import { type PlanLessonInput, type PlanTemplate, planning } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorText } from "@/lib/hooks";

const TEXTAREA =
  "w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

function LessonView({ lesson, n }: { lesson: PlanLessonInput; n: number }) {
  return (
    <div className="min-w-0 space-y-1.5">
      <p className="font-medium">
        <span className="mr-2 text-fg-soft tabular-nums">{n}.</span>
        {lesson.topic}
      </p>
      {lesson.goals && <p className="text-sm text-fg-soft">{lesson.goals}</p>}
      {(lesson.class_items.length > 0 || lesson.home_items.length > 0) && (
        <div className="grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <p className="text-xs font-medium tracking-wide text-fg-soft uppercase">К уроку</p>
            <PlanItems items={lesson.class_items} />
          </div>
          <div>
            <p className="text-xs font-medium tracking-wide text-fg-soft uppercase">На дом</p>
            <PlanItems items={lesson.home_items} />
          </div>
        </div>
      )}
      {lesson.exam_item_ids.length > 0 && (
        <div className="text-sm">
          <ExamItemsByIds ids={lesson.exam_item_ids} />
        </div>
      )}
    </div>
  );
}

/** Шаблон КТП: список уроков без дат. Свой — правится; чужой из библиотеки — только просмотр и копия. */
export function TemplateEditor({ template, reload }: { template?: PlanTemplate; reload?: () => void }) {
  const router = useRouter();
  const { user } = useAuth();
  const staff = !!user?.roles.some((r) => r === "moderator" || r === "admin");
  const editable = !template || template.can_edit;
  const mine = !template || template.owner_id === user?.id;
  const [title, setTitle] = useState(template?.title ?? "");
  const [subject, setSubject] = useState(template?.subject ?? "");
  const [level, setLevel] = useState(template?.level ?? "");
  const [description, setDescription] = useState(template?.description ?? "");
  const [lessons, setLessons] = useState<PlanLessonInput[]>(template?.lessons ?? []);
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [dirty, setDirty] = useState(!template);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const change = (fn: () => void) => {
    fn();
    setDirty(true);
  };

  async function act(action: () => Promise<unknown>) {
    setError(undefined);
    try {
      await action();
      reload?.();
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    const body = { title, subject: subject || null, level: level || null, description, lessons };
    try {
      if (template) {
        await planning.updateTemplate(template.id, body);
        setDirty(false);
        reload?.();
      } else {
        const t = await planning.createTemplate(body);
        router.replace(`/dashboard/planning/templates/${t.id}`);
      }
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      {error && <Alert>{error}</Alert>}
      {template && mine && template.status === "rejected" && template.review_comment && (
        <Alert kind="info">
          <b>Модератор вернул шаблон:</b> {template.review_comment}
        </Alert>
      )}
      {template?.status === "removed" && (
        <Alert>
          <b>Шаблон снят с платформы администратором.</b> {template.review_comment}
        </Alert>
      )}
      {template && (
        <div className="flex flex-wrap items-center gap-2">
          {mine && template.status !== "private" && <Badge tone={STATUS_LABELS[template.status].tone}>{STATUS_LABELS[template.status].text}</Badge>}
          {!mine && <span className="text-sm text-fg-soft">Автор: {template.author_name}</span>}
          <AdminContentActions kind="template" id={template.id} removed={template.status === "removed"} onChanged={() => reload?.()} />
          <Link
            href={`/dashboard/planning/new?template=${template.id}`}
            className="rounded-xl bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-strong"
          >
            Создать КТП по шаблону
          </Link>
          {!mine && (
            <Button
              variant="secondary"
              onClick={() =>
                act(async () => {
                  const copy = await planning.copyTemplate(template.id);
                  router.push(`/dashboard/planning/templates/${copy.id}`);
                })
              }
            >
              Взять за основу
            </Button>
          )}
          {mine && (template.status === "private" || template.status === "rejected") && (
            <Button variant="secondary" disabled={dirty} onClick={() => act(() => planning.submitTemplate(template.id))}>
              {staff ? "Опубликовать" : "Отправить в библиотеку"}
            </Button>
          )}
          {mine && (template.status === "pending" || template.status === "published") && (
            <Button variant="secondary" onClick={() => act(() => planning.unpublishTemplate(template.id))}>
              {template.status === "pending" ? "Отозвать с проверки" : "Снять с публикации"}
            </Button>
          )}
          {mine && (
            <Button
              variant="ghost"
              className="ml-auto text-danger"
              onClick={() =>
                window.confirm("Удалить шаблон? КТП, созданные по нему, останутся.") &&
                act(async () => {
                  await planning.deleteTemplate(template.id);
                  router.replace("/dashboard/planning?tab=templates");
                })
              }
            >
              Удалить
            </Button>
          )}
        </div>
      )}

      {editable ? (
        <form className="space-y-4 rounded-2xl border border-line bg-surface p-5" onSubmit={save}>
          <Field label="Название" required maxLength={200} value={title} onChange={(e) => change(() => setTitle(e.target.value))} />
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Предмет" maxLength={80} value={subject} onChange={(e) => change(() => setSubject(e.target.value))} />
            <Field label="Класс или уровень" placeholder="7 класс, ОГЭ…" maxLength={40} value={level} onChange={(e) => change(() => setLevel(e.target.value))} />
          </div>
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium">Описание</span>
            <textarea rows={2} maxLength={5000} className={TEXTAREA} value={description} onChange={(e) => change(() => setDescription(e.target.value))} />
          </label>
          <Button type="submit" loading={busy} disabled={!dirty}>
            {template ? (dirty ? "Сохранить шаблон" : "Сохранено") : "Создать шаблон"}
          </Button>
        </form>
      ) : (
        template?.description && <p className="text-fg-soft">{template.description}</p>
      )}

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Уроки ({lessons.length})</h2>
        <ol className="space-y-2">
          {lessons.map((lesson, i) => (
            <li key={i} className="rounded-2xl border border-line bg-surface p-4">
              {editing === i ? (
                <LessonForm
                  initial={lesson}
                  submitLabel="Готово"
                  onCancel={() => setEditing(null)}
                  onSubmit={async (data) => {
                    change(() => setLessons(lessons.map((x, j) => (j === i ? data : x))));
                    setEditing(null);
                  }}
                />
              ) : (
                <>
                  <LessonView lesson={lesson} n={i + 1} />
                  {editable && (
                    <div className="mt-2 flex flex-wrap gap-x-3 text-sm">
                      <button className="text-brand hover:underline" onClick={() => setEditing(i)}>
                        Изменить
                      </button>
                      <button
                        className="text-fg-soft hover:text-fg disabled:opacity-30"
                        disabled={i === 0}
                        onClick={() => change(() => setLessons(lessons.map((x, j) => (j === i - 1 ? lessons[i] : j === i ? lessons[i - 1] : x))))}
                      >
                        ↑ выше
                      </button>
                      <button
                        className="text-fg-soft hover:text-fg disabled:opacity-30"
                        disabled={i === lessons.length - 1}
                        onClick={() => change(() => setLessons(lessons.map((x, j) => (j === i + 1 ? lessons[i] : j === i ? lessons[i + 1] : x))))}
                      >
                        ↓ ниже
                      </button>
                      <button className="text-fg-soft hover:text-danger" onClick={() => change(() => setLessons(lessons.filter((_, j) => j !== i)))}>
                        Удалить
                      </button>
                    </div>
                  )}
                </>
              )}
            </li>
          ))}
        </ol>
        {editable &&
          (editing === "new" ? (
            <div className="rounded-2xl border border-brand/40 bg-surface p-4">
              <LessonForm
                submitLabel="Добавить"
                onCancel={() => setEditing(null)}
                onSubmit={async (data) => {
                  change(() => setLessons([...lessons, data]));
                  setEditing(null);
                }}
              />
            </div>
          ) : (
            <Button variant="secondary" onClick={() => setEditing("new")}>
              + Урок
            </Button>
          ))}
        {editable && dirty && lessons.length > 0 && template && <p className="text-sm text-tutor">Не забудьте сохранить шаблон.</p>}
      </section>
    </div>
  );
}
