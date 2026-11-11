"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { AddStudentModal } from "@/components/add-student";
import { BillingSelect, PaidBadge } from "@/components/billing";
import { ClassWorks } from "@/components/class-works";
import { SubjectSelect } from "@/components/subject-select";
import { ExamBoardView } from "@/components/exams";
import { Alert, Badge, Button, EmptyState, Field, Modal, Select, Spinner } from "@/components/ui";
import { classroom, colleagues, type GroupDetail, SHARE_PERMISSIONS, type SharePermission } from "@/lib/api";
import { useAuth } from "@/lib/auth";
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
  const me = useAuth().user;
  const router = useRouter();

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

  // Класс коллеги (решение №57): состав и класс — по правам, которые дал владелец (№61).
  const own = !g.shared;
  const perms = new Set(g.permissions ?? []);
  const canManage = own || perms.has("manage");
  const canAdd = canManage || perms.has("add_students");
  // «Работы класса» — только у класса с коллегами (больше одного педагога) и с правом на работы.
  const showWorks = (g.shared || g.shares.length > 0) && (own || perms.has("class_works"));
  const memberIds = new Set(g.members.map((m) => m.student_id));
  // Коллега добавляет только своих учеников — не тех, кто пришёл к нему через общий класс.
  const candidates = (students.data ?? []).filter(
    (s) => s.status === "active" && !memberIds.has(s.student_id) && (own || s.source !== "colleague"),
  );

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
            {g.shared && <Badge tone="brand">класс коллеги</Badge>}
          </div>
          {g.shared && (
            <p className="mt-1 text-sm">
              Класс ведёт <b>{g.owner_name}</b> и поделился им с вами: ставьте классу и ученикам свои занятия, назначайте тесты.
              {perms.size > 0
                ? ` Ещё вам доступно: ${SHARE_PERMISSIONS.filter((p) => perms.has(p.id)).map((p) => p.label.toLowerCase()).join(", ")}.`
                : " Состав меняет только он."}
            </p>
          )}
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
          {canManage && (
            <Button variant="secondary" onClick={() => setEditing(true)}>
              Изменить
            </Button>
          )}
          {canAdd && !g.archived && <Button onClick={() => setAdding(true)}>Добавить ученика</Button>}
        </div>
      </div>
      {own && <SharesBlock g={g} onChanged={() => group.reload()} onError={setError} />}

      {own && g.members.length > 0 && (
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
          action={canAdd && !g.archived && <Button onClick={() => setAdding(true)}>Добавить ученика</Button>}
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
                {m.added_by_name && <p className="text-xs text-fg-soft">добавил(а) {m.added_by_name}</p>}
              </div>
              {!own && m.can_remove && (
                <Button variant="ghost" className="h-9 text-fg-soft" onClick={() => act(() => classroom.removeMember(g.id, m.student_id))}>
                  Убрать из группы
                </Button>
              )}
              {own && (
                <>
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
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      {showWorks && <ClassWorks groupId={g.id} />}

      {g.members.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Подготовка к ЕГЭ и ОГЭ</h2>
          <ExamBoardView targetType="group" targetId={g.id} />
        </section>
      )}

      <div className="border-t border-line pt-4">
        {own ? (
          <Button
            variant="ghost"
            onClick={() => act(() => (g.archived ? classroom.restoreGroup(g.id) : classroom.archiveGroup(g.id)))}
          >
            {g.archived ? "Вернуть из архива" : "Переместить в архив"}
          </Button>
        ) : (
          <Button
            variant="ghost"
            className="text-danger"
            onClick={async () => {
              if (!me || !window.confirm(`Отказаться от класса «${g.title}»? Ваши занятия и работы останутся, но ученики класса перестанут быть вашими.`)) return;
              try {
                await classroom.unshareGroup(g.id, me.id);
                router.replace("/dashboard/groups");
              } catch (e) {
                setError(errorText(e));
              }
            }}
          >
            Отказаться от класса
          </Button>
        )}
      </div>

      {!own && (
        <ColleagueAddModal
          open={adding}
          onClose={() => setAdding(false)}
          groupId={g.id}
          candidates={candidates}
          onDone={() => {
            group.reload();
            students.reload();
          }}
        />
      )}
      <AddStudentModal
        open={adding && own}
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

/** Владельцу — с какими коллегами поделился классом (решение №57). */
function SharesBlock({ g, onChanged, onError }: { g: GroupDetail; onChanged: () => void; onError: (e: string) => void }) {
  const list = useLoad(() => colleagues.list(), []);
  const [pick, setPick] = useState("");
  const [perms, setPerms] = useState<SharePermission[]>([]);
  const [busy, setBusy] = useState(false);
  const sharedIds = new Set(g.shares.map((s) => s.user_id));
  const options = (list.data?.colleagues ?? []).filter((c) => !sharedIds.has(c.user_id));

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    try {
      await action();
      setPick("");
      setPerms([]);
      onChanged();
    } catch (e) {
      onError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-3 rounded-2xl border border-line bg-surface px-5 py-4">
      <h2 className="font-medium">Коллеги с доступом к классу</h2>
      <p className="text-sm text-fg-soft">
        Коллега всегда видит класс и учеников, ставит им свои занятия и назначает тесты; ваши занятия у него в расписании не появятся.
        Остальное — по правам, которые вы отметите. Удалить класс, отправить в архив и делиться им может только владелец.
      </p>
      {g.shares.length > 0 && (
        <ul className="divide-y divide-line rounded-xl border border-line">
          {g.shares.map((s) => (
            <li key={s.user_id} className="flex flex-wrap items-start gap-3 px-4 py-2.5 text-sm">
              <div className="min-w-0 flex-1 space-y-1.5">
                <span className="font-medium">{s.full_name}</span>
                <PermissionBoxes
                  value={s.permissions}
                  disabled={busy}
                  onChange={(next) => run(() => classroom.setSharePermissions(g.id, s.user_id, next))}
                />
              </div>
              <Button
                variant="ghost"
                className="h-9 text-danger"
                disabled={busy}
                onClick={() =>
                  window.confirm(`Закрыть доступ коллеге ${s.full_name}? Его занятия и оценки останутся, но ученики класса перестанут быть его.`) &&
                  run(() => classroom.unshareGroup(g.id, s.user_id))
                }
              >
                Закрыть доступ
              </Button>
            </li>
          ))}
        </ul>
      )}
      {list.data && !list.data.colleagues.length ? (
        <p className="text-sm">
          Коллег пока нет —{" "}
          <Link href="/dashboard/colleagues" className="text-brand-text hover:underline">
            добавьте их в «Мои коллеги»
          </Link>
          .
        </p>
      ) : (
        options.length > 0 && (
          <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <select
              value={pick}
              onChange={(e) => setPick(e.target.value)}
              aria-label="Коллега"
              className="h-10 min-w-0 flex-1 rounded-xl border border-line bg-surface px-3 text-sm"
            >
              <option value="">Выберите коллегу</option>
              {options.map((c) => (
                <option key={c.user_id} value={c.user_id}>
                  {c.full_name}
                </option>
              ))}
            </select>
            <Button className="h-10" loading={busy} disabled={!pick} onClick={() => run(() => classroom.shareGroup(g.id, pick, perms))}>
              Поделиться
            </Button>
          </div>
          {pick && <PermissionBoxes value={perms} onChange={setPerms} />}
          </div>
        )
      )}
    </section>
  );
}

function PermissionBoxes({
  value,
  disabled,
  onChange,
}: {
  value: SharePermission[];
  disabled?: boolean;
  onChange: (next: SharePermission[]) => void;
}) {
  return (
    <div className="grid gap-1.5 sm:grid-cols-2">
      {SHARE_PERMISSIONS.map((p) => (
        <label key={p.id} className="flex items-start gap-2 text-sm" title={p.hint}>
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4 accent-brand"
            checked={value.includes(p.id)}
            disabled={disabled}
            onChange={() => onChange(value.includes(p.id) ? value.filter((x) => x !== p.id) : [...value, p.id])}
          />
          <span>
            {p.label}
            <span className="block text-xs text-fg-soft">{p.hint}</span>
          </span>
        </label>
      ))}
    </div>
  );
}

/** Коллега с правом добавляет в общий класс своих учеников (решение №61). */
function ColleagueAddModal({
  open,
  onClose,
  groupId,
  candidates,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  groupId: string;
  candidates: { student_id: string; full_name: string }[];
  onDone: () => void;
}) {
  const [pick, setPick] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  return (
    <Modal open={open} onClose={onClose} title="Добавить своего ученика">
      <div className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {candidates.length === 0 ? (
          <p className="text-sm text-fg-soft">
            Своих учеников, которых ещё нет в классе, у вас нет. Добавьте ученика в разделе «Классы, группы, ученики».
          </p>
        ) : (
          <>
            <p className="text-sm text-fg-soft">Ученик станет учеником и владельца класса. Убрать его сможете вы и владелец.</p>
            <Select label="Ученик" value={pick} onChange={(e) => setPick(e.target.value)}>
              <option value="">Выберите</option>
              {candidates.map((c) => (
                <option key={c.student_id} value={c.student_id}>
                  {c.full_name}
                </option>
              ))}
            </Select>
            <Button
              className="w-full"
              loading={busy}
              disabled={!pick}
              onClick={async () => {
                setBusy(true);
                setError(undefined);
                try {
                  await classroom.addMember(groupId, pick);
                  setPick("");
                  onDone();
                  onClose();
                } catch (e) {
                  setError(errorText(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              Добавить в класс
            </Button>
          </>
        )}
      </div>
    </Modal>
  );
}
