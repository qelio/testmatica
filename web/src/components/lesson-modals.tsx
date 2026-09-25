"use client";

import Link from "next/link";
import { useState } from "react";

import { ExamItemsByIds, ExamItemsField } from "@/components/exams";
import { Alert, Badge, Button, Field, Modal, Select } from "@/components/ui";
import { classroom, type Lesson, type Repeat, schedule, type Scope } from "@/lib/api";
import {
  fmtDate,
  fmtDateTime,
  fmtTime,
  fromInputs,
  pluralLessons,
  timezone,
  toDateInput,
  toTimeInput,
  WEEKDAYS_SHORT,
  weekdayIndex,
} from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

const DURATIONS = [30, 45, 60, 90];

function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string }) {
  const { label, ...rest } = props;
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium">{label}</span>
      <textarea
        rows={2}
        {...rest}
        className="w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
      />
    </label>
  );
}

function ScopeChoice({ value, onChange }: { value: Scope; onChange: (s: Scope) => void }) {
  return (
    <fieldset className="space-y-1.5 rounded-xl bg-muted p-3 text-sm">
      <legend className="sr-only">Какие занятия изменить</legend>
      <label className="flex items-center gap-2">
        <input type="radio" checked={value === "this"} onChange={() => onChange("this")} className="accent-brand" />
        Только это занятие
      </label>
      <label className="flex items-center gap-2">
        <input type="radio" checked={value === "following"} onChange={() => onChange("following")} className="accent-brand" />
        Это и все следующие занятия серии
      </label>
    </fieldset>
  );
}

// ---------- создание ----------

export function CreateLessonModal({
  open,
  initial,
  onClose,
  onCreated,
}: {
  open: boolean;
  initial: Date | null;
  onClose: () => void;
  onCreated: (message: string) => void;
}) {
  return (
    <Modal open={open} onClose={onClose} title="Новое занятие">
      {open && <CreateLessonForm key={initial?.toISOString()} initial={initial ?? nextHour()} onCreated={onCreated} />}
    </Modal>
  );
}

function nextHour(): Date {
  const d = new Date();
  d.setHours(d.getHours() + 1, 0, 0, 0);
  return d;
}

