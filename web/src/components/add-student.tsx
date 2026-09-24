"use client";

import { useState } from "react";

import { Alert, Button, Field, Modal } from "@/components/ui";
import { classroom, type Student, type StudentCredentials } from "@/lib/api";
import { errorText } from "@/lib/hooks";

type Method = "existing" | "invite" | "request" | "manual";

const METHODS: { value: Method; label: string; hint: string }[] = [
  { value: "existing", label: "Мои ученики", hint: "Добавить в группу ученика, который уже привязан к вам." },
  { value: "invite", label: "По email", hint: "Ученик получит письмо со ссылкой, сам задаст пароль и зарегистрируется." },
  {
    value: "request",
    label: "Уже зарегистрирован",
    hint: "Найдём ученика по логину или email и отправим запрос — он появится у вас после подтверждения.",
  },
  {
    value: "manual",
    label: "Создать аккаунт",
    hint: "Вы задаёте имя, логин и пароль сами — email не нужен. Подходит для младших школьников.",
  },
];

/** Добавление ученика тремя способами из ТЗ (+ «из моих учеников», если открыто из группы). */
export function AddStudentModal({
  open,
  onClose,
  onDone,
  groupId,
  candidates = [],
}: {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
  groupId?: string;
  candidates?: Student[];
}) {
  const methods = groupId ? METHODS : METHODS.filter((m) => m.value !== "existing");
  const [method, setMethod] = useState<Method>(groupId && candidates.length ? "existing" : "invite");
  const [credentials, setCredentials] = useState<StudentCredentials | null>(null);

  function close() {
    setCredentials(null);
    onClose();
  }

  return (
    <Modal open={open} onClose={close} title="Добавить ученика">
      {credentials ? (
        <CredentialsView credentials={credentials} onClose={close} />
      ) : (
        <div className="space-y-5">
          <div className="flex flex-wrap gap-1.5" role="tablist">
            {methods.map((m) => (
              <button
                key={m.value}
                role="tab"
                aria-selected={method === m.value}
                onClick={() => setMethod(m.value)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium ${method === m.value ? "bg-brand text-white" : "bg-muted text-fg-soft hover:text-fg"}`}
              >
                {m.label}
              </button>
            ))}
          </div>
          <p className="text-sm text-fg-soft">{methods.find((m) => m.value === method)?.hint}</p>
          {method === "existing" && groupId && (
            <ExistingForm groupId={groupId} candidates={candidates} onDone={onDone} />
          )}
          {method === "invite" && <InviteForm groupId={groupId} onDone={onDone} />}
          {method === "request" && <RequestForm groupId={groupId} onDone={onDone} />}
          {method === "manual" && (
            <ManualForm
              groupId={groupId}
              onCreated={(c) => {
                setCredentials(c);
                onDone();
              }}
            />
          )}
        </div>
      )}
    </Modal>
  );
}

function useSubmit() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [success, setSuccess] = useState<string>();
  async function run(action: () => Promise<string | void>) {
    setLoading(true);
    setError(undefined);
    setSuccess(undefined);
    try {
      const message = await action();
      if (message) setSuccess(message);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }
  return { loading, error, success, run };
}

function Feedback({ error, success }: { error?: string; success?: string }) {
  if (error) return <Alert>{error}</Alert>;
  if (success) return <Alert kind="success">{success}</Alert>;
  return null;
}

function ExistingForm({ groupId, candidates, onDone }: { groupId: string; candidates: Student[]; onDone: () => void }) {
  const { loading, error, success, run } = useSubmit();
  if (!candidates.length) {
    return <p className="text-sm text-fg-soft">Все ваши ученики уже в этой группе.</p>;
  }
  return (
    <div className="space-y-3">
      <Feedback error={error} success={success} />
      <ul className="max-h-72 divide-y divide-line overflow-y-auto rounded-xl border border-line">
        {candidates.map((s) => (
          <li key={s.student_id} className="flex items-center justify-between gap-3 px-3 py-2.5">
            <span className="min-w-0 truncate">{s.full_name}</span>
            <Button
              variant="secondary"
              className="h-9 shrink-0"
              loading={loading}
              onClick={() =>
                run(async () => {
                  await classroom.addMember(groupId, s.student_id);
                  onDone();
                  return `${s.full_name} добавлен(а) в группу`;
                })
              }
            >
              Добавить
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function InviteForm({ groupId, onDone }: { groupId?: string; onDone: () => void }) {
  const [email, setEmail] = useState("");
  const { loading, error, success, run } = useSubmit();
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        run(async () => {
          await classroom.invite(email, groupId);
          onDone();
          setEmail("");
          return `Приглашение отправлено на ${email}`;
        });
      }}
    >
      <Feedback error={error} success={success} />
      <Field label="Email ученика" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <Button type="submit" loading={loading} className="w-full">
        Отправить приглашение
      </Button>
    </form>
  );
}

function RequestForm({ groupId, onDone }: { groupId?: string; onDone: () => void }) {
  const [identifier, setIdentifier] = useState("");
  const { loading, error, success, run } = useSubmit();
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        run(async () => {
          const s = await classroom.requestLink(identifier, groupId);
          onDone();
          setIdentifier("");
          return s.status === "pending"
            ? `Запрос отправлен: ${s.full_name}. Ученик появится после подтверждения.`
            : `${s.full_name} добавлен(а) в группу`;
        });
      }}
    >
      <Feedback error={error} success={success} />
      <Field
        label="Логин или email ученика"
        required
        value={identifier}
        onChange={(e) => setIdentifier(e.target.value)}
      />
      <Button type="submit" loading={loading} className="w-full">
        Отправить запрос
      </Button>
    </form>
  );
}

function ManualForm({ groupId, onCreated }: { groupId?: string; onCreated: (c: StudentCredentials) => void }) {
  const [form, setForm] = useState({ full_name: "", login: "", password: "" });
  const { loading, error, run } = useSubmit();
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        run(async () => {
          onCreated(
            await classroom.createManual({
              full_name: form.full_name,
              login: form.login || null,
              password: form.password || null,
              group_id: groupId,
            }),
          );
        });
      }}
    >
      <Feedback error={error} />
      <Field
        label="Имя и фамилия"
        required
        value={form.full_name}
        onChange={(e) => setForm({ ...form, full_name: e.target.value })}
      />
      <Field
        label="Логин"
        hint="Необязательно — придумаем сами. Латинские буквы и цифры."
        value={form.login}
        onChange={(e) => setForm({ ...form, login: e.target.value })}
      />
      <Field
        label="Пароль"
        hint="Необязательно — сгенерируем простой пароль."
        value={form.password}
        onChange={(e) => setForm({ ...form, password: e.target.value })}
      />
      <Button type="submit" loading={loading} className="w-full">
        Создать аккаунт
      </Button>
    </form>
  );
}

export function CredentialsView({ credentials, onClose }: { credentials: StudentCredentials; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const text = `Тестматика\nЛогин: ${credentials.login}\nПароль: ${credentials.password}\nВход: ${typeof window !== "undefined" ? window.location.origin : ""}/login`;
  return (
    <div className="space-y-4">
      <Alert kind="success">
        Аккаунт для <b>{credentials.student.full_name}</b> готов. Передайте ученику логин и пароль — пароль показывается
        только сейчас.
      </Alert>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 rounded-xl bg-muted p-4 font-mono text-[15px]">
        <dt className="text-fg-soft">Логин</dt>
        <dd className="select-all">{credentials.login}</dd>
        <dt className="text-fg-soft">Пароль</dt>
        <dd className="select-all">{credentials.password}</dd>
      </dl>
      <div className="flex gap-2">
        <Button
          variant="secondary"
          className="flex-1"
          onClick={async () => {
            await navigator.clipboard.writeText(text);
            setCopied(true);
          }}
        >
          {copied ? "Скопировано" : "Скопировать"}
        </Button>
        <Button className="flex-1" onClick={onClose}>
          Готово
        </Button>
      </div>
    </div>
  );
}
