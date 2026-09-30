"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { FinishButton } from "@/components/finish-attempt";
import { Markdown } from "@/components/markdown";
import { Alert, Badge, Button, Field, Modal, Spinner } from "@/components/ui";
import { type Assignment, assessment } from "@/lib/api";
import { attemptsText, bestAttempt, fmtLimit, KIND_LABELS, lastAttempt, studentStatus, summary } from "@/lib/assignments";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, fromInputs } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";
import { useRealtime } from "@/lib/realtime";

export default function AssignmentPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const a = useLoad(() => assessment.assignment(id), [id]);
  const isTeacher = !!a.data && a.data.teacher_id === user?.id;

  // Начал, сдал, завершил педагог — сразу, через WebSocket.
  useRealtime((e) => {
    if ((e.type === "assignment" && e.assignment_id === id) || e.type === "reconnected") a.reload();
  });
  // Запасной вариант, если WebSocket оборвался: тест на уроке и работы «в процессе» — раз в несколько секунд.
  const active = !!a.data && isTeacher && !a.data.closed && (a.data.kind === "live" || summary(a.data).inProgress > 0);
  useEffect(() => {
    if (!active) return;
    const t = setInterval(a.reload, 5000);
    return () => clearInterval(t);
  }, [active, a.reload]);

  if (a.error) return <Alert>{a.error}</Alert>;
  if (!a.data) return <Spinner />;
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <Link href="/dashboard/assignments" className="text-sm text-fg-soft hover:text-fg">
        ← {isTeacher ? "Назначение тестов" : "Назначенные тесты"}
      </Link>
      <Header a={a.data} isTeacher={isTeacher} />
      {isTeacher ? <TeacherPanel a={a.data} reload={a.reload} /> : <StudentPanel a={a.data} />}
    </div>
  );
}

