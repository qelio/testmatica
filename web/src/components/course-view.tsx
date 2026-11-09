"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AdminContentActions } from "@/components/admin-content";
import { ThemePicker, ThemeScope } from "@/components/theme-scope";
import { Alert, Badge, Button, EmptyState, Field, Modal, Select, Spinner } from "@/components/ui";
import { classroom, content, type CourseStatus, type CourseTheme, type CourseTree } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorText, useLoad } from "@/lib/hooks";

export const STATUS_LABELS: Record<CourseStatus, { text: string; tone: "neutral" | "brand" | "warn" | "ok" }> = {
  private: { text: "моя библиотека", tone: "neutral" },
  pending: { text: "на проверке", tone: "brand" },
  published: { text: "опубликован", tone: "ok" },
  rejected: { text: "отклонён", tone: "warn" },
  removed: { text: "снят администратором", tone: "warn" },
};

/** Окно с одним полем — переименование и добавление разделов/модулей. */
export function PromptModal({
  open,
  title,
  label,
  initial = "",
  onClose,
  onSubmit,
}: {
  open: boolean;
  title: string;
  label: string;
  initial?: string;
  onClose: () => void;
  onSubmit: (value: string) => Promise<void>;
}) {
  return (
    <Modal open={open} onClose={onClose} title={title}>
      {open && <PromptForm label={label} initial={initial} onSubmit={onSubmit} />}
    </Modal>
  );
}

