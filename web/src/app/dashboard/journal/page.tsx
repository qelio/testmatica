"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Alert, Badge, Button, EmptyState, Modal, Select, Spinner } from "@/components/ui";
import { academic, type AttendanceStatus, classroom, type Grade, type Journal } from "@/lib/api";
import { fmtDate, fmtDay, fmtTime, unzoned, WEEKDAYS_SHORT, zoned } from "@/lib/dates";
import { ATTENDANCE_LABELS, fmtAverage, fmtRate, gradeTone } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

export default function JournalPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <JournalScreen />
    </Suspense>
  );
}

function JournalScreen() {
  const params = useSearchParams();
  const router = useRouter();
  const groupId = params.get("group") ?? undefined;
  const studentId = params.get("student") ?? undefined;
  const [month, setMonth] = useState(() => {
    const d = zoned(new Date());
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });
  const [cell, setCell] = useState<{ lessonId: string; studentId: string } | null>(null);
  // Журнал предмета (решение №59): undefined — первый (предмет класса), null — «Без предмета».
  const [subject, setSubject] = useState<string | null | undefined>(undefined);
  const [error, setError] = useState<string>();

  const targets = useLoad(async () => {
    const [groups, students] = await Promise.all([classroom.groups(), classroom.students()]);
    return {
      groups,
      students: students.filter((s) => s.status === "active"),
    };
  }, []);

  // Месяц — «настенный» по часам пользователя; на сервер — моменты времени.
  const from = unzoned(month);
  const to = unzoned(new Date(month.getFullYear(), month.getMonth() + 1, 1));
  const hasTarget = !!(groupId || studentId);
  const journal = useLoad(
    () =>
      hasTarget
        ? academic.journal({ group_id: groupId, student_id: studentId }, from, to, subject)
        : Promise.resolve(null),
    [groupId, studentId, from.toISOString(), subject],
  );

  function choose(value: string) {
    const [kind, id] = value.split(":");
    setSubject(undefined);
    router.replace(id ? `/dashboard/journal?${kind}=${id}` : "/dashboard/journal");
  }

  const monthTitle = fmtDay(month, { month: "long", year: "numeric" });

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Журнал</h1>

      <div className="flex flex-wrap items-end gap-3">
        <div className="w-full max-w-xs">
          <Select
            label="Класс, группа или ученик"
            value={groupId ? `group:${groupId}` : studentId ? `student:${studentId}` : ""}
            onChange={(e) => choose(e.target.value)}
          >
            <option value="">Выберите…</option>
            {targets.data && targets.data.groups.length > 0 && (
              <optgroup label="Классы и группы">
                {targets.data.groups.map((g) => (
                  <option key={g.id} value={`group:${g.id}`}>
                    {g.title}
                  </option>
                ))}
              </optgroup>
            )}
            {targets.data && targets.data.students.length > 0 && (
              <optgroup label="Индивидуальные занятия">
                {targets.data.students.map((s) => (
                  <option key={s.student_id} value={`student:${s.student_id}`}>
                    {s.full_name}
                  </option>
                ))}
              </optgroup>
            )}
          </Select>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" className="h-11 px-3" aria-label="Предыдущий месяц" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}>
            ←
          </Button>
          <span className="min-w-36 text-center font-medium">{monthTitle.charAt(0).toUpperCase() + monthTitle.slice(1)}</span>
          <Button variant="ghost" className="h-11 px-3" aria-label="Следующий месяц" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}>
            →
          </Button>
        </div>
      </div>

      {journal.data && (
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Журналы по предметам">
          {journal.data.subjects.map((x) => {
            const active = x === journal.data!.subject;
            return (
              <button
                key={x ?? ""}
                role="tab"
                aria-selected={active}
                onClick={() => setSubject(x)}
                className={`h-9 rounded-full border px-4 text-sm font-medium ${active ? "border-brand bg-brand text-on-brand" : "border-line hover:bg-muted"}`}
              >
                {x ?? "Без предмета"}
              </button>
            );
          })}
        </div>
      )}

      {(journal.error || error) && <Alert>{journal.error ?? error}</Alert>}
      {!hasTarget ? (
        <EmptyState title="Выберите класс, группу или ученика" text="Столбцы журнала — проведённые занятия из расписания." />
      ) : !journal.data ? (
        !journal.error && <Spinner />
      ) : (
        <JournalTable
          journal={journal.data}
          onCell={(lessonId, sid) => setCell({ lessonId, studentId: sid })}
          onAllPresent={async (lessonId) => {
            setError(undefined);
            try {
              await academic.allPresent(lessonId);
              journal.reload();
            } catch (e) {
              setError(errorText(e));
            }
          }}
        />
      )}

      {journal.data && (
        <CellModal
          journal={journal.data}
          cell={cell}
          onClose={() => setCell(null)}
          onChanged={() => journal.reload()}
        />
      )}
    </div>
  );
}

