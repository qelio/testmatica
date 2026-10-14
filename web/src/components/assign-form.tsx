"use client";

import Link from "next/link";
import { useState } from "react";

import { EMPTY_VARIANTS, VariantSplit, variantsReady, VariantTests, type VariantsValue } from "@/components/assign-variants";
import { Alert, Button, Field, Select } from "@/components/ui";
import { academic, type Assignment, type AssignmentKind, assessment, billing, classroom, type GradeScale, schedule } from "@/lib/api";
import { fmtDateTime, fromInputs } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

export type AssignPreset = {
  testId?: string;
  kind?: AssignmentKind;
  targetType?: "group" | "student";
  targetId?: string;
  lessonId?: string;
};

const KINDS: { kind: AssignmentKind; title: string; hint: string }[] = [
  { kind: "test", title: "Тест", hint: "Самостоятельная работа без привязки к уроку: ученики проходят, пока тест открыт." },
  { kind: "homework", title: "ДЗ к уроку", hint: "Домашнее задание к занятию — ученики увидят его в карточке урока в расписании." },
  {
    kind: "live",
    title: "Тест на уроке",
    hint: "Проходят во время занятия, вы видите прогресс каждого. Когда закончите — завершите тест, незавершённые работы сдадутся.",
  },
];
const MODES: { mode: "plain" | "variants"; title: string; hint: string }[] = [
  { mode: "plain", title: "Обычное", hint: "Один тест — всем ученикам." },
  { mode: "variants", title: "По вариантам", hint: "Одна работа, но у учеников разные тесты." },
];
const ATTEMPTS: { value: string; title: string }[] = [
  { value: "1", title: "Одна" },
  { value: "2", title: "Две" },
  { value: "3", title: "Три" },
  { value: "5", title: "Пять" },
  { value: "", title: "Без ограничений" },
];

const DEFAULT_SCALE: GradeScale = { five: 85, four: 65, three: 45 };
const SCALE_PRESETS: { title: string; scale: GradeScale }[] = [
  { title: "Обычные", scale: DEFAULT_SCALE },
  { title: "Строгие", scale: { five: 90, four: 75, three: 50 } },
  { title: "Мягкие", scale: { five: 80, four: 60, three: 40 } },
];

