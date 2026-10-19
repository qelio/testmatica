"use client";

import Link from "next/link";
import { useState } from "react";

import { AddStudentModal, CredentialsView } from "@/components/add-student";
import { BillingSelect, PaidBadge } from "@/components/billing";
import { NameFields, splitFullName } from "@/components/name-fields";
import { SubjectSelect } from "@/components/subject-select";
import { Alert, Badge, Button, EmptyState, Field, Modal, Select, Spinner } from "@/components/ui";
import { classroom, type Group, type Invitation, type Student, type StudentCredentials } from "@/lib/api";
import { pluralStudents, SOURCE_LABELS } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";
import { fmtDate } from "@/lib/dates";

type Tab = "groups" | "students" | "invitations";

export default function GroupsPage() {
  const [tab, setTab] = useState<Tab>("groups");
  const [archived, setArchived] = useState(false);
  const groups = useLoad(() => classroom.groups(archived), [archived]);
  const students = useLoad(() => classroom.students(), []);
  const invitations = useLoad(() => classroom.invitations(), []);
  const [creating, setCreating] = useState(false);
  const [adding, setAdding] = useState(false);

  const reloadAll = () => {
    groups.reload();
    students.reload();
    invitations.reload();
  };

  const tabs: { value: Tab; label: string; count?: number }[] = [
    { value: "groups", label: "Классы и группы", count: groups.data?.length },
    { value: "students", label: "Ученики", count: students.data?.length },
    { value: "invitations", label: "Приглашения", count: invitations.data?.length },
  ];

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Классы, группы и ученики</h1>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setAdding(true)}>
            Добавить ученика
          </Button>
          <Button onClick={() => setCreating(true)}>Создать класс или группу</Button>
        </div>
      </div>

      <div className="flex gap-1 border-b border-line" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.value}
            role="tab"
            aria-selected={tab === t.value}
            onClick={() => setTab(t.value)}
            className={`-mb-px border-b-2 px-3 py-2.5 text-sm font-medium ${tab === t.value ? "border-brand text-fg" : "border-transparent text-fg-soft hover:text-fg"}`}
          >
            {t.label}
            {!!t.count && <span className="ml-1.5 text-fg-soft">{t.count}</span>}
          </button>
        ))}
      </div>

      {tab === "groups" && (
        <GroupsTab
          groups={groups.data}
          error={groups.error}
          archived={archived}
          setArchived={setArchived}
          onCreate={() => setCreating(true)}
        />
      )}
      {tab === "students" && (
        <StudentsTab
          students={students.data}
          groups={groups.data ?? []}
          error={students.error}
          onChanged={reloadAll}
          onAdd={() => setAdding(true)}
        />
      )}
      {tab === "invitations" && (
        <InvitationsTab items={invitations.data} error={invitations.error} reload={invitations.reload} />
      )}

      <CreateGroupModal
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={() => {
          setCreating(false);
          groups.reload();
        }}
      />
      <AddStudentModal open={adding} onClose={() => setAdding(false)} onDone={reloadAll} />
    </div>
  );
}