function CreateLessonForm({ initial, onCreated }: { initial: Date; onCreated: (message: string) => void }) {
  // Расписание у педагога общее — показываем группы обоих режимов.
  const groups = useLoad(
    async () => [...(await classroom.groups(false, "school")), ...(await classroom.groups(false, "tutor"))],
    [],
  );
  const students = useLoad(() => classroom.students(), []);
  const [kind, setKind] = useState<"group" | "individual">("group");
  const [target, setTarget] = useState("");
  const [date, setDate] = useState(toDateInput(initial));
  const [time, setTime] = useState(toTimeInput(initial));
  const [duration, setDuration] = useState(45);
  const [subject, setSubject] = useState("");
  const [topic, setTopic] = useState("");
  const [examItems, setExamItems] = useState<string[]>([]);
  const [videoUrl, setVideoUrl] = useState("");
  const [repeat, setRepeat] = useState(false);
  // null — пользователь дни не выбирал: повторяем в день недели выбранной даты.
  const [pickedWeekdays, setWeekdays] = useState<number[] | null>(null);
  const weekdays = pickedWeekdays ?? (date ? [weekdayIndex(fromInputs(date, "00:00"))] : []);
  const [intervalWeeks, setIntervalWeeks] = useState(1);
  const [endMode, setEndMode] = useState<"count" | "until">("count");
  const [count, setCount] = useState(10);
  const [until, setUntil] = useState("");
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);

  const activeStudents = (students.data ?? []).filter((s) => s.status === "active");
  const options =
    kind === "group"
      ? (groups.data ?? []).map((g) => ({ id: g.id, label: `${g.title} · ${g.mode === "tutor" ? "репетитор" : "школа"}` }))
      : activeStudents.map((s) => ({ id: s.student_id, label: s.full_name }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!target) {
      setError(kind === "group" ? "Выберите группу" : "Выберите ученика");
      return;
    }
    setLoading(true);
    setError(undefined);
    try {
      const repeatBody: Repeat | null = repeat
        ? { weekdays, interval_weeks: intervalWeeks, count: endMode === "count" ? count : null, until: endMode === "until" ? until : null }
        : null;
      const res = await schedule.create({
        kind,
        group_id: kind === "group" ? target : null,
        student_id: kind === "individual" ? target : null,
        starts_at: fromInputs(date, time).toISOString(),
        duration_min: duration,
        subject: subject || null,
        topic: topic || null,
        exam_item_ids: examItems,
        video_url: videoUrl || null,
        repeat: repeatBody,
        timezone: timezone(),
      });
      onCreated(res.count === 1 ? "Занятие создано" : `Создано ${pluralLessons(res.count)}`);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="space-y-4" onSubmit={submit}>
      {error && <Alert>{error}</Alert>}
      <div className="flex rounded-xl bg-muted p-1 text-sm" role="radiogroup" aria-label="Тип занятия">
        {(["group", "individual"] as const).map((k) => (
          <button
            key={k}
            type="button"
            role="radio"
            aria-checked={kind === k}
            onClick={() => {
              setKind(k);
              setTarget("");
            }}
            className={`flex-1 rounded-lg py-1.5 font-medium ${kind === k ? "bg-surface shadow-sm" : "text-fg-soft"}`}
          >
            {k === "group" ? "Группа / класс" : "Индивидуальное"}
          </button>
        ))}
      </div>
      <Select label={kind === "group" ? "Группа" : "Ученик"} value={target} onChange={(e) => setTarget(e.target.value)}>
        <option value="">{options.length ? "Выберите…" : kind === "group" ? "Нет групп — создайте в «Мои классы»" : "Нет учеников"}</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </Select>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Дата" type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
        <Field label="Начало" type="time" required value={time} onChange={(e) => setTime(e.target.value)} />
      </div>
      <Select label="Продолжительность" value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
        {DURATIONS.map((d) => (
          <option key={d} value={d}>
            {d} мин
          </option>
        ))}
      </Select>
      <Field label="Предмет" placeholder="Если пусто — предмет группы" value={subject} onChange={(e) => setSubject(e.target.value)} />
      <Field label="Тема урока" value={topic} maxLength={300} onChange={(e) => setTopic(e.target.value)} />
      <ExamItemsField value={examItems} onChange={setExamItems} />
      <Field
        label="Ссылка на видеозвонок"
        placeholder="https://… (Zoom, Meet и т. д.)"
        hint="Встроенная видеосвязь появится позже"
        value={videoUrl}
        onChange={(e) => setVideoUrl(e.target.value)}
      />

      <label className="flex items-center gap-2 text-sm font-medium">
        <input type="checkbox" checked={repeat} onChange={(e) => setRepeat(e.target.checked)} className="h-4 w-4 accent-brand" />
        Повторять
      </label>
      {repeat && (
        <div className="space-y-3 rounded-xl bg-muted p-3">
          <div className="flex flex-wrap gap-1.5">
            {WEEKDAYS_SHORT.map((w, i) => (
              <button
                key={w}
                type="button"
                aria-pressed={weekdays.includes(i)}
                onClick={() => setWeekdays(weekdays.includes(i) ? weekdays.filter((x) => x !== i) : [...weekdays, i])}
                className={`h-9 w-10 rounded-lg text-sm font-medium ${weekdays.includes(i) ? "bg-brand text-white" : "bg-surface text-fg-soft"}`}
              >
                {w}
              </button>
            ))}
          </div>
          <Select label="Как часто" value={intervalWeeks} onChange={(e) => setIntervalWeeks(Number(e.target.value))}>
            <option value={1}>Каждую неделю</option>
            <option value={2}>Раз в 2 недели</option>
            <option value={3}>Раз в 3 недели</option>
            <option value={4}>Раз в 4 недели</option>
          </Select>
          <div className="grid grid-cols-2 gap-3">
            <Select label="Окончание" value={endMode} onChange={(e) => setEndMode(e.target.value as "count" | "until")}>
              <option value="count">Количество занятий</option>
              <option value="until">До даты</option>
            </Select>
            {endMode === "count" ? (
              <Field label="Занятий" type="number" min={1} max={200} value={count} onChange={(e) => setCount(Number(e.target.value))} />
            ) : (
              <Field label="До" type="date" required value={until} onChange={(e) => setUntil(e.target.value)} />
            )}
          </div>
        </div>
      )}
      <Button type="submit" loading={loading} className="w-full">
        Создать
      </Button>
    </form>
  );
}

