"use client";

import { Select } from "@/components/ui";
import { classroom, type QuizSummary } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

export type VariantsValue = {
  on: boolean;
  /** Тесты 2-го, 3-го… вариантов; пустая строка — ещё не выбран. */
  testIds: string[];
  manual: boolean;
  /** Вручную: ученик → номер варианта; кого нет — получит вариант автоматически. */
  picks: Record<string, number>;
};

export const NO_VARIANTS: VariantsValue = { on: false, testIds: [""], manual: false, picks: {} };
const MAX_VARIANTS = 10;

/** Варианты работы (решение №48): одна работа, у учеников разные тесты — поровну автоматически или вручную. */
export function AssignVariants({
  value,
  onChange,
  tests,
  mainTestId,
  targetType,
  targetId,
  studentName,
}: {
  value: VariantsValue;
  onChange: (v: VariantsValue) => void;
  tests: QuizSummary[];
  mainTestId: string;
  targetType: "group" | "student";
  targetId: string;
  studentName?: string;
}) {
  const group = useLoad(
    () => (value.on && value.manual && targetType === "group" && targetId ? classroom.group(targetId) : Promise.resolve(null)),
    [value.on, value.manual, targetType, targetId],
  );
  const set = (patch: Partial<VariantsValue>) => onChange({ ...value, ...patch });
  const main = tests.find((t) => t.id === mainTestId);
  const count = 1 + value.testIds.length;
  const members =
    targetType === "group"
      ? (group.data?.members ?? []).map((m) => ({ id: m.student_id, name: m.full_name }))
      : targetId
        ? [{ id: targetId, name: studentName ?? "Ученик" }]
        : [];

  function removeVariant(i: number) {
    const testIds = value.testIds.filter((_, n) => n !== i);
    // Ученики на удалённом варианте — снова «авто», номера дальше — сдвигаются.
    const removed = i + 2;
    const picks = Object.fromEntries(
      Object.entries(value.picks)
        .filter(([, v]) => v !== removed)
        .map(([s, v]) => [s, v > removed ? v - 1 : v]),
    );
    set({ testIds: testIds.length ? testIds : [""], picks });
  }

  const tab = (active: boolean) =>
    `flex-1 rounded-lg px-3 py-1.5 text-sm font-medium whitespace-nowrap ${active ? "bg-surface shadow-sm" : "text-fg-soft hover:text-fg"}`;

  return (
    <fieldset className="space-y-3">
      <label className="flex items-start gap-3">
        <input type="checkbox" checked={value.on} onChange={(e) => set({ on: e.target.checked })} className="mt-1 h-4 w-4 accent-brand" />
        <span className="text-sm">
          <span className="font-medium">Разные варианты</span>
          <span className="block text-fg-soft">Одна работа, но у учеников разные тесты: каждый вариант — отдельный тест.</span>
        </span>
      </label>
      {value.on && (
        <div className="space-y-3 rounded-xl border border-line p-4">
          <div className="space-y-2">
            <p className="text-sm">
              <span className="font-medium">Вариант 1:</span>{" "}
              {main ? `${main.title} · заданий: ${main.tasks_count}` : <span className="text-fg-soft">тест, выбранный выше</span>}
            </p>
            {value.testIds.map((id, i) => (
              <div key={i} className="flex items-end gap-2">
                <div className="min-w-0 flex-1">
                  <Select label={`Вариант ${i + 2}`} value={id} required onChange={(e) => set({ testIds: value.testIds.map((x, n) => (n === i ? e.target.value : x)) })}>
                    <option value="">Выберите тест</option>
                    {tests
                      .filter((t) => t.id !== mainTestId && (t.id === id || !value.testIds.includes(t.id)))
                      .map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.title} · заданий: {t.tasks_count}
                        </option>
                      ))}
                  </Select>
                </div>
                <button
                  type="button"
                  onClick={() => removeVariant(i)}
                  className="h-11 rounded-xl px-3 text-fg-soft hover:text-danger"
                  aria-label={`Убрать вариант ${i + 2}`}
                >
                  ✕
                </button>
              </div>
            ))}
            {count < MAX_VARIANTS && (
              <button type="button" onClick={() => set({ testIds: [...value.testIds, ""] })} className="text-sm font-medium text-brand hover:underline">
                + Ещё вариант
              </button>
            )}
            <p className="text-xs text-fg-soft">У каждого варианта свои таймер, порядок заданий и оформление — как в его тесте. Критерии оценивания — общие для всей работы.</p>
          </div>

          <div className="space-y-2">
            <div className="flex rounded-xl border border-line bg-muted p-1" role="radiogroup" aria-label="Как раздать варианты">
              <button type="button" role="radio" aria-checked={!value.manual} className={tab(!value.manual)} onClick={() => set({ manual: false })}>
                Автоматически
              </button>
              <button type="button" role="radio" aria-checked={value.manual} className={tab(value.manual)} onClick={() => set({ manual: true })}>
                Вручную
              </button>
            </div>
            {!value.manual ? (
              <p className="text-sm text-fg-soft">
                Варианты раздадутся поровну и в случайном порядке. Поменять вариант ученику можно на странице работы, пока он её не начал.
              </p>
            ) : !targetId ? (
              <p className="text-sm text-fg-soft">Сначала выберите, кому назначить.</p>
            ) : (
              <ul className="divide-y divide-line">
                {members.map((m) => (
                  <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <span className="text-sm">{m.name}</span>
                    <span className="flex gap-1">
                      {Array.from({ length: count }, (_, n) => n + 1).map((v) => {
                        const active = value.picks[m.id] === v;
                        return (
                          <button
                            key={v}
                            type="button"
                            aria-pressed={active}
                            onClick={() => {
                              const picks = { ...value.picks };
                              if (active) delete picks[m.id];
                              else picks[m.id] = v;
                              set({ picks });
                            }}
                            className={`h-8 min-w-8 rounded-lg border px-2 text-sm ${active ? "border-brand bg-brand/10 text-brand" : "border-line text-fg-soft hover:text-fg"}`}
                          >
                            {v}
                          </button>
                        );
                      })}
                    </span>
                  </li>
                ))}
                <li className="pt-2 text-xs text-fg-soft">Кому вариант не выбран — получит его автоматически, чтобы вариантов было поровну.</li>
              </ul>
            )}
          </div>
        </div>
      )}
    </fieldset>
  );
}