function PromptForm({ label, initial, onSubmit }: { label: string; initial: string; onSubmit: (v: string) => Promise<void> }) {
  const [value, setValue] = useState(initial);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(undefined);
        try {
          await onSubmit(value.trim());
        } catch (err) {
          setError(errorText(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      {error && <Alert>{error}</Alert>}
      <Field label={label} required autoFocus maxLength={200} value={value} onChange={(e) => setValue(e.target.value)} />
      <Button type="submit" loading={busy} disabled={!value.trim()} className="w-full">
        Сохранить
      </Button>
    </form>
  );
}

type Prompt = { title: string; label: string; initial?: string; action: (v: string) => Promise<unknown> };

export function CourseView({ id, base }: { id: string; base: string }) {
  const { status, user } = useAuth();
  const router = useRouter();
  const course = useLoad(() => content.course(id, true), [id, status]);
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const [editing, setEditing] = useState(false);
  const [report, setReport] = useState(false);
  const [error, setError] = useState<string>();

  async function act(action: () => Promise<unknown>) {
    setError(undefined);
    try {
      await action();
      course.reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  if (course.error) return <Alert>{course.error}</Alert>;
  const c = course.data;
  if (!c) return <Spinner />;
  const edit = c.can_edit;
  const isTeacher = !!user?.roles.includes("teacher");
  const staff = !!user?.roles.some((r) => r === "moderator" || r === "admin");
  const total = c.materials_count;
  // Черновик изменений опубликованного курса (решение №46): ученики видят прежнюю версию, пока модератор не примет.
  const draft = c.revision_of;
  const mine = c.owner_id === user?.id;

  return (
    <ThemeScope page theme={c.theme} className="mx-auto max-w-4xl">
    <div className="space-y-6">
      <div>
        <div className="flex flex-wrap items-center gap-2 text-sm text-fg-soft">
          <span className="tm-eyebrow">{[c.subject?.name, c.author_name].filter(Boolean).join(" · ")}</span>
          {c.status !== "published" && (c.owner_id === user?.id || user?.roles.includes("moderator")) && (
            <Badge tone={STATUS_LABELS[c.status].tone}>
              {c.revision_of ? (c.status === "pending" ? "изменения на проверке" : "черновик изменений") : STATUS_LABELS[c.status].text}
            </Badge>
          )}
          <span className="ml-auto">
            <AdminContentActions kind="course" id={c.id} removed={c.status === "removed"} onChanged={course.reload} />
          </span>
        </div>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">{c.title}</h1>
        {c.description && <p className="mt-2 max-w-2xl text-fg-soft">{c.description}</p>}
        {status === "authenticated" && total > 0 && (
          <div className="mt-4 max-w-sm">
            <div className="flex justify-between text-sm">
              <span className="text-fg-soft">Изучено</span>
              <span>
                {c.viewed_count} из {total}
              </span>
            </div>
            <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-ok" style={{ width: `${(100 * c.viewed_count) / total}%` }} />
            </div>
          </div>
        )}
      </div>

      {error && <Alert>{error}</Alert>}
      {draft && (
        <Alert kind="info">
          <b>Черновик изменений опубликованного курса.</b> Ученики и педагоги видят прежнюю версию, пока модератор не примет
          изменения. Тесты к модулям правятся в их редакторе — изменения уйдут на проверку вместе с черновиком.{" "}
          <Link href={`${base}/course/${draft}`} className="font-medium underline">
            Опубликованная версия
          </Link>
        </Alert>
      )}
      {!draft && mine && c.revision && (
        <Alert kind="info">
          {c.revision.status === "pending" ? (
            <b>Изменения курса на проверке у модератора.</b>
          ) : c.revision.status === "rejected" ? (
            <>
              <b>Модератор вернул изменения на доработку:</b> {c.revision.review_comment}
            </>
          ) : (
            <b>У курса есть черновик изменений — он ещё не отправлен на проверку.</b>
          )}{" "}
          <Link href={`${base}/course/${c.revision.id}`} className="font-medium underline">
            Открыть черновик
          </Link>
        </Alert>
      )}
      {c.status === "rejected" && c.review_comment && (
        <Alert kind="info">
          <b>Модератор вернул {draft ? "изменения" : "курс"} на доработку:</b> {c.review_comment}
        </Alert>
      )}
      {c.status === "removed" && (
        <Alert>
          <b>Курс снят с платформы администратором.</b> {c.review_comment}
        </Alert>
      )}
      {c.status === "pending" && mine && (
        <Alert kind="info">
          {draft ? "Изменения на проверке у модератора." : "Курс на проверке у модератора."} Пока идёт проверка, правка недоступна.
        </Alert>
      )}

      {(edit || c.owner_id === user?.id || isTeacher) && (
        <div className="flex flex-wrap gap-2">
          {edit && (
            <>
              <Button variant="secondary" onClick={() => setEditing(true)}>
                Описание и оформление
              </Button>
              <Button
                variant="secondary"
                onClick={() => setPrompt({ title: "Новый раздел", label: "Название раздела", action: (v) => content.addChild(c.id, v) })}
              >
                Добавить раздел
              </Button>
            </>
          )}
          {edit && (c.status === "private" || c.status === "rejected") && (
            <Button
              onClick={() =>
                act(async () => {
                  const saved = await content.submit(c.id);
                  // Изменения штатного редактора применяются сразу — черновика больше нет.
                  if (saved.id !== c.id) router.replace(`${base}/course/${saved.id}`);
                })
              }
            >
              {draft
                ? staff
                  ? "Опубликовать изменения"
                  : "Отправить изменения на проверку"
                : staff
                  ? "Опубликовать"
                  : "Отправить в публичную библиотеку"}
            </Button>
          )}
          {!draft && mine && !edit && c.status === "published" && (
            <Button
              onClick={() =>
                act(async () => {
                  const revision = await content.startRevision(c.id);
                  router.push(`${base}/course/${revision.id}`);
                })
              }
            >
              {c.revision ? "Открыть черновик изменений" : "Предложить изменения"}
            </Button>
          )}
          {mine && (c.status === "pending" || (c.status === "published" && !draft)) && (
            <Button variant="secondary" onClick={() => act(() => content.unpublish(c.id))}>
              {c.status === "pending" ? "Отозвать с проверки" : "Снять с публикации"}
            </Button>
          )}
          {isTeacher && total > 0 && (
            <Button variant="ghost" onClick={() => setReport(true)}>
              Прогресс учеников
            </Button>
          )}
          {edit && (
            <Button
              variant="ghost"
              className="text-danger"
              onClick={() =>
                window.confirm(
                  draft ? "Отменить черновик изменений? Опубликованный курс останется прежним." : `Удалить курс «${c.title}» со всеми материалами?`,
                ) &&
                act(async () => {
                  await content.deleteNode(c.id);
                  router.replace(draft ? `${base}/course/${draft}` : base);
                })
              }
            >
              {draft ? "Отменить изменения" : "Удалить курс"}
            </Button>
          )}
        </div>
      )}

      {c.sections.length === 0 ? (
        <EmptyState
          title="В курсе пока нет разделов"
          text={edit ? "Структура: раздел → модули → материалы." : undefined}
        />
      ) : (
        <ol className="space-y-4">
          {c.sections.map((s, si) => (
            <li key={s.id} className="tm-card rounded-2xl border border-line bg-surface">
              <div className="flex items-center gap-3 border-b border-line px-5 py-3">
                <h2 className="flex flex-1 items-center gap-3 font-semibold">
                  <span className="tm-num">
                    {si + 1}
                    <span className="tm-dot">.</span>
                  </span>
                  <span>{s.title}</span>
                </h2>
                {edit && (
                  <NodeTools
                    onRename={() => setPrompt({ title: "Раздел", label: "Название", initial: s.title, action: (v) => content.updateNode(s.id, { title: v }) })}
                    onAdd={() => setPrompt({ title: "Новый модуль", label: "Название модуля", action: (v) => content.addChild(s.id, v) })}
                    onMove={(d) => act(() => content.moveNode(s.id, d))}
                    onDelete={() => window.confirm(`Удалить раздел «${s.title}» со всеми модулями?`) && act(() => content.deleteNode(s.id))}
                    addLabel="+ модуль"
                  />
                )}
              </div>
              {s.modules.length === 0 ? (
                <p className="px-5 py-3 text-sm text-fg-soft">Модулей пока нет.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {s.modules.map((m) => {
                    const viewed = m.materials.filter((x) => x.viewed).length;
                    return (
                      <li key={m.id} className="flex items-center gap-3 px-5 py-3">
                        <Link href={`${base}/module/${m.id}`} className="min-w-0 flex-1 hover:text-brand-text">
                          <span className="font-medium">{m.title}</span>
                          <span className="ml-2 text-sm text-fg-soft">
                            {m.materials.length ? `${m.materials.length} мат.` : "пусто"}
                            {status === "authenticated" && m.materials.length > 0 && viewed === m.materials.length && " · ✓ изучено"}
                          </span>
                        </Link>
                        {edit && (
                          <NodeTools
                            onRename={() => setPrompt({ title: "Модуль", label: "Название", initial: m.title, action: (v) => content.updateNode(m.id, { title: v }) })}
                            onMove={(d) => act(() => content.moveNode(m.id, d))}
                            onDelete={() => window.confirm(`Удалить модуль «${m.title}»?`) && act(() => content.deleteNode(m.id))}
                          />
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          ))}
        </ol>
      )}

      <PromptModal
        open={!!prompt}
        title={prompt?.title ?? ""}
        label={prompt?.label ?? ""}
        initial={prompt?.initial}
        onClose={() => setPrompt(null)}
        onSubmit={async (v) => {
          await prompt!.action(v);
          setPrompt(null);
          course.reload();
        }}
      />
      {editing && <CourseDetailsModal course={c} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); course.reload(); }} />}
      {report && <ProgressModal courseId={c.id} onClose={() => setReport(false)} />}
    </div>
    </ThemeScope>
  );
}

function NodeTools({
  onRename,
  onAdd,
  onMove,
  onDelete,
  addLabel,
}: {
  onRename: () => void;
  onAdd?: () => void;
  onMove: (d: "up" | "down") => void;
  onDelete: () => void;
  addLabel?: string;
}) {
  const btn = "rounded-lg px-2 py-1 text-sm text-fg-soft hover:bg-muted hover:text-fg";
  return (
    <div className="flex shrink-0 items-center">
      {onAdd && (
        <button onClick={onAdd} className={`${btn} text-brand-text`}>
          {addLabel}
        </button>
      )}
      <button onClick={() => onMove("up")} className={btn} aria-label="Выше">
        ↑
      </button>
      <button onClick={() => onMove("down")} className={btn} aria-label="Ниже">
        ↓
      </button>
      <button onClick={onRename} className={btn}>
        Переименовать
      </button>
      <button onClick={onDelete} className={`${btn} hover:text-danger`} aria-label="Удалить">
        ✕
      </button>
    </div>
  );
}

export function CourseDetailsModal({
  course,
  onClose,
  onSaved,
}: {
  course?: CourseTree;
  onClose: () => void;
  onSaved: (id: string) => void;
}) {
  const subjects = useLoad(() => content.subjects(), []);
  const [title, setTitle] = useState(course?.title ?? "");
  const [subjectId, setSubjectId] = useState(course?.subject?.id ?? "");
  const [description, setDescription] = useState(course?.description ?? "");
  const [theme, setTheme] = useState<CourseTheme>(course?.theme ?? "classic");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  return (
    <Modal open onClose={onClose} title={course ? "Описание и оформление" : "Новый курс"}>
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(undefined);
          try {
            const data = { title, subject_id: subjectId || null, description, theme };
            const saved = course ? await content.updateNode(course.id, data) : await content.createCourse(data);
            onSaved(saved.id);
          } catch (err) {
            setError(errorText(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        {error && <Alert>{error}</Alert>}
        <Field label="Название" required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
        <Select label="Предмет" value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
          <option value="">Не выбран</option>
          {subjects.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </Select>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Описание</span>
          <textarea
            rows={3}
            maxLength={5000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
          />
        </label>
        <ThemePicker value={theme} onChange={setTheme} hint="Как курс, его модули, задачи и привязанные к нему тесты выглядят у учеников." />
        <Button type="submit" loading={busy} disabled={!title.trim()} className="w-full">
          {course ? "Сохранить" : "Создать курс"}
        </Button>
      </form>
    </Modal>
  );
}

function ProgressModal({ courseId, onClose }: { courseId: string; onClose: () => void }) {
  const groups = useLoad(() => classroom.groups(), []);
  const [groupId, setGroupId] = useState("");
  const report = useLoad(() => (groupId ? content.progress(courseId, { group_id: groupId }) : Promise.resolve(null)), [groupId]);
  return (
    <Modal open onClose={onClose} title="Прогресс учеников">
      <div className="space-y-4">
        <Select label="Группа" value={groupId} onChange={(e) => setGroupId(e.target.value)}>
          <option value="">Выберите…</option>
          {groups.data?.map((g) => (
            <option key={g.id} value={g.id}>
              {g.title}
            </option>
          ))}
        </Select>
        {report.error && <Alert>{report.error}</Alert>}
        {report.data && (
          <div className="max-h-96 overflow-auto rounded-xl border border-line">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line">
                  <th className="px-3 py-2 text-left font-medium">Ученик</th>
                  <th className="px-3 py-2 text-right font-medium">Изучено</th>
                </tr>
              </thead>
              <tbody>
                {report.data.students.map((s) => (
                  <tr key={s.id} className="border-b border-line/60 last:border-0">
                    <td className="px-3 py-2">{s.full_name}</td>
                    <td className="px-3 py-2 text-right">
                      {s.viewed.length} из {report.data!.materials.length}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Modal>
  );
}
