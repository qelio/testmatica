"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { AddStudentModal } from "@/components/add-student";
import { BillingSelect, PaidBadge } from "@/components/billing";
import { SubjectSelect } from "@/components/subject-select";
import { ExamBoardView } from "@/components/exams";
import { Alert, Badge, Button, EmptyState, Field, Modal, Spinner } from "@/components/ui";
import { classroom, type GroupDetail } from "@/lib/api";
import { pluralStudents } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

export default function GroupPage() {
  const { id } = useParams<{ id: string }>();
  const group = useLoad(() => classroom.group(id), [id]);
  const students = useLoad(() => classroom.students(), []);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();

  if (group.error) {
    return (
      <div className="mx-auto max-w-4xl space-y-4">
        <BackLink />
        <Alert>{group.error}</Alert>
      </div>
    );
  }
  const g = group.data;
  if (!g) return <Spinner />;

  const memberIds = new Set(g.members.map((m) => m.student_id));
  const candidates = (students.data ?? []).filter((s) => s.status === "active" && !memberIds.has(s.student_id));

  async function signOut(action: () => Promise<{ count: number }>, text: (n: number) => string) {
    setError(undefined);
    setNotice(undefined);
    try {
      setNotice(text((await action()).count));
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function act(action: () => Promise<unknown>) {
    setError(undefined);
    try {
      await action();
      group.reload();
      students.reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <BackLink />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{g.title}</h1>
            <Badge>{g.kind === "class" ? "класс" : "группа"}</Badge>
            <PaidBadge paid={g.paid} />
            {g.archived && <Badge tone="warn">в архиве</Badge>}
          </div>
          <p className="mt-1 text-fg-soft">
            {[g.subject, pluralStudents(g.student_count)].filter(Boolean).join(" · ")}
          </p>
          {g.description && <p className="mt-2 max-w-2xl text-sm">{g.description}</p>}
        </div>
        <div className="flex gap-2">
          <Link
            href={`/dashboard/journal?group=${g.id}`}
            className="inline-flex h-11 items-center rounded-xl border border-line bg-surface px-4 text-sm font-medium hover:bg-muted"
          >
            Журнал
          </Link>
          <Button variant="secondary" onClick={() => setEditing(true)}>
            Изменить
          </Button>
          {!g.archived && <Button onClick={() => setAdding(true)}>Добавить ученика</Button>}
        </div>
      </div>
      {g.members.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-surface px-5 py-3 text-sm">
          <span className="min-w-0 flex-1 text-fg-soft">
            Ученики оставили вход на школьных компьютерах? Можно выйти из их аккаунтов — на всех устройствах сразу.
          </span>
          <Button
            variant="secondary"
            className="h-9"
            onClick={() =>
              window.confirm(`Выйти из аккаунтов всех учеников «${g.title}» на всех устройствах? Войти снова они смогут со своим логином и паролем.`) &&
              signOut(() => classroom.signOutGroup(g.id), (n) => `Выход выполнен у учеников: ${n}.`)
            }
          >
            Выйти у всех учеников
          </Button>
        </div>
      )}

      {error && <Alert>{error}</Alert>}
      {notice && <Alert kind="success">{notice}</Alert>}

      {g.members.length === 0 ? (
        <EmptyState
          title="В группе пока нет учеников"
          action={!g.archived && <Button onClick={() => setAdding(true)}>Добавить ученика</Button>}
        />
      ) : (
        <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
          {g.members.map((m, i) => (
            <li key={m.student_id} className="flex items-center gap-3 px-5 py-3">
              <span className="w-6 text-right text-sm text-fg-soft">{i + 1}</span>
              <div className="min-w-0 flex-1">
                <Link href={`/dashboard/students/${m.student_id}`} className="block truncate font-medium hover:underline">
                  {m.full_name}
                </Link>
                {m.login && <p className="font-mono text-sm text-fg-soft">{m.login}</p>}
              </div>
              <Button
                variant="ghost"
                className="h-9 text-fg-soft"
                title="Выйти из аккаунта ученика на всех устройствах"
                onClick={() => signOut(() => classroom.signOutStudent(m.student_id), () => `${m.full_name}: выход выполнен на всех устройствах.`)}
              >
                Выйти из аккаунта
              </Button>
              <Button
                variant="ghost"
                className="h-9 text-fg-soft"
                onClick={() => act(() => classroom.removeMember(g.id, m.student_id))}
              >
                Убрать из группы
              </Button>
            </li>
          ))}
        </ul>
      )}

      {g.members.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Подготовка к ЕГЭ и ОГЭ</h2>
          <ExamBoardView targetType="group" targetId={g.id} />
        </section>
      )}

      <div className="border-t border-line pt-4">
        <Button
          variant="ghost"
          onClick={() => act(() => (g.archived ? classroom.restoreGroup(g.id) : classroom.archiveGroup(g.id)))}
        >
          {g.archived ? "Вернуть из архива" : "Переместить в архив"}
        </Button>
      </div>

      <AddStudentModal
        open={adding}
        onClose={() => setAdding(false)}
        onDone={() => {
          group.reload();
          students.reload();
        }}
        groupId={g.id}
        candidates={candidates}
      />
      <EditGroupModal
        group={g}
        open={editing}
        onClose={() => setEditing(false)}
        onSaved={() => {
          setEditing(false);
          group.reload();
        }}
      />
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/dashboard/groups" className="inline-flex items-center gap-1 text-sm text-fg-soft hover:text-fg">
      ← Все группы
    </Link>
  );
}

function EditGroupModal({
  group,
  open,
  onClose,
  onSaved,
}: {
  group: GroupDetail;
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({ title: group.title, subject: group.subject ?? "", description: group.description, paid: group.paid });
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  return (
    <Modal open={open} onClose={onClose} title="Изменить группу">
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          setLoading(true);
          setError(undefined);
          try {
            await classroom.updateGroup(group.id, {
              title: form.title,
              subject: form.subject || null,
              description: form.description,
              paid: form.paid,
            });
            onSaved();
          } catch (err) {
            setError(errorText(err));
          } finally {
            setLoading(false);
          }
        }}
      >
        {error && <Alert>{error}</Alert>}
        <Field label="Название" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <SubjectSelect value={form.subject} onChange={(subject) => setForm({ ...form, subject })} />
        <div>
          <BillingSelect label="Занятия" value={form.paid} free="Бесплатные" paid="Платные" onChange={(paid) => setForm({ ...form, paid })} />
          <p className="mt-1.5 text-xs text-fg-soft">Действует на новые занятия; уже созданные не меняются.</p>
        </div>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Описание</span>
          <textarea
            rows={3}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            className="w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
          />
        </label>
        <Button type="submit" loading={loading} className="w-full">
          Сохранить
        </Button>
      </form>
    </Modal>
  );
}