// ---------- карточка занятия ----------

type Mode = "view" | "move" | "edit" | "cancel";

export function LessonModal({
  lesson,
  isTeacher,
  onClose,
  onChanged,
}: {
  lesson: Lesson | null;
  isTeacher: boolean;
  onClose: () => void;
  onChanged: (message?: string) => void;
}) {
  return (
    <Modal open={!!lesson} onClose={onClose} title={lesson ? lesson.title : ""}>
      {lesson && <LessonDetails key={lesson.id} lesson={lesson} isTeacher={isTeacher} onChanged={onChanged} />}
    </Modal>
  );
}

function LessonDetails({
  lesson,
  isTeacher,
  onChanged,
}: {
  lesson: Lesson;
  isTeacher: boolean;
  onChanged: (message?: string) => void;
}) {
  const [mode, setMode] = useState<Mode>("view");
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const start = new Date(lesson.starts_at);
  const cancelled = lesson.status === "cancelled";
  const past = new Date(lesson.ends_at) < new Date();
  const req = lesson.pending_reschedule;
  const canPropose = !isTeacher && lesson.kind === "individual";

  async function act(action: () => Promise<unknown>, message?: string) {
    setLoading(true);
    setError(undefined);
    try {
      await action();
      onChanged(message);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }

  if (mode === "move") {
    return (
      <MoveForm
        lesson={lesson}
        isTeacher={isTeacher}
        onBack={() => setMode("view")}
        onDone={(msg) => onChanged(msg)}
      />
    );
  }
  if (mode === "edit") return <EditForm lesson={lesson} onBack={() => setMode("view")} onDone={() => onChanged("Сохранено")} />;
  if (mode === "cancel") return <CancelForm lesson={lesson} onBack={() => setMode("view")} onDone={() => onChanged("Занятие отменено")} />;

  return (
    <div className="space-y-4">
      {error && <Alert>{error}</Alert>}
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={lesson.mode === "tutor" ? "warn" : "ok"}>{lesson.mode === "tutor" ? "репетитор" : "школа"}</Badge>
        <Badge>{lesson.kind === "group" ? "группа" : "индивидуальное"}</Badge>
        {lesson.series_id && <Badge>серия</Badge>}
        {cancelled && <Badge tone="warn">отменено</Badge>}
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        <dt className="text-fg-soft">Когда</dt>
        <dd className={cancelled ? "line-through" : ""}>
          {fmtDate(start, { weekday: "long", day: "numeric", month: "long" })}, {fmtTime(start)}–{fmtTime(lesson.ends_at)}
        </dd>
        {!isTeacher && (
          <>
            <dt className="text-fg-soft">Педагог</dt>
            <dd>{lesson.teacher.full_name}</dd>
          </>
        )}
        {lesson.subject && (
          <>
            <dt className="text-fg-soft">Предмет</dt>
            <dd>{lesson.subject}</dd>
          </>
        )}
        {lesson.topic && (
          <>
            <dt className="text-fg-soft">Тема</dt>
            <dd>{lesson.topic}</dd>
          </>
        )}
        {lesson.exam_item_ids.length > 0 && (
          <>
            <dt className="text-fg-soft">ЕГЭ / ОГЭ</dt>
            <dd>
              <ExamItemsByIds ids={lesson.exam_item_ids} />
            </dd>
          </>
        )}
        {cancelled && lesson.cancel_reason && (
          <>
            <dt className="text-fg-soft">Причина</dt>
            <dd>{lesson.cancel_reason}</dd>
          </>
        )}
        {isTeacher && lesson.participants && lesson.kind === "group" && (
          <>
            <dt className="text-fg-soft">Ученики</dt>
            <dd>{lesson.participants.length ? lesson.participants.map((p) => p.full_name).join(", ") : "—"}</dd>
          </>
        )}
      </dl>

      {req && !cancelled && (
        <div className="space-y-2 rounded-xl border border-tutor/40 bg-tutor/10 p-3 text-sm">
          <p>
            {req.requested_by_me ? "Вы предложили перенести на " : "Предлагают перенести на "}
            <b>{fmtDateTime(req.new_starts_at)}</b>
          </p>
          {req.comment && <p className="text-fg-soft">«{req.comment}»</p>}
          {req.requested_by_me ? (
            <Button variant="secondary" className="h-9" loading={loading} onClick={() => act(() => schedule.withdrawRequest(req.id), "Запрос отозван")}>
              Отозвать запрос
            </Button>
          ) : (
            <div className="flex gap-2">
              <Button className="h-9" loading={loading} onClick={() => act(() => schedule.acceptRequest(req.id), "Занятие перенесено")}>
                Согласиться
              </Button>
              <Button variant="secondary" className="h-9" loading={loading} onClick={() => act(() => schedule.declineRequest(req.id), "Перенос отклонён")}>
                Отказаться
              </Button>
            </div>
          )}
          {!req.requested_by_me && isTeacher === false && (
            <p className="text-xs text-fg-soft">Если отказаться от переноса, предложенного педагогом, занятие будет отменено.</p>
          )}
        </div>
      )}

      {!cancelled && lesson.video_url && (
        <a
          href={lesson.video_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex h-11 items-center justify-center rounded-xl bg-brand font-medium text-white hover:bg-brand-strong"
        >
          Войти в звонок
        </a>
      )}

      {!cancelled && !past && (
        <div className="flex flex-wrap gap-2 border-t border-line pt-4">
          {(isTeacher || canPropose) && !req && (
            <Button variant="secondary" onClick={() => setMode("move")}>
              {isTeacher ? "Перенести" : "Предложить перенос"}
            </Button>
          )}
          {isTeacher && (
            <>
              <Button variant="secondary" onClick={() => setMode("edit")}>
                Изменить
              </Button>
              <Button variant="ghost" className="text-danger" onClick={() => setMode("cancel")}>
                Отменить занятие
              </Button>
            </>
          )}
        </div>
      )}
      {isTeacher && !cancelled && new Date(lesson.starts_at) <= new Date() && (
        <Link
          href={`/dashboard/journal?${lesson.kind === "group" ? `group=${lesson.group_id}` : `student=${lesson.participants?.[0]?.id ?? ""}`}`}
          className="flex h-11 items-center justify-center rounded-xl border border-line font-medium hover:bg-muted"
        >
          Открыть журнал
        </Link>
      )}
      {isTeacher && !cancelled && (
        <p className="text-xs text-fg-soft">Домашние задания и встроенный видеозвонок появятся на следующих этапах.</p>
      )}
    </div>
  );
}

function MoveForm({
  lesson,
  isTeacher,
  onBack,
  onDone,
}: {
  lesson: Lesson;
  isTeacher: boolean;
  onBack: () => void;
  onDone: (message: string) => void;
}) {
  const start = new Date(lesson.starts_at);
  const [date, setDate] = useState(toDateInput(start));
  const [time, setTime] = useState(toTimeInput(start));
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const needsConfirmation = lesson.kind === "individual";

  return (
    <form
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setLoading(true);
        setError(undefined);
        try {
          await schedule.reschedule(lesson.id, fromInputs(date, time).toISOString(), comment || null);
          onDone(needsConfirmation ? "Запрос на перенос отправлен" : "Занятие перенесено");
        } catch (err) {
          setError(errorText(err));
        } finally {
          setLoading(false);
        }
      }}
    >
      {error && <Alert>{error}</Alert>}
      <p className="text-sm text-fg-soft">
        {needsConfirmation
          ? isTeacher
            ? "Ученик получит уведомление и должен подтвердить новое время."
            : "Педагог получит уведомление и должен подтвердить новое время."
          : "Занятие будет перенесено сразу, ученики получат уведомление."}
      </p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Новая дата" type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
        <Field label="Начало" type="time" required value={time} onChange={(e) => setTime(e.target.value)} />
      </div>
      {needsConfirmation && <Textarea label="Комментарий" value={comment} maxLength={500} onChange={(e) => setComment(e.target.value)} />}
      <div className="flex gap-2">
        <Button type="button" variant="secondary" onClick={onBack}>
          Назад
        </Button>
        <Button type="submit" loading={loading} className="flex-1">
          {needsConfirmation ? "Предложить перенос" : "Перенести"}
        </Button>
      </div>
    </form>
  );
}

