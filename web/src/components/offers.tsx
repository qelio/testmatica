"use client";

import Link from "next/link";
import { useState } from "react";

import { Avatar, Rating } from "@/components/tutor-card";
import { Alert, Badge, Button, Field, Select } from "@/components/ui";
import { content, type GroupOffer, marketplace, type OfferInput, planning, type TutorLevel } from "@/lib/api";
import { toDateInput } from "@/lib/dates";
import { fmtOfferSchedule, fmtRub, LEVEL_LABELS, OFFER_STATUS, pluralWord } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";
import { useMarketBase } from "@/lib/market-base";

const TEXTAREA =
  "w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";
const WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"];

export function priceText(price: number): string {
  return price ? `${fmtRub(price)} за занятие` : "бесплатно";
}

export function seatsText(o: GroupOffer): string {
  return `${o.enrolled_count} из ${o.max_students} ${pluralWord(o.max_students, "места", "мест", "мест")} · минимум ${o.min_students}`;
}

/** Карточка набора в каталоге и в профиле репетитора. */
export function OfferCard({ offer, showTutor = true }: { offer: GroupOffer; showTutor?: boolean }) {
  const st = OFFER_STATUS[offer.status];
  const base = useMarketBase();
  return (
    <Link href={`${base}/groups/${offer.id}`} className="block space-y-2 rounded-2xl border border-line bg-surface p-5 hover:border-brand/50">
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 flex-1 text-lg font-semibold">{offer.title}</span>
        {offer.enrolled && <Badge tone="ok">вы записаны</Badge>}
        <Badge tone={st.tone}>{st.text}</Badge>
      </div>
      <p className="text-sm text-fg-soft">
        {[offer.subject.name, offer.levels.map((l) => LEVEL_LABELS[l]).join(", ")].filter(Boolean).join(" · ")}
      </p>
      <p className="text-sm">{fmtOfferSchedule(offer.schedule)}</p>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <b>{priceText(offer.price)}</b>
        <span className="text-fg-soft">{seatsText(offer)}</span>
        {offer.status === "recruiting" && (
          <span className="text-fg-soft">запись до {new Date(`${offer.enroll_until}T00:00:00`).toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}</span>
        )}
      </div>
      {showTutor && (
        <div className="flex items-center gap-2 border-t border-line pt-3 text-sm">
          <Avatar url={offer.tutor.photo_url} name={offer.tutor.full_name} size={28} />
          <span className="font-medium">{offer.tutor.full_name}</span>
          <Rating rating={offer.tutor.rating} count={offer.tutor.reviews_count} />
        </div>
      )}
    </Link>
  );
}

/** Программа — нумерованный список тем. */
export function Program({ items }: { items: string[] }) {
  if (!items.length) return <p className="text-sm text-fg-soft">Программа не указана.</p>;
  return (
    <ol className="list-inside list-decimal space-y-1 text-sm">
      {items.map((t, i) => (
        <li key={i}>{t}</li>
      ))}
    </ol>
  );
}

function emptyInput(): OfferInput {
  const today = new Date();
  const enroll = new Date(today.getTime() + 7 * 864e5);
  const start = new Date(today.getTime() + 10 * 864e5);
  return {
    title: "",
    subject_id: "",
    levels: [],
    description: "",
    program: [],
    schedule: { weekdays: [], time: "18:00", duration_min: 60, start_date: toDateInput(start), lessons_count: 16, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone },
    price: 800,
    min_students: 3,
    max_students: 8,
    enroll_until: toDateInput(enroll),
    private: false,
  };
}

export function toInput(o: GroupOffer): OfferInput {
  return {
    title: o.title, subject_id: o.subject.id, levels: o.levels, description: o.description, program: o.program, schedule: o.schedule,
    price: o.price, min_students: o.min_students, max_students: o.max_students, enroll_until: o.enroll_until, private: o.private,
  };
}

/** Программа из своего шаблона КТП — темы уроков по порядку. */
function ImportFromPlan({ onImport }: { onImport: (topics: string[]) => void }) {
  const templates = useLoad(() => planning.templates("mine"), []);
  const [busy, setBusy] = useState(false);
  if (!templates.data?.length) return null;
  return (
    <select
      className="h-9 rounded-lg border border-line bg-surface px-2 text-sm"
      value=""
      disabled={busy}
      onChange={async (e) => {
        if (!e.target.value) return;
        setBusy(true);
        try {
          const t = await planning.template(e.target.value);
          onImport(t.lessons.map((l) => l.topic).filter(Boolean));
        } finally {
          setBusy(false);
        }
      }}
    >
      <option value="">Взять темы из КТП…</option>
      {templates.data.map((t) => (
        <option key={t.id} value={t.id}>
          {t.title}
        </option>
      ))}
    </select>
  );
}