function JournalTable({
  journal,
  onCell,
  onAllPresent,
}: {
  journal: Journal;
  onCell: (lessonId: string, studentId: string) => void;
  onAllPresent: (lessonId: string) => void;
}) {
  if (journal.lessons.length === 0 && journal.works.length === 0) {
    return <EmptyState title="В этом месяце занятий нет" text="Запланируйте занятия в расписании — они появятся здесь столбцами." />;
  }
  if (journal.students.length === 0) {
    return <EmptyState title="В группе нет учеников" />;
  }
  const grades = new Map<string, Grade[]>();
  for (const g of journal.grades) {
    const key = `${g.lesson_id ?? g.work_id}:${g.student_id}`;
    grades.set(key, [...(grades.get(key) ?? []), g]);
  }
  const marks = new Map(journal.attendance.map((a) => [`${a.lesson_id}:${a.student_id}`, a.status]));

  return (
    <div className="overflow-x-auto rounded-2xl border border-line bg-surface">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-line">
            <th className="sticky left-0 z-10 min-w-44 bg-surface px-3 py-2 text-left font-medium">{journal.title}</th>
            {journal.lessons.map((l) => {
              const d = zoned(l.starts_at);
              return (
                <th
                  key={l.id}
                  title={l.own ? undefined : `Занятие коллеги: ${l.teacher_name}`}
                  className={`min-w-14 border-l border-line px-1 py-1.5 text-center font-normal ${l.started ? "" : "text-fg-soft/50"} ${l.own ? "" : "bg-muted/60"}`}
                >
                  <span className="block text-[11px] text-fg-soft">{WEEKDAYS_SHORT[(d.getDay() + 6) % 7]}</span>
                  <span className="block font-medium">{fmtDate(l.starts_at, { day: "2-digit", month: "2-digit" })}</span>
                  {!l.own && <span className="block max-w-16 truncate text-[11px] text-fg-soft">{l.teacher_name?.split(" ")[0]}</span>}
                  {l.started && l.own && (
                    <button
                      onClick={() => onAllPresent(l.id)}
                      title="Отметить всех присутствующими"
                      className="mt-0.5 rounded px-1 text-[11px] text-brand-text hover:bg-brand/10"
                    >
                      все ✓
                    </button>
                  )}
                </th>
              );
            })}
            {journal.works.map((w) => (
              <th
                key={w.id}
                className="max-w-28 min-w-20 border-l border-line bg-brand/5 px-1.5 py-1.5 text-center font-normal"
                title={w.own ? w.title : `${w.title} — работа коллеги: ${w.teacher_name}`}
              >
                <span className="block text-[11px] text-fg-soft">{fmtDate(w.at, { day: "2-digit", month: "2-digit" })}</span>
                {w.own ? (
                  <Link href={`/dashboard/assignments/${w.id}`} className="line-clamp-2 text-xs font-medium hover:text-brand-text">
                    {w.title}
                  </Link>
                ) : (
                  <>
                    <span className="line-clamp-2 text-xs font-medium">{w.title}</span>
                    <span className="block truncate text-[11px] text-fg-soft">{w.teacher_name?.split(" ")[0]}</span>
                  </>
                )}
              </th>
            ))}
            <th className="border-l border-line px-2 py-2 text-center font-medium">Ср. балл</th>
            <th className="px-2 py-2 text-center font-medium">Посещ.</th>
          </tr>
        </thead>
        <tbody>
          {journal.students.map((s) => (
            <tr key={s.id} className="border-b border-line/70 last:border-0">
              <td className="sticky left-0 z-10 bg-surface px-3 py-1.5">
                <span className={s.current ? "" : "text-fg-soft"}>{s.full_name}</span>
                {!s.current && <span className="ml-1 text-[11px] text-fg-soft">(выбыл)</span>}
              </td>
              {journal.lessons.map((l) => {
                const key = `${l.id}:${s.id}`;
                const cellGrades = grades.get(key) ?? [];
                const mark = marks.get(key);
                return (
                  <td key={l.id} className="border-l border-line/70 p-0 text-center">
                    <button
                      disabled={!l.started}
                      onClick={() => onCell(l.id, s.id)}
                      aria-label={`${s.full_name}, ${fmtDate(l.starts_at)}`}
                      className="flex h-11 w-full items-center justify-center gap-1 enabled:hover:bg-muted disabled:cursor-not-allowed disabled:bg-muted/30"
                    >
                      {mark && mark !== "present" && (
                        <span className={`text-xs font-semibold ${mark === "sick" ? "text-fg-soft" : "text-danger"}`}>
                          {ATTENDANCE_LABELS[mark].short}
                        </span>
                      )}
                      {mark === "present" && cellGrades.length === 0 && <span className="text-xs text-fg-soft">·</span>}
                      {cellGrades.map((g) => (
                        <span key={g.id} className={`font-semibold ${gradeTone(g.value)}`}>
                          {g.value}
                        </span>
                      ))}
                    </button>
                  </td>
                );
              })}
              {journal.works.map((w) => {
                const cellGrades = grades.get(`${w.id}:${s.id}`) ?? [];
                const values = cellGrades.map((g) => (
                  <span key={g.id} className={`font-semibold ${gradeTone(g.value)}`}>
                    {g.value}
                  </span>
                ));
                const hint = cellGrades.map((g) => `${g.grade_type}. ${g.comment}`).join("\n") || "Оценки пока нет";
                return (
                  <td key={w.id} className="border-l border-line/70 bg-brand/5 p-0 text-center">
                    {w.own ? (
                      <Link href={`/dashboard/assignments/${w.id}`} title={hint} className="flex h-11 w-full items-center justify-center gap-1 hover:bg-muted">
                        {values}
                      </Link>
                    ) : (
                      <span title={`${hint}\nПоставил(а): ${w.teacher_name}`} className="flex h-11 w-full items-center justify-center gap-1">
                        {values}
                      </span>
                    )}
                  </td>
                );
              })}
              <td className="border-l border-line px-2 text-center font-semibold">{fmtAverage(s.stats.average)}</td>
              <td className="px-2 text-center text-fg-soft">{fmtRate(s.stats.attendance_rate)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-line bg-muted/50">
            <td className="sticky left-0 z-10 bg-muted px-3 py-2 font-medium">Итого по {journal.students.length > 1 ? "группе" : "ученику"}</td>
            <td colSpan={journal.lessons.length + journal.works.length} className="border-l border-line px-3 text-xs text-fg-soft">
              Н — отсутствовал, О — опоздал, Б — болел, · — присутствовал
              {journal.works.length > 0 && " · выделенные колонки — оценки за тесты и ДЗ; изменить — на странице работы"}
              {journal.lessons.some((l) => !l.own) && " · серые колонки — занятия коллег: их оценки видны, но менять их нельзя"}
            </td>
            <td className="border-l border-line px-2 text-center font-semibold">{fmtAverage(journal.stats.average)}</td>
            <td className="px-2 text-center text-fg-soft">{fmtRate(journal.stats.attendance_rate)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function CellModal({
  journal,
  cell,
  onClose,
  onChanged,
}: {
  journal: Journal;
  cell: { lessonId: string; studentId: string } | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const lesson = cell && journal.lessons.find((l) => l.id === cell.lessonId);
  const student = cell && journal.students.find((s) => s.id === cell.studentId);
  const title = student ? student.full_name : "";
  return (
    <Modal open={!!(lesson && student)} onClose={onClose} title={title}>
      {lesson && student && (
        <CellEditor
          key={`${lesson.id}:${student.id}`}
          journal={journal}
          lessonId={lesson.id}
          studentId={student.id}
          onChanged={onChanged}
        />
      )}
    </Modal>
  );
}

function CellEditor({
  journal,
  lessonId,
  studentId,
  onChanged,
}: {
  journal: Journal;
  lessonId: string;
  studentId: string;
  onChanged: () => void;
}) {
  const types = useLoad(() => academic.gradeTypes(), []);
  const lesson = journal.lessons.find((l) => l.id === lessonId)!;
  const mark = journal.attendance.find((a) => a.lesson_id === lessonId && a.student_id === studentId)?.status;
  const grades = journal.grades.filter((g) => g.lesson_id === lessonId && g.student_id === studentId);
  const [value, setValue] = useState<number | null>(null);
  const [typeId, setTypeId] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(undefined);
    try {
      await action();
      onChanged();
      return true;
    } catch (e) {
      setError(errorText(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  const effectiveType = typeId || types.data?.[0]?.id || "";

  return (
    <div className="space-y-5">
      <p className="text-sm text-fg-soft">
        {fmtDate(lesson.starts_at, { weekday: "long", day: "numeric", month: "long" })}, {fmtTime(lesson.starts_at)}
        {lesson.subject && ` · ${lesson.subject}`}
        {lesson.topic && ` · ${lesson.topic}`}
      </p>
      {lesson.ktp.length > 0 && <p className="text-sm">По КТП: {lesson.ktp.join("; ")}</p>}
      {error && <Alert>{error}</Alert>}

      {!lesson.own ? (
        <>
          <p className="rounded-xl bg-muted px-3 py-2 text-sm">
            Занятие коллеги — {lesson.teacher_name}. Оценки и посещаемость на нём ставит коллега
            {grades.some((g) => g.can_edit) ? "; править и удалять его оценки вам разрешено." : ", вы их только видите."}
          </p>
          {mark && <p className="text-sm">Посещаемость: {ATTENDANCE_LABELS[mark].full}</p>}
          <section className="space-y-2">
            <h3 className="text-sm font-medium">Оценки</h3>
            {grades.length === 0 && <p className="text-sm text-fg-soft">Оценок за это занятие нет.</p>}
            {grades.map((g) => (
              <div key={g.id} className="flex items-start gap-3 rounded-xl bg-muted px-3 py-2">
                <span className={`text-xl font-bold ${gradeTone(g.value)}`}>{g.value}</span>
                <div className="min-w-0 flex-1 text-sm">
                  <p className="font-medium">{g.grade_type}</p>
                  <p className="text-fg-soft">{g.comment}</p>
                </div>
                {/* Право «правка всех оценок» или владелец класса (решение №61). */}
                {g.can_edit && (
                  <button disabled={busy} onClick={() => act(() => academic.deleteGrade(g.id))} className="text-sm text-danger hover:underline">
                    Удалить
                  </button>
                )}
              </div>
            ))}
          </section>
        </>
      ) : (
        <>
        <section>
          <h3 className="mb-2 text-sm font-medium">Посещаемость</h3>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {(Object.keys(ATTENDANCE_LABELS) as AttendanceStatus[]).map((status) => (
              <button
                key={status}
                disabled={busy}
                aria-pressed={mark === status}
                onClick={() => act(() => academic.setAttendance(lessonId, studentId, mark === status ? null : status))}
                className={`h-10 rounded-xl border text-sm font-medium ${mark === status ? "border-brand bg-brand text-on-brand" : "border-line hover:bg-muted"}`}
              >
                {ATTENDANCE_LABELS[status].full}
              </button>
            ))}
          </div>
        </section>

        <section className="space-y-2">
          <h3 className="text-sm font-medium">Оценки</h3>
          {grades.length === 0 && <p className="text-sm text-fg-soft">Оценок за это занятие нет.</p>}
          {grades.map((g) => (
            <div key={g.id} className="flex items-start gap-3 rounded-xl bg-muted px-3 py-2">
              <span className={`text-xl font-bold ${gradeTone(g.value)}`}>{g.value}</span>
              <div className="min-w-0 flex-1 text-sm">
                <p className="font-medium">
                  {g.grade_type}
                  {g.source === "test" && <Badge tone="brand">из теста</Badge>}
                </p>
                <p className="text-fg-soft">{g.comment}</p>
              </div>
              <button
                disabled={busy}
                onClick={() => act(() => academic.deleteGrade(g.id))}
                className="text-sm text-danger hover:underline"
              >
                Удалить
              </button>
            </div>
          ))}
        </section>

        <form
          className="space-y-3 border-t border-line pt-4"
          onSubmit={async (e) => {
            e.preventDefault();
            if (value === null) {
              setError("Выберите оценку");
              return;
            }
            const ok = await act(() =>
              academic.addGrade(lessonId, { student_id: studentId, value, grade_type_id: effectiveType, comment }),
            );
            if (ok) {
              setValue(null);
              setComment("");
            }
          }}
        >
          <h3 className="text-sm font-medium">Новая оценка</h3>
          <div className="flex gap-2">
            {[5, 4, 3, 2, 1].map((v) => (
              <button
                key={v}
                type="button"
                aria-pressed={value === v}
                onClick={() => setValue(v)}
                className={`h-11 w-11 rounded-xl border text-lg font-bold ${value === v ? "border-brand bg-brand text-on-brand" : `border-line hover:bg-muted ${gradeTone(v)}`}`}
              >
                {v}
              </button>
            ))}
          </div>
          <Select label="Тип оценки" value={effectiveType} onChange={(e) => setTypeId(e.target.value)}>
            {types.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium">Комментарий (обязательно)</span>
            <textarea
              rows={2}
              required
              maxLength={1000}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="За что оценка"
              className="w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
            />
          </label>
          <Button type="submit" loading={busy} disabled={value === null || !comment.trim()} className="w-full">
            Поставить оценку
          </Button>
        </form>
        </>
      )}
    </div>
  );
}
