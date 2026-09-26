"use client";

import Link from "next/link";
import { useState } from "react";

import { AttachButton, UploadChips, useUploads } from "@/components/files";
import { ReviewsAboutMe } from "@/components/reviews";
import { Avatar } from "@/components/tutor-card";
import { Alert, Badge, Button, Field, Spinner } from "@/components/ui";
import { content, marketplace, type MyTutorProfile, type TutorFormat, type TutorLevel, type TutorProfileInput } from "@/lib/api";
import { FORMAT_LABELS, LEVEL_LABELS } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

const TEXTAREA =
  "w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

export default function ProfilePage() {
  const data = useLoad(() => marketplace.myProfile(), []);
  if (data.error) return <Alert>{data.error}</Alert>;
  if (!data.data) return <Spinner />;
  return <ProfileEditor key={data.data.profile.user_id} initial={data.data} />;
}

function toInput(p: MyTutorProfile): TutorProfileInput {
  return {
    published: p.profile.published,
    headline: p.profile.headline,
    about: p.profile.about,
    photo_file_id: p.photo_file_id,
    subject_ids: p.profile.subjects.map((s) => s.id),
    levels: p.profile.levels,
    formats: p.profile.formats,
    price: p.profile.price,
    experience_years: p.profile.experience_years,
  };
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((x) => x !== value) : [...list, value];
}

