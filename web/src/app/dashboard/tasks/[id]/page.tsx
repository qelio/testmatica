"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { CodeEditor } from "@/components/code-editor";
import { AdminContentActions } from "@/components/admin-content";
import { STATUS_LABELS } from "@/components/course-view";
import { ExamChips } from "@/components/exams";
import { Markdown } from "@/components/markdown";
import { TaskEditor } from "@/components/task-editor";
import { buildRubric, topicLabel, TopicSelect } from "@/components/topics";
import { Alert, Badge, Button, Spinner } from "@/components/ui";
import { assessment } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { DIFFICULTY_LABELS, TASK_TYPE_LABELS } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

const FILE_MODES = { none: "", optional: "Можно прикрепить файл", required: "Файл обязателен" };

export default function TaskPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const task = useLoad(() => assessment.task(id), [id]);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string>();

  async function act(action: () => Promise<unknown>) {
    setError(undefined);
    try {
      await action();
      task.reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  if (task.error) return <Alert>{task.error}</Alert>;
  const t = task.data;
  if (!t) return <Spinner />;
  const mine = t.owner_id === user?.id;
  const staff = !!user?.roles.some((r) => r === "moderator" || r === "admin");

  if (editing) {
    return (
      <div className="mx-auto max-w-3xl space-y-5">
        <h1 className="text-2xl font-semibold tracking-tight">Изменить задачу</h1>
        <div className="rounded-2xl border border-line bg-surface p-5 sm:p-6">
          <TaskEditor
            task={t}
            onCancel={() => setEditing(false)}
            onSaved={() => {
              setEditing(false);
              task.reload();
            }}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <Link href="/dashboard/tasks" className="text-sm text-fg-soft hover:text-fg">
        ← Банк задач
      </Link>
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="brand">{TASK_TYPE_LABELS[t.type]}</Badge>
          <Badge>{DIFFICULTY_LABELS[t.difficulty]}</Badge>
          <ExamChips labels={t.exam_items} />
          {(mine || staff) && t.status !== "private" && <Badge tone={STATUS_LABELS[t.status].tone}>{STATUS_LABELS[t.status].text}</Badge>}
          <span className="ml-auto">
            <AdminContentActions kind="task" id={t.id} removed={t.status === "removed"} onChanged={task.reload} />
          </span>
        </div>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">{t.title}</h1>
        <p className="mt-1 text-sm text-fg-soft">
          {[t.topic_path.length ? topicLabel(t.topic_path, t.subject_name) : "Без темы", t.author_name, t.tags.join(", ")]
            .filter(Boolean)
            .join(" · ")}
        </p>
      </div>
      {error && <Alert>{error}</Alert>}
      {mine && t.status === "rejected" && t.review_comment && (
        <Alert kind="info">
          <b>Модератор вернул задачу:</b> {t.review_comment}
        </Alert>
      )}
      {t.status === "removed" && (
        <Alert>
          <b>Задача снята с платформы администратором.</b> {t.review_comment}
        </Alert>
      )}

      {mine && !t.topic_id && (t.status === "private" || t.status === "rejected") && (
        <Alert kind="info">Чтобы отправить задачу в публичный банк, выберите для неё раздел и тему.</Alert>
      )}
      {staff && !mine && <MoveTask taskId={t.id} topicId={t.topic_id} onMoved={task.reload} />}

      <div className="flex flex-wrap gap-2">
        {t.can_edit && (
          <Button variant="secondary" onClick={() => setEditing(true)}>
            Изменить
          </Button>
        )}
        {mine && (t.status === "private" || t.status === "rejected") && (
          <Button onClick={() => act(() => assessment.submitForReview(t.id))}>Отправить в публичный банк</Button>
        )}
        {mine && (t.status === "pending" || t.status === "published") && (
          <Button variant="secondary" onClick={() => act(() => assessment.unpublish(t.id))}>
            {t.status === "pending" ? "Отозвать с проверки" : "Снять с публикации"}
          </Button>
        )}
        {!mine && t.options.every((o) => o.is_correct !== null) && (
          <Button
            variant="secondary"
            onClick={() => act(async () => router.push(`/dashboard/tasks/${(await assessment.copy(t.id)).id}`))}
          >
            Взять за основу
          </Button>
        )}
        {t.can_edit && (
          <Button
            variant="ghost"
            className="text-danger"
            onClick={() => window.confirm("Удалить задачу?") && act(async () => { await assessment.remove(t.id); router.replace("/dashboard/tasks"); })}
          >
            Удалить
          </Button>
        )}
      </div>

      <section className="rounded-2xl border border-line bg-surface p-5">
        <h2 className="mb-2 text-sm font-medium text-fg-soft">Условие</h2>
        <Markdown text={t.statement} />
        {t.type === "choice" && (
          <ul className="mt-4 space-y-1.5">
            {t.options.map((o) => (
              <li key={o.id} className={`flex items-start gap-2 rounded-lg border px-3 py-2 ${o.is_correct ? "border-ok/50 bg-ok/10" : "border-line"}`}>
                <span className={`w-4 shrink-0 ${o.is_correct ? "text-ok" : ""}`}>{o.is_correct ? "✓" : ""}</span>
                <div className="min-w-0 flex-1">
                  <Markdown text={o.text} />
                </div>
              </li>
            ))}
          </ul>
        )}
        {t.type === "short" && t.answers && (
          <p className="mt-4 text-sm">
            Правильные ответы:{" "}
            {t.answers.map((a, i) => (
              <code key={i} className="mr-2 rounded bg-muted px-1.5 py-0.5">
                {a.mode === "regex" ? `/${a.value}/` : a.value}
              </code>
            ))}
          </p>
        )}
        {t.type === "long" && FILE_MODES[t.file_mode] && <p className="mt-4 text-sm text-fg-soft">{FILE_MODES[t.file_mode]}</p>}
      </section>

      {t.type === "code" && (
        <section className="space-y-3 rounded-2xl border border-line bg-surface p-5">
          <h2 className="text-sm font-medium text-fg-soft">
            Python · лимит {t.time_limit_s} с, {t.memory_limit_mb} МБ
          </h2>
          {t.starter_code && <CodeEditor value={t.starter_code} readOnly minHeight="60px" label="Заготовка" />}
          {t.tests && (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-fg-soft">
                  <th className="py-1 pr-3 font-medium">№</th>
                  <th className="py-1 pr-3 font-medium">Ввод</th>
                  <th className="py-1 font-medium">Ожидаемый вывод</th>
                </tr>
              </thead>
              <tbody>
                {t.tests.map((c, i) => (
                  <tr key={i} className="border-t border-line align-top">
                    <td className="py-1.5 pr-3">{i + 1}</td>
                    <td className="py-1.5 pr-3 font-mono whitespace-pre-wrap">{c.input || "—"}</td>
                    <td className="py-1.5 font-mono whitespace-pre-wrap">{c.expected}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {t.explanation && (
        <section className="rounded-2xl border border-line bg-surface p-5">
          <h2 className="mb-2 text-sm font-medium text-fg-soft">Разбор</h2>
          <Markdown text={t.explanation} />
        </section>
      )}
    </div>
  );
}

/** Модератор переносит задачу в другую тему рубрикатора (например, при проверке). */
function MoveTask({ taskId, topicId, onMoved }: { taskId: string; topicId: string | null; onMoved: () => void }) {
  const topics = useLoad(() => assessment.topics(), []);
  const [error, setError] = useState<string>();
  if (!topics.data) return null;
  return (
    <div className="max-w-md">
      {error && <Alert>{error}</Alert>}
      <TopicSelect
        rubric={buildRubric(topics.data)}
        value={topicId ?? ""}
        label="Тема в рубрикаторе"
        onChange={async (id) => {
          if (!id) return;
          setError(undefined);
          try {
            await assessment.moveTask(taskId, id);
            onMoved();
          } catch (e) {
            setError(errorText(e));
          }
        }}
      />
    </div>
  );
}