/** Форма набора: создать или изменить (до запуска группы). */
export function OfferForm({ offer, onSaved }: { offer?: GroupOffer; onSaved: (o: GroupOffer) => void }) {
  const subjects = useLoad(() => content.subjects(), []);
  const [form, setForm] = useState<OfferInput>(() => (offer ? toInput(offer) : emptyInput()));
  const [programText, setProgramText] = useState(() => (offer?.program ?? []).join("\n"));
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof OfferInput>(k: K, v: OfferInput[K]) => setForm((f) => ({ ...f, [k]: v }));
  const setSchedule = <K extends keyof OfferInput["schedule"]>(k: K, v: OfferInput["schedule"][K]) =>
    setForm((f) => ({ ...f, schedule: { ...f.schedule, [k]: v } }));

  return (
    <form
      className="space-y-5"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(undefined);
        const data = { ...form, program: programText.split("\n").map((t) => t.trim()).filter(Boolean) };
        try {
          onSaved(offer ? await marketplace.updateOffer(offer.id, data) : await marketplace.createOffer(data));
        } catch (err) {
          setError(errorText(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      {error && <Alert>{error}</Alert>}
      <Field label="Название группы" required minLength={3} maxLength={120} placeholder="ОГЭ по математике, 9 класс" value={form.title} onChange={(e) => set("title", e.target.value)} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Select label="Предмет" required value={form.subject_id} onChange={(e) => set("subject_id", e.target.value)}>
          <option value="">Выберите</option>
          {subjects.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </Select>
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">Для кого</legend>
          <div className="flex flex-wrap gap-1.5">
            {(Object.keys(LEVEL_LABELS) as TutorLevel[]).map((l) => {
              const on = form.levels.includes(l);
              return (
                <button
                  key={l}
                  type="button"
                  aria-pressed={on}
                  onClick={() => set("levels", on ? form.levels.filter((x) => x !== l) : [...form.levels, l])}
                  className={`rounded-lg border px-2.5 py-1 text-sm ${on ? "border-brand bg-brand/10 text-brand" : "border-line text-fg-soft"}`}
                >
                  {LEVEL_LABELS[l]}
                </button>
              );
            })}
          </div>
        </fieldset>
      </div>
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium">Описание</span>
        <textarea rows={4} maxLength={5000} className={TEXTAREA} value={form.description} onChange={(e) => set("description", e.target.value)}
          placeholder="Чему научатся, как проходят занятия, что нужно знать заранее" />
      </label>
      <div>
        <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm font-medium">Программа — по теме на строке</span>
          <ImportFromPlan onImport={(topics) => setProgramText(topics.join("\n"))} />
        </div>
        <textarea rows={6} className={TEXTAREA} value={programText} onChange={(e) => setProgramText(e.target.value)} placeholder={"Дроби\nПроценты\nУравнения"} />
      </div>

      <fieldset className="space-y-3 rounded-xl bg-muted p-4">
        <legend className="px-1 text-sm font-medium">Расписание</legend>
        <div className="flex flex-wrap gap-1.5">
          {WEEKDAYS.map((w, i) => {
            const on = form.schedule.weekdays.includes(i);
            return (
              <button
                key={w}
                type="button"
                aria-pressed={on}
                onClick={() => setSchedule("weekdays", on ? form.schedule.weekdays.filter((x) => x !== i) : [...form.schedule.weekdays, i].sort())}
                className={`h-9 w-10 rounded-lg text-sm font-medium ${on ? "bg-brand text-white" : "bg-surface text-fg-soft"}`}
              >
                {w}
              </button>
            );
          })}
        </div>
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Время" type="time" required value={form.schedule.time} onChange={(e) => setSchedule("time", e.target.value)} />
          <Select label="Длительность" value={form.schedule.duration_min} onChange={(e) => setSchedule("duration_min", Number(e.target.value) as OfferInput["schedule"]["duration_min"])}>
            {[30, 45, 60, 90, 120].map((d) => (
              <option key={d} value={d}>
                {d} мин
              </option>
            ))}
          </Select>
          <Field label="Первое занятие" type="date" required value={form.schedule.start_date} onChange={(e) => setSchedule("start_date", e.target.value)} />
          <Field label="Занятий в курсе" type="number" min={1} max={200} value={form.schedule.lessons_count ?? ""}
            onChange={(e) => setSchedule("lessons_count", e.target.value ? Number(e.target.value) : null)} />
        </div>
      </fieldset>

      <div className="grid gap-3 sm:grid-cols-4">
        <Field label="Цена за занятие, ₽" type="number" min={0} step={50} required value={form.price} hint="0 — бесплатно" onChange={(e) => set("price", Number(e.target.value))} />
        <Field label="Минимум учеников" type="number" min={1} max={15} required value={form.min_students} hint="Без него группа не стартует" onChange={(e) => set("min_students", Number(e.target.value))} />
        <Field label="Максимум" type="number" min={1} max={15} required value={form.max_students} onChange={(e) => set("max_students", Number(e.target.value))} />
        <Field label="Запись до" type="date" required value={form.enroll_until} onChange={(e) => set("enroll_until", e.target.value)} />
      </div>
      <label className="flex items-start gap-3">
        <input type="checkbox" checked={form.private} onChange={(e) => set("private", e.target.checked)} className="mt-1 h-4 w-4 accent-brand" />
        <span className="text-sm">
          <span className="font-medium">Закрытая группа</span>
          <span className="block text-fg-soft">Не показывается в каталоге и профиле — записаться можно только по ссылке.</span>
        </span>
      </label>
      <Button type="submit" loading={busy} disabled={!form.schedule.weekdays.length || !form.subject_id} className="w-full sm:w-auto">
        {offer ? "Сохранить" : "Опубликовать набор"}
      </Button>
    </form>
  );
}