function Header({ a, isTeacher }: { a: Assignment; isTeacher: boolean }) {
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={a.kind === "live" ? "brand" : "neutral"}>{KIND_LABELS[a.kind]}</Badge>
        {a.not_open_yet && a.opens_at && <Badge>откроется {fmtDateTime(a.opens_at)}</Badge>}
        {a.kind === "live" && !a.closed && !a.not_open_yet && <Badge tone="brand">идёт сейчас</Badge>}
        {a.closed && <Badge>завершён</Badge>}
        {a.overdue && !a.closed && <Badge tone="warn">срок прошёл</Badge>}
      </div>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">{a.title}</h1>
      {isTeacher && (
        <p className="mt-1 text-sm">
          Тест:{" "}
          <Link href={`/dashboard/tests/${a.test_id}`} className="text-brand hover:underline">
            {a.test_title}
          </Link>
        </p>
      )}
      <p className="mt-1 text-sm text-fg-soft">
        {[
          a.target_title,
          a.teacher_name,
          a.opens_at && !a.not_open_yet ? `открыт с ${fmtDateTime(a.opens_at)}` : null,
          a.deadline ? `сдать до ${fmtDateTime(a.deadline)}` : null,
          attemptsText(a),
          `заданий: ${a.tasks_count}`,
          `баллов: ${a.max_score}`,
          fmtLimit(a.settings),
          a.grade_to_journal ? "оценка в журнал" : null,
          a.proctoring ? "с прокторингом" : null,
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
    </div>
  );
}

function TeacherPanel({ a, reload }: { a: Assignment; reload: () => void }) {
  const [error, setError] = useState<string>();
  const [closing, setClosing] = useState(false);
  const s = summary(a);
  return (
    <div className="space-y-4">
      {error && <Alert>{error}</Alert>}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-2xl border border-line bg-surface px-5 py-3 text-sm">
        <span>
          Сдали: <b>{s.submitted}</b> из {s.total}
        </span>
        {s.inProgress > 0 && <span className="text-brand">решают сейчас: {s.inProgress}</span>}
        {s.toReview > 0 && <span className="text-tutor">ждут вашей проверки: {s.toReview}</span>}
        {s.avg !== null && <span>средний результат: {s.avg}%</span>}
        {a.proctoring && (
          <Link
            href={`/dashboard/assignments/${a.id}/proctoring`}
            className="rounded-xl bg-brand px-3 py-1.5 font-medium text-white hover:bg-brand-strong"
          >
            Наблюдение{s.inProgress ? ` · решают ${s.inProgress}` : ""}
          </Link>
        )}
        {a.kind === "live" && !a.closed && (
          <Button
            variant="secondary"
            className="ml-auto h-9"
            loading={closing}
            onClick={async () => {
              if (!window.confirm("Завершить тест? Незавершённые работы сдадутся с тем, что ученики успели ответить.")) return;
              setClosing(true);
              try {
                await assessment.closeAssignment(a.id);
                reload();
              } catch (e) {
                setError(errorText(e));
              } finally {
                setClosing(false);
              }
            }}
          >
            Завершить тест
          </Button>
        )}
      </div>
      <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
        {a.students.map((row) => (
          <StudentRow key={row.student_id} a={a} row={row} onChanged={reload} onError={setError} />
        ))}
      </ul>
    </div>
  );
}

function StudentRow({
  a,
  row,
  onChanged,
  onError,
}: {
  a: Assignment;
  row: Assignment["students"][number];
  onChanged: () => void;
  onError: (e: string) => void;
}) {
  const st = studentStatus(a, row);
  const last = lastAttempt(row);
  const best = bestAttempt(row);
  const [reassigning, setReassigning] = useState(false);
  const [date, setDate] = useState("");
  const [time, setTime] = useState("20:00");
  // Без лимита попыток переназначать нечего — разве что продлить срок.
  const canReassign =
    last?.status !== "in_progress" && (!!last || a.overdue || a.closed) && (a.max_attempts === null ? a.overdue || a.closed : row.attempts.length >= row.allowed_attempts);

  return (
    <li className="px-5 py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Link href={`/dashboard/students/${row.student_id}`} className="min-w-0 flex-1 font-medium hover:underline">
          {row.full_name}
        </Link>
        {last?.status === "in_progress" && (
          <span className="h-2 w-28 overflow-hidden rounded-full bg-muted" aria-hidden>
            <span className="block h-full bg-brand" style={{ width: `${(last.answered / Math.max(1, last.total)) * 100}%` }} />
          </span>
        )}
        {best?.score != null && (
          <span className="text-sm text-fg-soft tabular-nums">
            {best.score} из {best.max_score}
            {row.attempts.length > 1 && " (лучшая)"}
          </span>
        )}
        <Badge tone={st.tone}>{st.text}</Badge>
        {a.proctoring && row.proctor_alerts > 0 && <Badge tone="warn">нарушений прокторинга: {row.proctor_alerts}</Badge>}
        {row.attempts.map((t) => (
          <Link key={t.id} href={`/dashboard/attempts/${t.id}`} className="text-sm text-brand hover:underline">
            {row.attempts.length > 1 ? `попытка ${t.number}` : "открыть"}
          </Link>
        ))}
        {last?.finished_by_teacher && <span className="text-xs text-fg-soft">завершили вы</span>}
        {last?.status === "in_progress" && (
          <FinishButton attemptId={last.id} name={row.full_name} onDone={onChanged} onError={onError} />
        )}
        {canReassign && !reassigning && (
          <button className="text-sm text-fg-soft hover:text-fg" onClick={() => setReassigning(true)}>
            Переназначить
          </button>
        )}
      </div>
      {reassigning && (
        <form
          className="mt-2 flex flex-wrap items-end gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await assessment.reassign(a.id, row.student_id, date ? fromInputs(date, time).toISOString() : null);
              setReassigning(false);
              onChanged();
            } catch (err) {
              onError(errorText(err));
            }
          }}
        >
          <p className="w-full text-sm text-fg-soft">
            {a.max_attempts === null ? "Ученик снова сможет проходить тест;" : "Ученик сможет пройти ещё раз;"} прошлые попытки сохранятся.
            {a.deadline && " Если общий срок прошёл — задайте новый."}
          </p>
          <Field label="Новый срок" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          <Field label="Время" type="time" value={time} disabled={!date} onChange={(e) => setTime(e.target.value)} />
          <Button type="submit" className="h-11">
            Переназначить
          </Button>
          <Button type="button" variant="ghost" className="h-11" onClick={() => setReassigning(false)}>
            Отмена
          </Button>
        </form>
      )}
    </li>
  );
}