function GroupsTab({
  groups,
  error,
  archived,
  setArchived,
  onCreate,
}: {
  groups: Group[] | null;
  error?: string;
  archived: boolean;
  setArchived: (v: boolean) => void;
  onCreate: () => void;
}) {
  return (
    <div className="space-y-4">
      <label className="flex items-center gap-2 text-sm text-fg-soft">
        <input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} className="accent-brand" />
        Показать архив
      </label>
      {error && <Alert>{error}</Alert>}
      {!groups && !error && <Spinner />}
      {groups?.length === 0 && (
        <EmptyState
          title={archived ? "В архиве пусто" : "Пока нет ни одной группы"}
          text={archived ? undefined : "Создайте класс или группу и добавьте в неё учеников."}
          action={!archived && <Button onClick={onCreate}>Создать</Button>}
        />
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {groups?.map((g) => (
          <Link
            key={g.id}
            href={`/dashboard/groups/${g.id}`}
            className="rounded-2xl border border-line bg-surface p-5 transition-colors hover:border-brand/50"
          >
            <div className="flex items-start justify-between gap-2">
              <h2 className="text-lg font-semibold">{g.title}</h2>
              <span className="flex gap-1">
                <PaidBadge paid={g.paid} />
                <Badge>{g.kind === "class" ? "класс" : "группа"}</Badge>
              </span>
            </div>
            {g.subject && <p className="mt-1 text-sm text-fg-soft">{g.subject}</p>}
            {g.shared && <p className="mt-1 text-sm text-brand">класс коллеги · {g.owner_name}</p>}
            <p className="mt-4 text-sm text-fg-soft">{pluralStudents(g.student_count)}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}

function StudentsTab({
  students,
  groups,
  error,
  onChanged,
  onAdd,
}: {
  students: Student[] | null;
  groups: Group[];
  error?: string;
  onChanged: () => void;
  onAdd: () => void;
}) {
  const [editing, setEditing] = useState<Student | null>(null);
  const titles = Object.fromEntries(groups.map((g) => [g.id, g.title]));
  if (error) return <Alert>{error}</Alert>;
  if (!students) return <Spinner />;
  if (!students.length) {
    return (
      <EmptyState
        title="У вас пока нет учеников"
        text="Пригласите ученика по email, найдите зарегистрированного или создайте аккаунт сами."
        action={<Button onClick={onAdd}>Добавить ученика</Button>}
      />
    );
  }
  return (
    <>
      <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
        {students.map((s) => (
          <li key={s.student_id} className="flex flex-wrap items-center gap-3 px-5 py-3.5">
            <div className="min-w-0 flex-1">
              <p className="font-medium">
                {s.full_name}
                {s.login && <span className="ml-2 font-mono text-sm text-fg-soft">{s.login}</span>}
              </p>
              <p className="mt-0.5 text-sm text-fg-soft">
                {SOURCE_LABELS[s.source]}
                {s.group_ids.length > 0 && ` · ${s.group_ids.map((id) => titles[id] ?? "архивная группа").join(", ")}`}
                {s.paid && " · индивидуально платно"}
              </p>
            </div>
            {s.status === "pending" ? (
              <Badge tone="warn">ждёт подтверждения</Badge>
            ) : (
              <>
                <Link href={`/dashboard/journal?student=${s.student_id}`} className="text-sm font-medium text-brand hover:underline">
                  Журнал
                </Link>
                <Link href={`/dashboard/students/${s.student_id}`} className="text-sm font-medium text-brand hover:underline">
                  Прогресс
                </Link>
              </>
            )}
            <Button variant="ghost" className="h-9" onClick={() => setEditing(s)}>
              Управление
            </Button>
          </li>
        ))}
      </ul>
      <StudentModal key={editing?.student_id ?? "none"} student={editing} onClose={() => setEditing(null)} onChanged={onChanged} />
    </>
  );
}

function StudentModal({
  student,
  onClose,
  onChanged,
}: {
  student: Student | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [name, setName] = useState(() => splitFullName(student?.full_name ?? ""));
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [credentials, setCredentials] = useState<StudentCredentials | null>(null);
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const [signedOut, setSignedOut] = useState(false);

  function close() {
    setCredentials(null);
    setConfirmUnlink(false);
    setError(undefined);
    onClose();
  }

  async function act(action: () => Promise<void>) {
    setLoading(true);
    setError(undefined);
    try {
      await action();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }

  if (!student) return <Modal open={false} onClose={close} title="">{null}</Modal>;

  return (
    <Modal open onClose={close} title={student.full_name}>
      {credentials ? (
        <CredentialsView credentials={credentials} onClose={close} />
      ) : (
        <div className="space-y-5">
          {error && <Alert>{error}</Alert>}
          <div>
            <BillingSelect
              label="Индивидуальные занятия"
              value={student.paid}
              free="Бесплатные"
              paid="Платные"
              onChange={(paid) =>
                act(async () => {
                  await classroom.setStudentBilling(student.student_id, paid);
                  onChanged();
                  close();
                })
              }
            />
            <p className="mt-1.5 text-xs text-fg-soft">
              Не зависит от групп: ученик может бесплатно ходить в класс и отдельно заниматься с вами платно. Действует на новые занятия.
            </p>
          </div>
          {student.managed ? (
            <>
              <form
                className="space-y-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  act(async () => {
                    await classroom.renameStudent(student.student_id, name);
                    onChanged();
                    close();
                  });
                }}
              >
                <NameFields value={name} onChange={setName} idPrefix="student-name" autoComplete={false} />
                <Button type="submit" variant="secondary" loading={loading} disabled={!name.last_name.trim() || !name.first_name.trim()}>
                  Сохранить
                </Button>
              </form>
              <div>
                <Button
                  variant="secondary"
                  loading={loading}
                  onClick={() => act(async () => setCredentials(await classroom.resetPassword(student.student_id)))}
                >
                  Сбросить пароль
                </Button>
                <p className="mt-1.5 text-sm text-fg-soft">Будет создан новый пароль, старый перестанет работать.</p>
              </div>
            </>
          ) : (
            <p className="text-sm text-fg-soft">
              Ученик сам управляет своим аккаунтом: имя и пароль может изменить только он.
            </p>
          )}
          {student.status === "active" && (
            <div>
              <Button
                variant="secondary"
                loading={loading}
                onClick={() =>
                  act(async () => {
                    await classroom.signOutStudent(student.student_id);
                    setSignedOut(true);
                  })
                }
              >
                Выйти из аккаунта
              </Button>
              <p className="mt-1.5 text-sm text-fg-soft">
                {signedOut
                  ? "Готово: вход завершён на всех устройствах. Войти снова можно со своим логином и паролем."
                  : "Если ученик оставил вход на школьном компьютере — завершить его на всех устройствах."}
              </p>
            </div>
          )}
          <div className="border-t border-line pt-4">
            {confirmUnlink ? (
              <div className="space-y-3">
                <p className="text-sm">
                  {student.status === "pending"
                    ? "Отменить запрос?"
                    : "Отвязать ученика? Он выйдет из всех ваших групп. Аккаунт ученика не удаляется."}
                </p>
                <div className="flex gap-2">
                  <Button variant="secondary" onClick={() => setConfirmUnlink(false)}>
                    Нет
                  </Button>
                  <Button
                    className="bg-danger hover:bg-danger/90"
                    loading={loading}
                    onClick={() =>
                      act(async () => {
                        await classroom.unlinkStudent(student.student_id);
                        onChanged();
                        close();
                      })
                    }
                  >
                    Да, отвязать
                  </Button>
                </div>
              </div>
            ) : (
              <button onClick={() => setConfirmUnlink(true)} className="text-sm font-medium text-danger hover:underline">
                {student.status === "pending" ? "Отменить запрос" : "Отвязать ученика"}
              </button>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}

function InvitationsTab({
  items,
  error,
  reload,
}: {
  items: Invitation[] | null;
  error?: string;
  reload: () => void;
}) {
  if (error) return <Alert>{error}</Alert>;
  if (!items) return <Spinner />;
  if (!items.length) {
    return <EmptyState title="Нет активных приглашений" text="Отправленные и ещё не принятые приглашения появятся здесь." />;
  }
  return (
    <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
      {items.map((inv) => (
        <li key={inv.id} className="flex items-center gap-3 px-5 py-3.5">
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{inv.email}</p>
            <p className="text-sm text-fg-soft">действует до {fmtDate(inv.expires_at, { day: "numeric", month: "long", year: "numeric" })}</p>
          </div>
          <Button
            variant="ghost"
            className="h-9 text-danger"
            onClick={async () => {
              await classroom.revokeInvitation(inv.id);
              reload();
            }}
          >
            Отменить
          </Button>
        </li>
      ))}
    </ul>
  );
}

function CreateGroupModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (g: Group) => void;
}) {
  const [form, setForm] = useState<{ title: string; subject: string; kind: "class" | "group"; paid: boolean }>({
    title: "",
    subject: "",
    kind: "class",
    paid: false,
  });
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);

  return (
    <Modal open={open} onClose={onClose} title="Новый класс или группа">
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          setLoading(true);
          setError(undefined);
          try {
            const group = await classroom.createGroup({
              title: form.title,
              subject: form.subject || null,
              kind: form.kind,
              paid: form.paid,
            });
            setForm({ title: "", subject: "", kind: "class", paid: false });
            onCreated(group);
          } catch (err) {
            setError(errorText(err));
          } finally {
            setLoading(false);
          }
        }}
      >
        {error && <Alert>{error}</Alert>}
        <div className="grid grid-cols-2 gap-3">
          <Select label="Тип" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as "class" | "group" })}>
            <option value="class">Класс</option>
            <option value="group">Группа</option>
          </Select>
          <BillingSelect label="Занятия" value={form.paid} onChange={(paid) => setForm({ ...form, paid })} free="Бесплатные" paid="Платные" />
        </div>
        <p className="-mt-2 text-xs text-fg-soft">
          Школьный класс или кружок — бесплатно. Платные занятия ученики будут оплачивать через платформу (появится на следующем этапе).
        </p>
        <Field
          label="Название"
          placeholder={form.kind === "class" ? "7А" : "Подготовка к ЕГЭ"}
          required
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
        />
        <SubjectSelect value={form.subject} onChange={(subject) => setForm({ ...form, subject })} />
        <Button type="submit" loading={loading} className="w-full">
          Создать
        </Button>
      </form>
    </Modal>
  );
}