/** Критерии оценивания: с какого процента ставится 5, 4 и 3 (ниже — 2). */
function GradeCriteria({ scale, onChange, maxScore }: { scale: GradeScale; onChange: (s: GradeScale) => void; maxScore?: number }) {
  const valid = scale.five > scale.four && scale.four > scale.three && scale.three >= 1 && scale.five <= 100;
  const points = (p: number) => Math.ceil((p / 100) * (maxScore ?? 0) - 1e-9);
  const row = (grade: "five" | "four" | "three", label: string) => (
    <label className="flex items-center gap-2 text-sm">
      <span className="w-6 text-center text-base font-semibold">{label}</span>
      <span className="text-fg-soft">от</span>
      <input
        type="number"
        min={1}
        max={100}
        value={scale[grade]}
        onChange={(e) => onChange({ ...scale, [grade]: Math.min(100, Math.max(1, Number(e.target.value) || 1)) })}
        className="h-9 w-16 rounded-lg border border-line bg-surface px-2"
        aria-label={`Оценка ${label}: от скольких процентов`}
      />
      <span className="text-fg-soft">%</span>
    </label>
  );
  return (
    <fieldset className="space-y-2">
      <legend className="mb-1.5 text-sm font-medium">Критерии оценивания</legend>
      <div className="flex flex-wrap gap-1.5">
        {SCALE_PRESETS.map((p) => {
          const active = p.scale.five === scale.five && p.scale.four === scale.four && p.scale.three === scale.three;
          return (
            <button
              key={p.title}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(p.scale)}
              className={`rounded-lg border px-3 py-1.5 text-sm ${active ? "border-brand bg-brand/10 text-brand" : "border-line text-fg-soft hover:text-fg"}`}
            >
              {p.title}
            </button>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-2">
        {row("five", "5")}
        {row("four", "4")}
        {row("three", "3")}
      </div>
      <p className={`text-xs ${valid ? "text-fg-soft" : "text-danger"}`}>
        {valid
          ? `Ниже ${scale.three}% — 2.${maxScore ? ` В баллах (всего ${maxScore}): 5 — от ${points(scale.five)}, 4 — от ${points(scale.four)}, 3 — от ${points(scale.three)}.` : ""} Оценку любой работы можно потом исправить вручную.`
          : "Границы должны убывать: для «5» больше, чем для «4», для «4» — больше, чем для «3»."}
      </p>
    </fieldset>
  );
}

/** Дата и время одной парой полей; пусто — не задано. */
function When({ label, date, time, onDate, onTime }: { label: string; date: string; time: string; onDate: (v: string) => void; onTime: (v: string) => void }) {
  return (
    <div className="grid grid-cols-[1fr_7rem] gap-2">
      <Field label={label} type="date" value={date} onChange={(e) => onDate(e.target.value)} />
      <Field label="Время" type="time" value={time} disabled={!date} onChange={(e) => onTime(e.target.value)} />
    </div>
  );
}

/** Назначение теста: какой тест, кому, как (тест / ДЗ / на уроке), когда открыть и закрыть, сколько попыток. */
export function AssignForm({ preset, onAssigned }: { preset: AssignPreset; onAssigned: (a: Assignment) => void }) {
  const own = useLoad(() => assessment.tests(), []);
  // Публичный тест чужого курса («Назначить» со страницы модуля) — в списке отдельно от своих (решение №44).
  const course = useLoad(
    () => (preset.testId ? assessment.courseTest(preset.testId).catch(() => null) : Promise.resolve(null)),
    [preset.testId],
  );
  const fromCourse = course.data && !own.data?.some((t) => t.id === course.data!.id) ? course.data : null;
  const tests = { data: own.data ? [...own.data, ...(fromCourse ? [fromCourse] : [])] : null };
  const groups = useLoad(() => classroom.groups(), []);
  const students = useLoad(() => classroom.students(), []);
  // Уроки за месяц назад и на два вперёд — к какому привязать тест и куда ставить оценку.
  const lessons = useLoad(() => {
    const now = Date.now();
    return schedule.lessons(new Date(now - 30 * 864e5), new Date(now + 60 * 864e5));
  }, []);
  const gradeTypes = useLoad(() => academic.gradeTypes(), []);
  const plan = useLoad(async () => (await billing.subscription()).plan, []);

  const [testId, setTestId] = useState(preset.testId ?? "");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<AssignmentKind>(preset.kind ?? (preset.lessonId ? "homework" : "test"));
  const [targetType, setTargetType] = useState<"group" | "student">(preset.targetType ?? "group");
  const [targetId, setTargetId] = useState(preset.targetId ?? "");
  const [lessonId, setLessonId] = useState(preset.lessonId ?? "");
  const [openDate, setOpenDate] = useState("");
  const [openTime, setOpenTime] = useState("08:00");
  const [closeDate, setCloseDate] = useState("");
  const [closeTime, setCloseTime] = useState("20:00");
  const [attempts, setAttempts] = useState("1");
  const [toJournal, setToJournal] = useState(false);
  const [proctoring, setProctoring] = useState(false);
  const [gradeTypeId, setGradeTypeId] = useState("");
  const [scale, setScale] = useState<GradeScale>(DEFAULT_SCALE);
  // Обычное назначение — один тест; по вариантам — у учеников разные тесты (решение №48).
  const [mode, setMode] = useState<"plain" | "variants">("plain");
  const [variants, setVariants] = useState<VariantsValue>(EMPTY_VARIANTS);
  const byVariants = mode === "variants";
  const mainId = byVariants ? variants.testIds[0] : testId;
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const withLesson = kind !== "test";
  const selectedTest = tests.data?.find((t) => t.id === mainId);
  const targetLessons = (lessons.data ?? []).filter(
    (l) =>
      l.status !== "cancelled" &&
      (targetType === "group" ? l.group_id === targetId : l.kind === "individual" && l.participants?.some((p) => p.id === targetId)),
  );


  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    const lesson = withLesson ? lessonId || null : null;
    try {
      onAssigned(
        await assessment.assign(mainId, {
          kind,
          title: title.trim() || null,
          target_type: targetType,
          target_id: targetId,
          lesson_id: lesson,
          opens_at: openDate ? fromInputs(openDate, openTime).toISOString() : null,
          deadline: closeDate ? fromInputs(closeDate, closeTime).toISOString() : null,
          max_attempts: attempts ? Number(attempts) : null,
          grade_scale: scale,
          grade_to_journal: toJournal,
          grade_type_id: toJournal ? gradeTypeId || null : null,
          proctoring,
          ...(byVariants ? { variant_test_ids: variants.testIds.slice(1), variants: variants.manual ? variants.picks : {} } : {}),
        }),
      );
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  function switchMode(next: "plain" | "variants") {
    if (next === mode) return;
    // Выбранный тест переходит между режимами: обычный тест ↔ 1-й вариант.
    if (next === "variants" && testId && !variants.testIds[0]) setVariants({ ...variants, testIds: [testId, ...variants.testIds.slice(1)] });
    if (next === "plain" && variants.testIds[0]) setTestId(variants.testIds[0]);
    setMode(next);
  }

  const tab = (active: boolean) =>
    `flex-1 rounded-lg px-3 py-1.5 text-sm font-medium whitespace-nowrap ${active ? "bg-surface shadow-sm" : "text-fg-soft hover:text-fg"}`;

  return (
    <div className="space-y-4">
      {/* Обычное назначение или по вариантам (решение №48) — над формой, крупными плитками. */}
      <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Как назначить: один тест или варианты">
        {MODES.map((m) => {
          const active = mode === m.mode;
          return (
            <button
              key={m.mode}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => switchMode(m.mode)}
              className={`flex items-start gap-3 rounded-2xl border p-4 text-left transition-colors ${active ? "border-brand bg-brand/5 ring-2 ring-brand/20" : "border-line bg-surface hover:bg-muted"}`}
            >
              <span aria-hidden className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border-2 ${active ? "border-brand" : "border-line"}`}>
                {active && <span className="h-2.5 w-2.5 rounded-full bg-brand" />}
              </span>
              <span>
                <span className="block font-medium">{m.title}</span>
                <span className="block text-sm text-fg-soft">{m.hint}</span>
              </span>
            </button>
          );
        })}
      </div>
      <form className="space-y-5 rounded-2xl border border-line bg-surface p-5" onSubmit={submit}>
        {error && <Alert>{error}</Alert>}
        {byVariants ? (
          <VariantTests value={variants} onChange={setVariants} tests={tests.data ?? []} />
        ) : (
          <Select label="Тест" value={testId} required onChange={(e) => setTestId(e.target.value)}>
            <option value="">{tests.data && !tests.data.length ? "Сначала создайте тест" : "Выберите тест"}</option>
            {own.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.title} · заданий: {t.tasks_count}
              </option>
            ))}
            {fromCourse && (
              <optgroup label={`Из курса «${fromCourse.module?.course_title ?? "библиотеки"}»`}>
                <option value={fromCourse.id}>
                  {fromCourse.title} · заданий: {fromCourse.tasks_count}
                </option>
              </optgroup>
            )}
          </Select>
        )}
        <Field
          label="Название для учеников"
          maxLength={200}
          value={title}
          placeholder={selectedTest?.title ?? "Например: ДЗ к уроку 12 марта"}
          hint="Так назначение увидят ученики, в журнале и уведомлениях. Не заполните — будет как у теста."
          onChange={(e) => setTitle(e.target.value)}
        />

        <div className="space-y-2">
          <div className="flex flex-wrap rounded-xl border border-line bg-muted p-1" role="radiogroup" aria-label="Как назначить">
            {KINDS.map((k) => (
              <button key={k.kind} type="button" role="radio" aria-checked={kind === k.kind} className={tab(kind === k.kind)} onClick={() => setKind(k.kind)}>
                {k.title}
              </button>
            ))}
          </div>
          <p className="text-sm text-fg-soft">{KINDS.find((k) => k.kind === kind)?.hint}</p>
        </div>

        <div className="grid grid-cols-[auto_1fr] items-end gap-3">
          <Select
            label="Кому"
            value={targetType}
            onChange={(e) => {
              setTargetType(e.target.value as "group" | "student");
              setTargetId("");
              setLessonId("");
            }}
          >
            <option value="group">Группе</option>
            <option value="student">Ученику</option>
          </Select>
          <Select
            label={targetType === "group" ? "Группа" : "Ученик"}
            value={targetId}
            required
            onChange={(e) => {
              setTargetId(e.target.value);
              setLessonId("");
            }}
          >
            <option value="">Выберите</option>
            {targetType === "group"
              ? groups.data?.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.title}
                  </option>
                ))
              : students.data
                  ?.filter((s) => s.status === "active")
                  .map((s) => (
                    <option key={s.student_id} value={s.student_id}>
                      {s.full_name}
                    </option>
                  ))}
          </Select>
        </div>

        {withLesson && (
          <Select label="Урок" value={lessonId} required disabled={!targetId} onChange={(e) => setLessonId(e.target.value)}>
            <option value="">{targetId ? (targetLessons.length ? "Выберите урок" : "Уроков рядом нет") : "Сначала выберите, кому"}</option>
            {targetLessons.map((l) => (
              <option key={l.id} value={l.id}>
                {fmtDateTime(l.starts_at)}
                {l.topic ? ` · ${l.topic}` : l.subject ? ` · ${l.subject}` : ""}
              </option>
            ))}
          </Select>
        )}

        {byVariants && (
          <VariantSplit
            value={variants}
            onChange={setVariants}
            targetType={targetType}
            targetId={targetId}
            studentName={students.data?.find((s) => s.student_id === targetId)?.full_name}
          />
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <When label="Откроется (пусто — сразу)" date={openDate} time={openTime} onDate={setOpenDate} onTime={setOpenTime} />
          <When label="Закроется (пусто — без срока)" date={closeDate} time={closeTime} onDate={setCloseDate} onTime={setCloseTime} />
        </div>

        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">Сколько раз можно пройти</legend>
          <div className="flex flex-wrap gap-1.5">
            {ATTEMPTS.map((o) => (
              <button
                key={o.value || "none"}
                type="button"
                aria-pressed={attempts === o.value}
                onClick={() => setAttempts(o.value)}
                className={`rounded-lg border px-3 py-1.5 text-sm ${attempts === o.value ? "border-brand bg-brand/10 text-brand" : "border-line text-fg-soft hover:text-fg"}`}
              >
                {o.title}
              </button>
            ))}
          </div>
          {attempts !== "1" && <p className="mt-1.5 text-xs text-fg-soft">В итог и в журнал идёт лучшая из попыток.</p>}
        </fieldset>

        <GradeCriteria scale={scale} onChange={setScale} maxScore={selectedTest?.max_score} />

        <label className="flex items-start gap-3">
          <input type="checkbox" checked={toJournal} onChange={(e) => setToJournal(e.target.checked)} className="mt-1 h-4 w-4 accent-brand" />
          <span className="text-sm">
            <span className="font-medium">Выставить оценку в журнал</span>
            <span className="block text-fg-soft">
              Когда работа проверена, оценка появится в журнале {targetType === "group" ? "группы" : "ученика"} отдельной колонкой с названием
              работы — не в колонке урока.
            </span>
          </span>
        </label>
        {toJournal && (
          <Select label="Тип оценки" value={gradeTypeId} required onChange={(e) => setGradeTypeId(e.target.value)}>
            <option value="">Выберите</option>
            {gradeTypes.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
        )}

        <label className={`flex items-start gap-3 ${plan.data === "basic" ? "" : "opacity-60"}`}>
          <input
            type="checkbox"
            checked={proctoring}
            disabled={plan.data !== "basic"}
            onChange={(e) => setProctoring(e.target.checked)}
            className="mt-1 h-4 w-4 accent-brand"
          />
          <span className="text-sm">
            <span className="font-medium">Прокторинг</span>
            <span className="block text-fg-soft">
              Ученик соглашается на мониторинг и показывает весь экран; вы видите экраны всех, сигналы о смене вкладки и можете включить
              камеру. Экран записывается, запись хранится 2 недели.
              {plan.data && plan.data !== "basic" && (
                <>
                  {" "}
                  Доступно на тарифе{" "}
                  <Link href="/dashboard/subscription" className="text-brand hover:underline">
                    «Базовый»
                  </Link>
                  .
                </>
              )}
            </span>
          </span>
        </label>

        <Button
          type="submit"
          loading={busy}
          disabled={!mainId || !targetId || (byVariants && !variantsReady(variants)) || (withLesson && !lessonId) || !(scale.five > scale.four && scale.four > scale.three)}
          className="w-full"
        >
          {kind === "live" && !openDate ? "Запустить тест" : "Назначить"}
        </Button>
      </form>
    </div>
  );
}
