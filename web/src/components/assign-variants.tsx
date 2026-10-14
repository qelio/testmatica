"use client";

import { Select } from "@/components/ui";
import { classroom } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

export type VariantsValue = {
  /** Тесты вариантов по порядку: 1-й, 2-й…; пустая строка — ещё не выбран. */
  testIds: string[];
  manual: boolean;
  /** Вручную: ученик → номер варианта; кого нет — получит вариант автоматически. */
  picks: Record<string, number>;
};

/** Тест в списках выбора; группы — свои тесты и тесты модуля курса (решение №48). */
export type TestOption = { id: string; title: string; tasks_count: number; max_score: number };
export type TestGroup = { label: string | null; tests: TestOption[] };

/** Варианты списка тестов: свои — без заголовка, остальные — группами. */
export function TestOptions({ groups, hide = [] }: { groups: TestGroup[]; hide?: string[] }) {
  return groups.map((g, n) => {
    const options = g.tests
      .filter((t) => !hide.includes(t.id))
      .map((t) => (
        <option key={t.id} value={t.id}>
          {t.title} · заданий: {t.tasks_count}
        </option>
      ));
    if (!options.length) return null;
    return g.label ? (
      <optgroup key={n} label={g.label}>
        {options}
      </optgroup>
    ) : (
      options
    );
  });
}

export const EMPTY_VARIANTS: VariantsValue = { testIds: ["", ""], manual: false, picks: {} };
const MAX_VARIANTS = 10;

/** Готово к назначению: хотя бы два варианта и у каждого выбран тест. */
export function variantsReady(v: VariantsValue): boolean {
  return v.testIds.length >= 2 && v.testIds.every(Boolean);
}

/** Тесты вариантов (решение №48) — вместо поля «Тест» в назначении по вариантам. */
export function VariantTests({ value, onChange, groups }: { value: VariantsValue; onChange: (v: VariantsValue) => void; groups: TestGroup[] }) {
  const set = (patch: Partial<VariantsValue>) => onChange({ ...value, ...patch });

  function setTest(i: number, id: string) {
    const testIds = value.testIds.map((x, n) => (n === i ? id : x));
    // Тест варианта убрали — ученики на нём снова «авто».
    const picks = id ? value.picks : Object.fromEntries(Object.entries(value.picks).filter(([, v]) => v !== i + 1));
    set({ testIds, picks });
  }

  function removeVariant(i: number) {
    const removed = i + 1;
    const picks = Object.fromEntries(
      Object.entries(value.picks)
        .filter(([, v]) => v !== removed)
        .map(([s, v]) => [s, v > removed ? v - 1 : v]),
    );
    set({ testIds: value.testIds.filter((_, n) => n !== i), picks });
  }

  return (
    <div className="space-y-2">
      {value.testIds.map((id, i) => (
        <div key={i} className="flex items-end gap-2">
          <div className="min-w-0 flex-1">
            <Select label={`Вариант ${i + 1}`} value={id} required onChange={(e) => setTest(i, e.target.value)}>
              <option value="">Выберите тест</option>
              <TestOptions groups={groups} hide={value.testIds.filter((t) => t && t !== id)} />
            </Select>
          </div>
          {value.testIds.length > 2 && (
            <button
              type="button"
              onClick={() => removeVariant(i)}
              className="h-11 rounded-xl px-3 text-fg-soft hover:text-danger"
              aria-label={`Убрать вариант ${i + 1}`}
            >
              ✕
            </button>
          )}
        </div>
      ))}
      {value.testIds.length < MAX_VARIANTS && (
        <button type="button" onClick={() => set({ testIds: [...value.testIds, ""] })} className="text-sm font-medium text-brand hover:underline">
          + Ещё вариант
        </button>
      )}
      <p className="text-xs text-fg-soft">
        Работа одна, но у учеников разные тесты. У каждого варианта свои таймер, порядок заданий и оформление — как в его тесте; критерии оценивания —
        общие.
      </p>
    </div>
  );
}

/** Как раздать варианты: поровну автоматически или вручную — кому какой (только варианты с выбранным тестом). */
export function VariantSplit({
  value,
  onChange,
  targetType,
  targetId,
  studentName,
}: {
  value: VariantsValue;
  onChange: (v: VariantsValue) => void;
  targetType: "group" | "student";
  targetId: string;
  studentName?: string;
}) {
  const group = useLoad(
    () => (value.manual && targetType === "group" && targetId ? classroom.group(targetId) : Promise.resolve(null)),
    [value.manual, targetType, targetId],
  );
  const set = (patch: Partial<VariantsValue>) => onChange({ ...value, ...patch });
  // Номера вариантов, у которых уже выбран тест, — только их можно дать ученику вручную.
  const chosen = value.testIds.flatMap((id, n) => (id ? [n + 1] : []));
  const members =
    targetType === "group"
      ? (group.data?.members ?? []).map((m) => ({ id: m.student_id, name: m.full_name }))
      : targetId
        ? [{ id: targetId, name: studentName ?? "Ученик" }]
        : [];
  const tab = (active: boolean) =>
    `flex-1 rounded-lg px-3 py-1.5 text-sm font-medium whitespace-nowrap ${active ? "bg-surface shadow-sm" : "text-fg-soft hover:text-fg"}`;

  return (
    <fieldset className="space-y-2">
      <legend className="mb-1.5 text-sm font-medium">Как раздать варианты</legend>
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
      ) : !chosen.length ? (
        <p className="text-sm text-fg-soft">Выберите тесты для вариантов — тогда их можно будет раздать.</p>
      ) : (
        <ul className="divide-y divide-line">
          {members.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="text-sm">{m.name}</span>
              <span className="flex gap-1">
                {chosen.map((v) => {
                  const active = value.picks[m.id] === v;
                  return (
                    <button
                      key={v}
                      type="button"
                      aria-pressed={active}
                      aria-label={`${m.name}: вариант ${v}`}
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
    </fieldset>
  );
}
