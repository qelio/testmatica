"use client";

import { useState } from "react";

import { Alert, Button, Field, Select } from "@/components/ui";
import { content, type LessonRequest, marketplace, type RequestGoal, type RequestInput, type SubjectRef } from "@/lib/api";
import { GOAL_LABELS } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

const WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"];
const TEXTAREA =
  "w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

function CompetencyPicker({
  label,
  subjectId,
  value,
  onChange,
}: {
  label: string;
  subjectId: string;
  value: string[];
  onChange: (ids: string[]) => void;
}) {
  const list = useLoad(async () => (subjectId ? marketplace.competencies(subjectId) : []), [subjectId]);
  if (!subjectId || !list.data?.length) return null;
  return (
    <fieldset>
      <legend className="mb-1.5 text-sm font-medium">{label}</legend>
      <div className="flex flex-wrap gap-1.5">
        {list.data.map((c) => {
          const on = value.includes(c.id);
          return (
            <button
              key={c.id}
              type="button"
              aria-pressed={on}
              onClick={() => onChange(on ? value.filter((x) => x !== c.id) : [...value, c.id])}
              className={`rounded-lg border px-2.5 py-1 text-sm ${on ? "border-brand bg-brand/10 text-brand" : "border-line text-fg-soft hover:text-fg"}`}
            >
              {c.title}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

/** Заявка ученика: адресная (tutorId) или открытая — её увидят репетиторы по предмету. */
export function RequestForm({
  tutorId,
  subjects: only,
  defaultPrice,
  onCreated,
}: {
  tutorId?: string;
  subjects?: SubjectRef[];
  defaultPrice?: number | null;
  onCreated: (r: LessonRequest) => void;
}) {
  const all = useLoad(async () => only ?? content.subjects(), []);
  const subjects = all.data ?? [];
  const [form, setForm] = useState<RequestInput>({
    tutor_id: tutorId ?? null,
    subject_id: only?.length === 1 ? only[0].id : "",
    goal: "ege",
    current_ids: [],
    desired_ids: [],
    schedule: { weekdays: [] },
    price: defaultPrice ?? 1000,
    duration_min: 60,
    comment: "",
  });
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof RequestInput>(k: K, v: RequestInput[K]) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <form
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        e.stopPropagation();
        setBusy(true);
        setError(undefined);
        try {
          onCreated(await marketplace.createRequest(form));
        } catch (err) {
          setError(errorText(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      {error && <Alert>{error}</Alert>}
      <div className="grid gap-3 sm:grid-cols-2">
        <Select
          label="Предмет"
          required
          value={form.subject_id}
          onChange={(e) => setForm((f) => ({ ...f, subject_id: e.target.value, current_ids: [], desired_ids: [] }))}
        >
          <option value="">Выберите</option>
          {subjects.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </Select>
        <Select label="Цель" value={form.goal} onChange={(e) => set("goal", e.target.value as RequestGoal)}>
          {Object.entries(GOAL_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </Select>
      </div>
      <CompetencyPicker label="Что уже знаю" subjectId={form.subject_id} value={form.current_ids} onChange={(v) => set("current_ids", v)} />
      <CompetencyPicker label="Что хочу получить" subjectId={form.subject_id} value={form.desired_ids} onChange={(v) => set("desired_ids", v)} />

      <fieldset>
        <legend className="mb-1.5 text-sm font-medium">В какие дни удобно заниматься</legend>
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex gap-1">
            {WEEKDAYS.map((d, i) => {
              const on = form.schedule.weekdays.includes(i);
              return (
                <button
                  key={d}
                  type="button"
                  aria-pressed={on}
                  onClick={() =>
                    set("schedule", {
                      ...form.schedule,
                      weekdays: on ? form.schedule.weekdays.filter((x) => x !== i) : [...form.schedule.weekdays, i].sort(),
                    })
                  }
                  className={`h-9 w-9 rounded-lg border text-sm ${on ? "border-brand bg-brand/10 text-brand" : "border-line text-fg-soft"}`}
                >
                  {d}
                </button>
              );
            })}
          </div>
          <span className="pb-2 text-xs text-fg-soft">Время согласуете с репетитором в чате</span>
        </div>
      </fieldset>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          label="Предлагаемая цена за занятие, ₽"
          type="number"
          required
          min={100}
          step={50}
          value={form.price}
          hint="Окончательную цену согласуете с репетитором в чате"
          onChange={(e) => set("price", Number(e.target.value))}
        />
        <Select label="Длительность" value={form.duration_min} onChange={(e) => set("duration_min", Number(e.target.value) as RequestInput["duration_min"])}>
          {[30, 45, 60, 90].map((d) => (
            <option key={d} value={d}>
              {d} мин
            </option>
          ))}
        </Select>
      </div>
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium">Комментарий</span>
        <textarea
          rows={3}
          maxLength={2000}
          className={TEXTAREA}
          value={form.comment}
          placeholder="Класс, цель, что не получается — всё, что поможет репетитору"
          onChange={(e) => set("comment", e.target.value)}
        />
      </label>
      <Button type="submit" loading={busy} className="w-full" disabled={!form.subject_id}>
        {tutorId ? "Отправить заявку" : "Опубликовать заявку"}
      </Button>
      {!tutorId && <p className="text-xs text-fg-soft">Заявку увидят репетиторы по предмету. Она закроется сама через 14 дней или когда вы договоритесь.</p>}
    </form>
  );
}