function ProfileEditor({ initial }: { initial: MyTutorProfile }) {
  const subjects = useLoad(() => content.subjects(), []);
  const [saved, setSaved] = useState(initial);
  const [form, setForm] = useState<TutorProfileInput>(() => toInput(initial));
  const photo = useUploads("avatar", 1);
  const [error, setError] = useState<string>();
  const [info, setInfo] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const set = <K extends keyof TutorProfileInput>(k: K, v: TutorProfileInput[K]) => setForm((f) => ({ ...f, [k]: v }));
  const photoUrl = photo.items[0]?.file?.url ?? saved.profile.photo_url;

  async function save(published = form.published) {
    setBusy(true);
    setError(undefined);
    setInfo(undefined);
    try {
      const next = await marketplace.saveProfile({ ...form, published, photo_file_id: photo.ids[0] ?? form.photo_file_id });
      setSaved(next);
      setForm(toInput(next));
      photo.clear();
      setInfo(next.profile.published ? "Сохранено. Профиль виден в поиске." : "Сохранено.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Профиль репетитора</h1>
          <p className="mt-1 text-sm text-fg-soft">Ученики находят вас в поиске и пишут через платформу — контакты не публикуются.</p>
        </div>
        <div className="flex gap-2">
          <Link href={`/tutors/${saved.profile.user_id}`} target="_blank" className="rounded-xl border border-line px-4 py-2 text-sm font-medium hover:bg-muted">
            Открыть профиль
          </Link>
          <Button
            variant="secondary"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(saved.profile.share_url);
                setCopied(true);
              } catch {
                window.prompt("Ссылка на профиль", saved.profile.share_url);
              }
            }}
          >
            {copied ? "Скопировано" : "Поделиться"}
          </Button>
        </div>
      </div>

      <section className={`rounded-2xl border p-5 ${saved.profile.published ? "border-ok/40 bg-ok/5" : "border-line bg-surface"}`}>
        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            checked={form.published}
            disabled={busy}
            onChange={(e) => {
              set("published", e.target.checked);
              void save(e.target.checked);
            }}
            className="mt-1 h-5 w-5 accent-ok"
          />
          <span>
            <span className="font-medium">Показывать меня в поиске репетиторов</span>
            <span className="block text-sm text-fg-soft">
              Если вы работаете только со своими классами бесплатно — оставьте выключенным.
            </span>
          </span>
        </label>
        {saved.missing.length > 0 && (
          <p className="mt-3 text-sm text-tutor">Чтобы появиться в поиске, заполните: {saved.missing.join(", ").toLowerCase()}.</p>
        )}
      </section>

      {error && <Alert>{error}</Alert>}
      {info && <Alert kind="success">{info}</Alert>}

      <form
        className="space-y-5 rounded-2xl border border-line bg-surface p-5"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <div className="flex flex-wrap items-center gap-4">
          <Avatar url={photoUrl} name={saved.profile.full_name} size={80} />
          <div className="space-y-1">
            <AttachButton onFiles={photo.add} label="Загрузить фото" />
            <UploadChips items={photo.items.filter((u) => u.status !== "done")} onRemove={photo.remove} />
            <p className="text-xs text-fg-soft">JPG или PNG до 5 МБ. Фото сохранится вместе с профилем.</p>
          </div>
        </div>
        <Field
          label="Коротко о себе"
          placeholder="Математика ЕГЭ и ОГЭ, 10 лет опыта"
          maxLength={150}
          value={form.headline}
          onChange={(e) => set("headline", e.target.value)}
        />
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Подробно: как занимаетесь, чего добиваются ученики</span>
          <textarea rows={6} maxLength={5000} className={TEXTAREA} value={form.about} onChange={(e) => set("about", e.target.value)} />
        </label>

        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">Предметы</legend>
          <div className="flex flex-wrap gap-1.5">
            {subjects.data?.map((s) => {
              const on = form.subject_ids.includes(s.id);
              return (
                <button
                  key={s.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() => set("subject_ids", toggle(form.subject_ids, s.id))}
                  className={`rounded-lg border px-2.5 py-1 text-sm ${on ? "border-brand bg-brand/10 text-brand" : "border-line text-fg-soft hover:text-fg"}`}
                >
                  {s.name}
                </button>
              );
            })}
          </div>
        </fieldset>

        <div className="grid gap-4 sm:grid-cols-2">
          <fieldset>
            <legend className="mb-1.5 text-sm font-medium">С кем занимаетесь</legend>
            {(Object.keys(LEVEL_LABELS) as TutorLevel[]).map((l) => (
              <label key={l} className="flex items-center gap-2 py-0.5 text-sm">
                <input type="checkbox" checked={form.levels.includes(l)} onChange={() => set("levels", toggle(form.levels, l))} className="h-4 w-4 accent-brand" />
                {LEVEL_LABELS[l]}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend className="mb-1.5 text-sm font-medium">Формат</legend>
            {(Object.keys(FORMAT_LABELS) as TutorFormat[]).map((f) => (
              <label key={f} className="flex items-center gap-2 py-0.5 text-sm">
                <input type="checkbox" checked={form.formats.includes(f)} onChange={() => set("formats", toggle(form.formats, f))} className="h-4 w-4 accent-brand" />
                {FORMAT_LABELS[f]}
              </label>
            ))}
          </fieldset>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            label="Ориентировочная цена за 60 минут, ₽"
            type="number"
            min={100}
            step={50}
            value={form.price ?? ""}
            hint="В поиске — «от». Итоговую цену предлагает ученик, договариваетесь в чате."
            onChange={(e) => set("price", e.target.value ? Number(e.target.value) : null)}
          />
          <Field
            label="Опыт, лет"
            type="number"
            min={0}
            max={70}
            value={form.experience_years ?? ""}
            onChange={(e) => set("experience_years", e.target.value ? Number(e.target.value) : null)}
          />
        </div>
        <Button type="submit" loading={busy || photo.busy}>
          Сохранить
        </Button>
      </form>

      <Education profile={saved} onChanged={setSaved} />
      <ReviewsAboutMe />
    </div>
  );
}

const STATUS = {
  pending: { text: "на проверке", tone: "neutral" },
  approved: { text: "подтверждён", tone: "ok" },
  rejected: { text: "не принят", tone: "warn" },
} as const;

function Education({ profile, onChanged }: { profile: MyTutorProfile; onChanged: (p: MyTutorProfile) => void }) {
  const file = useUploads("document", 1);
  const [form, setForm] = useState({ title: "", institution: "", year: "" });
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  return (
    <section className="space-y-4 rounded-2xl border border-line bg-surface p-5">
      <div>
        <h2 className="text-lg font-semibold">Образование</h2>
        <p className="mt-1 text-sm text-fg-soft">
          Дипломы, курсы, сертификаты. Модератор проверит каждый документ; в профиле появится бейдж «Образование подтверждено». Файлы видит только
          модератор.
        </p>
      </div>
      {error && <Alert>{error}</Alert>}
      {profile.education.length > 0 && (
        <ul className="divide-y divide-line rounded-xl border border-line">
          {profile.education.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-sm">
              <span className="min-w-0 flex-1">
                <b>{d.title}</b> — {d.institution}, {d.year}
                {d.status === "rejected" && d.comment && <span className="block text-tutor">Модератор: {d.comment}</span>}
              </span>
              {d.status && <Badge tone={STATUS[d.status].tone}>{STATUS[d.status].text}</Badge>}
              <button
                className="text-fg-soft hover:text-danger"
                onClick={async () => {
                  if (!window.confirm("Удалить документ?")) return;
                  try {
                    onChanged(await marketplace.deleteEducation(d.id));
                  } catch (e) {
                    setError(errorText(e));
                  }
                }}
              >
                Удалить
              </button>
            </li>
          ))}
        </ul>
      )}
      <form
        className="grid gap-3 sm:grid-cols-[1fr_1fr_6rem]"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!file.ids[0]) {
            setError("Прикрепите скан или фото документа");
            return;
          }
          setBusy(true);
          setError(undefined);
          try {
            onChanged(await marketplace.addEducation({ ...form, year: Number(form.year), file_id: file.ids[0] }));
            setForm({ title: "", institution: "", year: "" });
            file.clear();
          } catch (err) {
            setError(errorText(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Документ" placeholder="Диплом учителя математики" required maxLength={200} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <Field label="Учреждение" placeholder="МПГУ" required maxLength={200} value={form.institution} onChange={(e) => setForm({ ...form, institution: e.target.value })} />
        <Field label="Год" type="number" required min={1950} max={2100} value={form.year} onChange={(e) => setForm({ ...form, year: e.target.value })} />
        <div className="flex flex-wrap items-center gap-2 sm:col-span-3">
          <AttachButton onFiles={file.add} label="Прикрепить скан (PDF или фото)" />
          <UploadChips items={file.items} onRemove={file.remove} />
          <Button type="submit" variant="secondary" loading={busy || file.busy} className="ml-auto">
            Отправить на проверку
          </Button>
        </div>
      </form>
    </section>
  );
}
