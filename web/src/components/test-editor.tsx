"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ExamChips } from "@/components/exams";
import { TaskNumber } from "@/components/task-number";
import { TaskPicker } from "@/components/task-picker";
import { PreviewToggle, TaskPreview } from "@/components/task-preview";
import { Alert, Badge, Button, Field, Select } from "@/components/ui";
import { assessment, content, type CourseSummary, type CourseTree, type Quiz, type QuizInput, type TaskSummary, type TaskType, type TimeMode } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { themeLabel } from "@/lib/course-themes";
import { GRADE_LEVELS } from "@/lib/assignments";
import { TASK_TYPE_LABELS } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

type Item = { task_id: string; points: number; solution_file: boolean; title: string; task?: TaskSummary; type?: TaskType };

/** К каким типам задач можно запросить файл с решением (решение №34). */
const SOLUTION_TYPES = new Set<TaskType>(["short", "choice"]);

const TEXTAREA =
  "w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

function canAskFile(item: Item): boolean {
  const type = item.task?.type ?? item.type;
  return !!type && SOLUTION_TYPES.has(type);
}

/** Редактор теста: задачи из банка, баллы, порядок, перемешивание, таймер. Назначают тест в разделе «Назначение тестов».
 *  preset — новый тест со страницы модуля: сразу привязан к нему (решение №43). */