function StudentPanel({ a }: { a: Assignment }) {
  const router = useRouter();
  const row = a.students[0];
  const last = lastAttempt(row);
  const st = studentStatus(a, row);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [consenting, setConsenting] = useState(false);
  const limit = fmtLimit(a.settings);

  async function go(consent = false) {
    if (a.proctoring && !consent) {
      setConsenting(true);
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      const attempt = await assessment.start(a.id, consent);
      router.push(`/dashboard/attempts/${attempt.id}`);
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {error && <Alert>{error}</Alert>}
      {a.description && (
        <div className="rounded-2xl border border-line bg-surface p-5">
          <Markdown text={a.description} />
        </div>
      )}
      <div className="space-y-3 rounded-2xl border border-line bg-surface p-5">
        <p>
          Статус: <Badge tone={st.tone}>{st.text}</Badge>
        </p>
        <ul className="list-inside list-disc text-sm text-fg-soft">
          {limit && (
            <li>
              Ограничение времени: {limit}.{" "}
              {a.settings.time_mode === "per_task" ? "Задания открываются по одному, вернуться к пройденному нельзя." : "Таймер запустится, когда вы начнёте."}
            </li>
          )}
          <li>Ответы сохраняются сами; проверка — после того как вы сдадите работу.</li>
          {a.proctoring && <li>Тест с прокторингом: педагог видит ваш экран, пока вы решаете.</li>}
          {a.not_open_yet && a.opens_at && <li>Тест откроется {fmtDateTime(a.opens_at)}.</li>}
          <li>
            {a.max_attempts === 1
              ? "Сдать можно один раз."
              : `${a.max_attempts === null ? "Проходить можно сколько угодно раз" : `Можно пройти до ${a.max_attempts} раз`} — засчитывается лучшая попытка.`}
            {a.attempts_left !== null && a.max_attempts !== 1 && row?.attempts.length ? ` Осталось попыток: ${a.attempts_left}.` : ""}
            {a.deadline && " Когда срок выйдет, незавершённая работа сдастся автоматически с тем, что вы успели ответить."}
          </li>
        </ul>
        {last?.status === "in_progress" ? (
          <Button onClick={() => router.push(`/dashboard/attempts/${last.id}`)}>Продолжить</Button>
        ) : (
          a.can_start && (
            <Button onClick={() => go()} loading={busy}>
              {row?.attempts.length ? "Пройти ещё раз" : "Начать"}
            </Button>
          )
        )}
      </div>
      <Modal open={consenting} onClose={() => setConsenting(false)} title="Тест с прокторингом">
        <div className="space-y-3 text-sm">
          <p>Во время теста педагог наблюдает за прохождением:</p>
          <ul className="list-inside list-disc space-y-1 text-fg-soft">
            <li>вы показываете <b className="text-fg">весь экран</b> — без этого тест закрыт;</li>
            <li>педагог сразу видит, если вы переключились на другую вкладку, окно или свернули браузер;</li>
            <li>педагог может включить вашу камеру — на это время появится отметка «камера включена»;</li>
            <li>экран записывается, запись хранится 2 недели и доступна только педагогу.</li>
          </ul>
          <p className="text-fg-soft">Анализ лица и автоматические решения не применяются. Чат с педагогом работает как обычно.</p>
          <div className="flex flex-wrap gap-2 pt-1">
            <Button
              loading={busy}
              onClick={() => {
                setConsenting(false);
                void go(true);
              }}
            >
              Согласен, начать тест
            </Button>
            <Button variant="secondary" onClick={() => setConsenting(false)}>
              Отмена
            </Button>
          </div>
        </div>
      </Modal>
      {row && row.attempts.some((t) => t.status === "submitted") && (
        <div className="rounded-2xl border border-line bg-surface">
          <h2 className="border-b border-line px-5 py-3 font-medium">Мои попытки</h2>
          <ul className="divide-y divide-line">
            {row.attempts
              .filter((t) => t.status === "submitted")
              .map((t) => (
                <li key={t.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                  <span className="font-medium">Попытка {t.number}</span>
                  <span className="text-fg-soft">сдана {fmtDateTime(t.submitted_at!)}</span>
                  {t.checked ? (
                    <Badge tone={(t.grade ?? 0) >= 4 ? "ok" : "warn"}>
                      {t.score} из {t.max_score} · оценка {t.grade}
                    </Badge>
                  ) : (
                    <Badge>проверяется</Badge>
                  )}
                  <Link href={`/dashboard/attempts/${t.id}`} className="ml-auto text-brand hover:underline">
                    Посмотреть
                  </Link>
                </li>
              ))}
          </ul>
        </div>
      )}
    </div>
  );
}