function EditForm({ lesson, onBack, onDone }: { lesson: Lesson; onBack: () => void; onDone: () => void }) {
  const [scope, setScope] = useState<Scope>("this");
  const [duration, setDuration] = useState(lesson.duration_min);
  const [subject, setSubject] = useState(lesson.subject ?? "");
  const [topic, setTopic] = useState(lesson.topic ?? "");
  const [examItems, setExamItems] = useState(lesson.exam_item_ids);
  const [videoUrl, setVideoUrl] = useState(lesson.video_url ?? "");
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const durations = DURATIONS.includes(lesson.duration_min) ? DURATIONS : [...DURATIONS, lesson.duration_min].sort((a, b) => a - b);

  return (
    <form
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setLoading(true);
        setError(undefined);
        try {
          await schedule.update(lesson.id, {
            scope,
            duration_min: duration,
            subject: subject || null,
            topic: topic || null,
            exam_item_ids: examItems,
            video_url: videoUrl || null,
          });
          onDone();
        } catch (err) {
          setError(errorText(err));
        } finally {
          setLoading(false);
        }
      }}
    >
      {error && <Alert>{error}</Alert>}
      {lesson.series_id && <ScopeChoice value={scope} onChange={setScope} />}
      <Select label="Продолжительность" value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
        {durations.map((d) => (
          <option key={d} value={d}>
            {d} мин
          </option>
        ))}
      </Select>
      <Field label="Предмет" value={subject} onChange={(e) => setSubject(e.target.value)} />
      <Field label="Тема урока" value={topic} onChange={(e) => setTopic(e.target.value)} />
      <ExamItemsField value={examItems} onChange={setExamItems} />
      <Field label="Ссылка на видеозвонок" placeholder="https://…" value={videoUrl} onChange={(e) => setVideoUrl(e.target.value)} />
      <div className="flex gap-2">
        <Button type="button" variant="secondary" onClick={onBack}>
          Назад
        </Button>
        <Button type="submit" loading={loading} className="flex-1">
          Сохранить
        </Button>
      </div>
    </form>
  );
}

function CancelForm({ lesson, onBack, onDone }: { lesson: Lesson; onBack: () => void; onDone: () => void }) {
  const [scope, setScope] = useState<Scope>("this");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  return (
    <form
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setLoading(true);
        setError(undefined);
        try {
          await schedule.cancel(lesson.id, scope, reason || null);
          onDone();
        } catch (err) {
          setError(errorText(err));
        } finally {
          setLoading(false);
        }
      }}
    >
      {error && <Alert>{error}</Alert>}
      {lesson.series_id && <ScopeChoice value={scope} onChange={setScope} />}
      <Textarea label="Причина (увидят ученики)" value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
      <div className="flex gap-2">
        <Button type="button" variant="secondary" onClick={onBack}>
          Назад
        </Button>
        <Button type="submit" loading={loading} className="flex-1 bg-danger hover:bg-danger/90">
          Отменить занятие
        </Button>
      </div>
    </form>
  );
}