export function TestEditor({ test, preset }: { test?: Quiz; preset?: { courseId: string; moduleId: string } }) {
  const router = useRouter();
  const [title, setTitle] = useState(test?.title ?? "");
  const [description, setDescription] = useState(test?.description ?? "");
  const [gradeLevel, setGradeLevel] = useState(test?.grade_level ? String(test.grade_level) : "");
  const [orderMode, setOrderMode] = useState(test?.order_mode ?? "fixed");
  const [shuffle, setShuffle] = useState(test?.shuffle_options ?? false);
  const [timeMode, setTimeMode] = useState<TimeMode>(test?.time_mode ?? "none");
  const [minutes, setMinutes] = useState(test?.time_limit_s ? test.time_limit_s / 60 : 20);
  const { user } = useAuth();
  // Привязка к модулю курса (по желанию): свои курсы и опубликованные в библиотеке (решение №44).
  const [courseId, setCourseId] = useState(test?.module?.course_id ?? preset?.courseId ?? "");
  const [moduleId, setModuleId] = useState(test?.module?.id ?? preset?.moduleId ?? "");
  const [shared, setShared] = useState(test?.shared ?? false);
  const mine = useLoad(() => content.myCourses(), []);
  const library = useLoad(() => content.catalog({}), []);
  const tree = useLoad(() => (courseId ? content.course(courseId, true) : Promise.resolve(null)), [courseId]);
  const courseAuthor = !!tree.data && tree.data.owner_id === user?.id;
  const [items, setItems] = useState<Item[]>(
    () => test?.items.map((i) => ({ task_id: i.task_id, points: i.points, solution_file: i.solution_file, title: i.task.title, task: i.task })) ?? [],
  );
  const [picking, setPicking] = useState(false);
  const [opened, setOpened] = useState<Set<string>>(() => new Set());
  const toggleOpen = (id: string) =>
    setOpened((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const [dirty, setDirty] = useState(!test);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const change = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setDirty(true);
  };
  const move = (i: number, j: number) =>
    change(setItems)(items.map((x, n) => (n === i ? items[j] : n === j ? items[i] : x)));

  async function save(e?: React.FormEvent) {
    e?.preventDefault();
    setBusy(true);
    setError(undefined);
    const body: QuizInput = {
      title,
      description,
      grade_level: Number(gradeLevel),
      order_mode: orderMode,
      shuffle_options: shuffle,
      time_mode: timeMode,
      time_limit_s: timeMode === "none" ? null : Math.round(minutes * 60),
      module_id: moduleId || null,
      shared: shared && !!moduleId && courseAuthor,
      items: items.map((i) => ({ task_id: i.task_id, points: i.points, solution_file: i.solution_file && canAskFile(i) })),
    };
    try {
      const saved = test ? await assessment.updateTest(test.id, body) : await assessment.createTest(body);
      setDirty(false);
      if (!test) router.replace(`/dashboard/tests/${saved.id}`);
      else setItems(saved.items.map((i) => ({ task_id: i.task_id, points: i.points, solution_file: i.solution_file, title: i.task.title, task: i.task })));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const total = items.reduce((n, i) => n + i.points, 0);
  const hasManual = items.some((i) => i.task?.type === "long");
  const withFiles = items.some((i) => i.solution_file && canAskFile(i));

  return (
    <form className="space-y-6" onSubmit={save}>
      {error && <Alert>{error}</Alert>}
      <section className="space-y-4 rounded-2xl border border-line bg-surface p-5">
        <div className="grid gap-3 sm:grid-cols-[1fr_12rem]">
          <Field label="Название" required maxLength={200} value={title} onChange={(e) => change(setTitle)(e.target.value)} />
          <Select label="Для какого класса" required value={gradeLevel} onChange={(e) => change(setGradeLevel)(e.target.value)}>
            <option value="">Выберите</option>
            {GRADE_LEVELS.map((g) => (
              <option key={g} value={g}>
                {g} класс
              </option>
            ))}
          </Select>
        </div>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Описание для учеников</span>
          <textarea rows={2} maxLength={5000} className={TEXTAREA} value={description} onChange={(e) => change(setDescription)(e.target.value)} />
        </label>
        <div className="grid gap-3 sm:grid-cols-3">
          <Select label="Порядок заданий" value={orderMode} onChange={(e) => change(setOrderMode)(e.target.value as "fixed" | "random")}>
            <option value="fixed">Как в списке</option>
            <option value="random">Случайный у каждого</option>
          </Select>
          <Select label="Ограничение времени" value={timeMode} onChange={(e) => change(setTimeMode)(e.target.value as TimeMode)}>
            <option value="none">Без таймера</option>
            <option value="total">На весь тест</option>
            <option value="per_task">На каждое задание</option>
          </Select>
          {timeMode !== "none" && (
            <Field
              label={timeMode === "total" ? "Минут на тест" : "Минут на задание"}
              type="number"
              min={0.5}
              max={360}
              step={0.5}
              required
              value={minutes}
              onChange={(e) => change(setMinutes)(Number(e.target.value))}
            />
          )}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={shuffle} onChange={(e) => change(setShuffle)(e.target.checked)} className="h-4 w-4 accent-brand" />
          Перемешивать варианты ответа — у каждого ученика свой порядок
        </label>
        {timeMode === "per_task" && (
          <p className="text-xs text-fg-soft">Задания открываются по одному; к пройденному вернуться нельзя. Когда время выходит — открывается следующее.</p>
        )}
        <ModuleField
          mine={mine.data ?? []}
          library={library.data ?? []}
          extraCourse={test?.module && test.module.course_title ? { id: test.module.course_id, title: test.module.course_title } : null}
          courseId={courseId}
          tree={tree.data ?? null}
          moduleId={moduleId}
          onCourse={(id) => {
            change(setCourseId)(id);
            setModuleId("");
            setShared(false);
          }}
          onModule={change(setModuleId)}
        />
        {moduleId && courseAuthor && (
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={shared} onChange={(e) => change(setShared)(e.target.checked)} className="mt-0.5 h-4 w-4 accent-brand" />
            <span>
              Для всех, кто проходит курс
              <span className="block text-xs text-fg-soft">
                Тест виден под модулем всем ученикам курса, его можно пройти самостоятельно; в публичную библиотеку попадает вместе
                с курсом. Без галочки — только ваш: проверочная или контрольная, которую вы назначаете сами.
              </span>
            </span>
          </label>
        )}
        <p className="text-xs text-fg-soft">
          {moduleId && tree.data
            ? `Оформление для учеников — как у курса: «${themeLabel(tree.data.theme)}».`
            : "Оформление для учеников — обычное. Тесты, привязанные к модулю курса, оформляются как курс."}
        </p>
      </section>

      <section className="space-y-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-lg font-semibold">Задания</h2>
          <span className="text-sm text-fg-soft">
            {items.length} · всего баллов: {total}
          </span>
        </div>
        {items.length > 0 && (
          <ol className="divide-y divide-line rounded-2xl border border-line bg-surface">
            {items.map((item, i) => (
              <li key={item.task_id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
                <span className="w-6 text-right text-sm text-fg-soft tabular-nums">{i + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">
                    {item.task && <TaskNumber n={item.task.number} />}
                    {item.title}
                  </span>
                  {item.task && (
                    <span className="mt-0.5 flex flex-wrap items-center gap-1.5">
                      <Badge>{TASK_TYPE_LABELS[item.task.type]}</Badge>
                      <ExamChips labels={item.task.exam_items} />
                    </span>
                  )}
                </span>
                {canAskFile(item) && (
                  <label className="flex items-center gap-1.5 text-sm text-fg-soft" title="Ученик прикрепит фото или файл с ходом решения">
                    <input
                      type="checkbox"
                      checked={item.solution_file}
                      onChange={(e) => change(setItems)(items.map((x, n) => (n === i ? { ...x, solution_file: e.target.checked } : x)))}
                      className="h-4 w-4 accent-brand"
                    />
                    файл с решением
                  </label>
                )}
                <label className="flex items-center gap-1.5 text-sm text-fg-soft">
                  баллы
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={item.points}
                    onChange={(e) => change(setItems)(items.map((x, n) => (n === i ? { ...x, points: Math.max(1, Number(e.target.value)) } : x)))}
                    className="h-9 w-16 rounded-lg border border-line bg-surface px-2 text-fg"
                    aria-label={`Баллы за задание ${i + 1}`}
                  />
                </label>
                <PreviewToggle open={opened.has(item.task_id)} onToggle={() => toggleOpen(item.task_id)} />
                <span className="flex">
                  <button type="button" className="px-1.5 text-fg-soft hover:text-fg disabled:opacity-30" disabled={i === 0} onClick={() => move(i, i - 1)} aria-label="Выше">
                    ↑
                  </button>
                  <button type="button" className="px-1.5 text-fg-soft hover:text-fg disabled:opacity-30" disabled={i === items.length - 1} onClick={() => move(i, i + 1)} aria-label="Ниже">
                    ↓
                  </button>
                  <button type="button" className="px-1.5 text-fg-soft hover:text-danger" onClick={() => change(setItems)(items.filter((_, n) => n !== i))} aria-label="Убрать из теста">
                    ✕
                  </button>
                </span>
                {opened.has(item.task_id) && (
                  <div className="w-full">
                    <TaskPreview taskId={item.task_id} />
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}
        {hasManual && <p className="text-xs text-fg-soft">Развёрнутые ответы проверяете вы — итог и оценка появятся после проверки.</p>}
        {withFiles && (
          <p className="text-xs text-fg-soft">
            К отмеченным заданиям ученик прикрепит файл с решением. Ответы проверятся автоматически и ученик сразу увидит, какие верны, но итог и
            оценку он получит после вашей проверки — работа будет ждать её в «Назначении тестов».
          </p>
        )}
        {picking ? (
          <div className="space-y-2">
            <TaskPicker
              selected={null}
              autoOnly={false}
              exclude={items.map((i) => i.task_id)}
              onSelect={(id, taskTitle, type) => change(setItems)([...items, { task_id: id, points: 1, solution_file: false, title: taskTitle, type }])}
            />
            <Button type="button" variant="ghost" onClick={() => setPicking(false)}>
              Готово
            </Button>
          </div>
        ) : (
          <Button type="button" variant="secondary" onClick={() => setPicking(true)}>
            + Добавить задачи из банка
          </Button>
        )}
      </section>

      <div className="flex flex-wrap gap-2 border-t border-line pt-4">
        <Button type="submit" loading={busy} disabled={!dirty && !!test}>
          {test ? (dirty ? "Сохранить" : "Сохранено") : "Создать тест"}
        </Button>
        {test && !dirty && items.length > 0 && (
            <Link
              href={`/dashboard/assignments/new?test=${test.id}`}
              className="rounded-xl border border-line px-4 py-2.5 text-sm font-medium hover:bg-muted"
            >
              Назначить…
            </Link>
        )}
        {test && dirty && <span className="self-center text-sm text-fg-soft">Сохраните изменения, чтобы назначить тест</span>}
        {test && test.assignments_count === 0 && (
          <Button
            type="button"
            variant="ghost"
            className="ml-auto text-danger"
            onClick={async () => {
              if (!window.confirm("Удалить тест?")) return;
              try {
                await assessment.deleteTest(test.id);
                router.replace("/dashboard/tests");
              } catch (err) {
                setError(errorText(err));
              }
            }}
          >
            Удалить
          </Button>
        )}
      </div>
    </form>
  );
}

/** Тема курса библиотеки, к которой относится тест (решение №43): курс → модуль. По желанию. */
function ModuleField({
  mine,
  library,
  extraCourse,
  courseId,
  tree,
  moduleId,
  onCourse,
  onModule,
}: {
  mine: CourseSummary[];
  library: CourseSummary[];
  extraCourse: { id: string; title: string } | null;
  courseId: string;
  tree: CourseTree | null;
  moduleId: string;
  onCourse: (id: string) => void;
  onModule: (id: string) => void;
}) {
  // Свои курсы (в том числе черновики) и опубликованные чужие; привязанный курс могли снять — показываем его всё равно.
  const ownIds = new Set(mine.map((c) => c.id));
  const others = library.filter((c) => !ownIds.has(c.id));
  const known = extraCourse && !ownIds.has(extraCourse.id) && !others.some((c) => c.id === extraCourse.id) ? extraCourse : null;
  return (
    <div className="space-y-1.5">
      <div className="grid gap-3 sm:grid-cols-2">
        <Select label="Курс (по желанию)" value={courseId} onChange={(e) => onCourse(e.target.value)}>
          <option value="">Без привязки к курсу</option>
          {known && <option value={known.id}>{known.title}</option>}
          {mine.length > 0 && (
            <optgroup label="Мои курсы">
              {mine.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </optgroup>
          )}
          {others.length > 0 && (
            <optgroup label="Библиотека">
              {others.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </optgroup>
          )}
        </Select>
        {courseId && (
          <Select label="Тема (модуль)" value={moduleId} onChange={(e) => onModule(e.target.value)}>
            <option value="">{tree ? "Выберите модуль" : "Загрузка…"}</option>
            {tree?.sections.map((s) => (
              <optgroup key={s.id} label={s.title}>
                {s.modules.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.title}
                  </option>
                ))}
              </optgroup>
            ))}
          </Select>
        )}
      </div>
      <p className="text-xs text-fg-soft">Тест появится на странице модуля в блоке «Тесты по теме» — там же кнопка «Назначить».</p>
    </div>
  );
}
