"use client";

import Link from "next/link";
import { useState } from "react";

import { ImagePicker } from "@/components/image-picker";
import { Avatar } from "@/components/tutor-card";
import { Alert, Badge, Button, Field, Select, Spinner } from "@/components/ui";
import { marketplace, site, type TutorCard } from "@/lib/api";
import { errorText, useLoad } from "@/lib/hooks";
import type { Landing, LandingIcon, LandingOut } from "@/lib/server-api";

import { NewsTab } from "./news-tab";

const TEXTAREA =
  "w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

const ICONS: [LandingIcon, string][] = [
  ["sparkles", "Звёздочки"],
  ["graduation", "Шапочка"],
  ["book", "Книга"],
  ["users", "Люди"],
  ["calendar", "Календарь"],
  ["video", "Видео"],
  ["chart", "График"],
  ["shield", "Щит"],
  ["target", "Мишень"],
  ["message", "Сообщение"],
  ["wallet", "Кошелёк"],
  ["check", "Галочка"],
];

const SECTIONS: [keyof Landing["sections"], string][] = [
  ["stats", "Цифры"],
  ["features", "Преимущества"],
  ["steps", "Как это работает"],
  ["teachers", "Преподаватели"],
  ["news", "Новости"],
  ["faq", "Частые вопросы"],
];

type Tab = "landing" | "teachers" | "news";

/** Главная страница сайта: содержимое, преподаватели, новости — меняет администратор. */
export default function SiteEditorPage() {
  const [tab, setTab] = useState<Tab>("landing");
  const loaded = useLoad(() => site.landing(), []);
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Главная страница</h1>
        <Link href="/" target="_blank" className="rounded-xl border border-line px-4 py-2 text-sm font-medium hover:bg-muted">
          Открыть сайт ↗
        </Link>
      </div>
      <div className="flex rounded-xl border border-line bg-muted p-1 text-sm sm:w-fit" role="tablist">
        {(
          [
            ["landing", "Главная"],
            ["teachers", "Преподаватели"],
            ["news", "Новости"],
          ] as const
        ).map(([key, title]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`flex-1 rounded-lg px-4 py-1.5 font-medium whitespace-nowrap ${tab === key ? "bg-surface shadow-sm" : "text-fg-soft hover:text-fg"}`}
          >
            {title}
          </button>
        ))}
      </div>
      {tab === "news" ? (
        <NewsTab />
      ) : loaded.error ? (
        <Alert>{loaded.error}</Alert>
      ) : !loaded.data ? (
        <Spinner />
      ) : (
        <LandingForm key={loaded.data.updated_at ?? "default"} initial={loaded.data} tab={tab} />
      )}
    </div>
  );
}

function strip(d: LandingOut): Landing {
  const { hero_image_url: _url, latest_news: _news, updated_at: _at, ...rest } = d;
  void _url;
  void _news;
  void _at;
  return rest;
}

function LandingForm({ initial, tab }: { initial: LandingOut; tab: Tab }) {
  const [form, setForm] = useState<Landing>(() => strip(initial));
  const [imageUrl, setImageUrl] = useState(initial.hero_image_url);
  const [error, setError] = useState<string>();
  const [info, setInfo] = useState<string>();
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof Landing>(k: K, v: Landing[K]) => setForm((f) => ({ ...f, [k]: v }));

  async function save() {
    setBusy(true);
    setError(undefined);
    setInfo(undefined);
    try {
      const saved = await site.saveLanding(form);
      setImageUrl(saved.hero_image_url);
      setInfo("Сохранено. На сайте изменения появятся в течение 30 секунд.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      {error && <Alert>{error}</Alert>}
      {info && <Alert kind="success">{info}</Alert>}
      {tab === "landing" ? (
        <>
          <Section title="Первый экран">
            <Field label="Заголовок" required maxLength={200} value={form.hero.title} onChange={(e) => set("hero", { ...form.hero, title: e.target.value })} />
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium">Подзаголовок</span>
              <textarea rows={3} maxLength={600} className={TEXTAREA} value={form.hero.subtitle} onChange={(e) => set("hero", { ...form.hero, subtitle: e.target.value })} />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Главная кнопка" maxLength={40} value={form.hero.primary_text} onChange={(e) => set("hero", { ...form.hero, primary_text: e.target.value })} />
              <Field label="Её ссылка" placeholder="/register" value={form.hero.primary_href} onChange={(e) => set("hero", { ...form.hero, primary_href: e.target.value })} />
              <Field label="Вторая кнопка" maxLength={40} value={form.hero.secondary_text} onChange={(e) => set("hero", { ...form.hero, secondary_text: e.target.value })} />
              <Field label="Её ссылка" placeholder="/tutors" value={form.hero.secondary_href} onChange={(e) => set("hero", { ...form.hero, secondary_href: e.target.value })} />
            </div>
            <ImagePicker
              label="Картинка справа (необязательно)"
              url={imageUrl}
              onUploaded={(id, url) => {
                set("hero", { ...form.hero, image_file_id: id });
                setImageUrl(url);
              }}
              onClear={() => {
                set("hero", { ...form.hero, image_file_id: null });
                setImageUrl(null);
              }}
            />
          </Section>

          <Section title="Разделы на главной">
            <div className="flex flex-wrap gap-4">
              {SECTIONS.map(([key, title]) => (
                <label key={key} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form.sections[key]}
                    onChange={(e) => set("sections", { ...form.sections, [key]: e.target.checked })}
                    className="h-4 w-4 accent-brand"
                  />
                  {title}
                </label>
              ))}
            </div>
          </Section>

          <Section title="Цифры" hint="До 6 штук: «40 мин — бесплатных видеозанятий».">
            <ListEditor
              items={form.stats}
              max={6}
              empty={{ value: "", label: "" }}
              onChange={(v) => set("stats", v)}
              render={(item, update) => (
                <div className="grid flex-1 gap-2 sm:grid-cols-[8rem_1fr]">
                  <Field label="Значение" required maxLength={20} value={item.value} onChange={(e) => update({ ...item, value: e.target.value })} />
                  <Field label="Подпись" required maxLength={80} value={item.label} onChange={(e) => update({ ...item, label: e.target.value })} />
                </div>
              )}
            />
          </Section>

          <Section title="Преимущества" hint="До 9 карточек с иконкой.">
            <ListEditor
              items={form.features}
              max={9}
              empty={{ icon: "sparkles" as LandingIcon, title: "", text: "" }}
              onChange={(v) => set("features", v)}
              render={(item, update) => (
                <div className="grid flex-1 gap-2 sm:grid-cols-[9rem_1fr]">
                  <Select label="Иконка" value={item.icon} onChange={(e) => update({ ...item, icon: e.target.value as LandingIcon })}>
                    {ICONS.map(([v, t]) => (
                      <option key={v} value={v}>
                        {t}
                      </option>
                    ))}
                  </Select>
                  <Field label="Заголовок" required maxLength={80} value={item.title} onChange={(e) => update({ ...item, title: e.target.value })} />
                  <label className="block sm:col-span-2">
                    <span className="mb-1.5 block text-sm font-medium">Текст</span>
                    <textarea rows={2} maxLength={300} className={TEXTAREA} value={item.text} onChange={(e) => update({ ...item, text: e.target.value })} />
                  </label>
                </div>
              )}
            />
          </Section>

          <Section title="Как это работает" hint="По шагу на строке, до 6 для каждой колонки.">
            <Field label="Заголовок раздела" maxLength={80} value={form.steps.title} onChange={(e) => set("steps", { ...form.steps, title: e.target.value })} />
            <div className="grid gap-3 sm:grid-cols-2">
              {(["students", "teachers"] as const).map((who) => (
                <label key={who} className="block">
                  <span className="mb-1.5 block text-sm font-medium">{who === "students" ? "Ученикам" : "Педагогам"}</span>
                  <textarea
                    rows={5}
                    className={TEXTAREA}
                    value={form.steps[who].join("\n")}
                    onChange={(e) => set("steps", { ...form.steps, [who]: e.target.value.split("\n").slice(0, 6) })}
                  />
                </label>
              ))}
            </div>
          </Section>

          <Section title="Новости на главной">
            <div className="grid gap-3 sm:grid-cols-[1fr_10rem]">
              <Field label="Заголовок раздела" maxLength={80} value={form.news.title} onChange={(e) => set("news", { ...form.news, title: e.target.value })} />
              <Field label="Сколько последних" type="number" min={1} max={6} value={form.news.count} onChange={(e) => set("news", { ...form.news, count: Number(e.target.value) })} />
            </div>
            <p className="text-sm text-fg-soft">Сами новости — на вкладке «Новости».</p>
          </Section>

          <Section title="Частые вопросы">
            <ListEditor
              items={form.faq}
              max={20}
              empty={{ q: "", a: "" }}
              onChange={(v) => set("faq", v)}
              render={(item, update) => (
                <div className="flex-1 space-y-2">
                  <Field label="Вопрос" required maxLength={200} value={item.q} onChange={(e) => update({ ...item, q: e.target.value })} />
                  <label className="block">
                    <span className="mb-1.5 block text-sm font-medium">Ответ</span>
                    <textarea rows={2} maxLength={2000} className={TEXTAREA} value={item.a} onChange={(e) => update({ ...item, a: e.target.value })} />
                  </label>
                </div>
              )}
            />
          </Section>

          <Section title="Контакты (подвал сайта)">
            <Field label="Текст" maxLength={300} value={form.contacts.text} onChange={(e) => set("contacts", { ...form.contacts, text: e.target.value })} />
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Email" value={form.contacts.email} onChange={(e) => set("contacts", { ...form.contacts, email: e.target.value })} />
              <Field label="Телефон" value={form.contacts.phone} onChange={(e) => set("contacts", { ...form.contacts, phone: e.target.value })} />
              <Field label="Telegram (ссылка)" placeholder="https://t.me/…" value={form.contacts.telegram} onChange={(e) => set("contacts", { ...form.contacts, telegram: e.target.value })} />
              <Field label="ВКонтакте (ссылка)" placeholder="https://vk.com/…" value={form.contacts.vk} onChange={(e) => set("contacts", { ...form.contacts, vk: e.target.value })} />
              <Field label="Адрес" value={form.contacts.address} onChange={(e) => set("contacts", { ...form.contacts, address: e.target.value })} />
            </div>
          </Section>
        </>
      ) : (
        <TeachersEditor value={form.teachers} onChange={(v) => set("teachers", v)} />
      )}
      <div className="sticky bottom-4 flex justify-end">
        <Button onClick={save} loading={busy} className="shadow-lg">
          Сохранить главную
        </Button>
      </div>
    </div>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 rounded-2xl border border-line bg-surface p-5">
      <div>
        <h2 className="font-semibold">{title}</h2>
        {hint && <p className="text-sm text-fg-soft">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

/** Список однотипных карточек: добавить, удалить, поменять местами. */
function ListEditor<T>({
  items,
  max,
  empty,
  onChange,
  render,
}: {
  items: T[];
  max: number;
  empty: T;
  onChange: (items: T[]) => void;
  render: (item: T, update: (next: T) => void) => React.ReactNode;
}) {
  const move = (i: number, d: number) => {
    const next = [...items];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    onChange(next);
  };
  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <div key={i} className="flex items-start gap-3 rounded-xl bg-muted p-3">
          {render(item, (next) => onChange(items.map((x, j) => (j === i ? next : x))))}
          <div className="flex flex-col gap-1 pt-6 text-sm">
            <button type="button" disabled={i === 0} onClick={() => move(i, -1)} className="text-fg-soft hover:text-fg disabled:opacity-30" aria-label="Выше">
              ↑
            </button>
            <button type="button" disabled={i === items.length - 1} onClick={() => move(i, 1)} className="text-fg-soft hover:text-fg disabled:opacity-30" aria-label="Ниже">
              ↓
            </button>
            <button type="button" onClick={() => onChange(items.filter((_, j) => j !== i))} className="text-fg-soft hover:text-danger" aria-label="Удалить">
              ✕
            </button>
          </div>
        </div>
      ))}
      {items.length < max && (
        <Button variant="secondary" onClick={() => onChange([...items, empty])}>
          + Добавить
        </Button>
      )}
    </div>
  );
}

/** Преподаватели на главной: выбрать репетиторов платформы, порядок и своя подпись. */
function TeachersEditor({ value, onChange }: { value: Landing["teachers"]; onChange: (v: Landing["teachers"]) => void }) {
  const ids = value.items.map((t) => t.user_id);
  const cards = useLoad(() => marketplace.tutorsByIds(ids), [ids.join()]);
  const [q, setQ] = useState("");
  const [found, setFound] = useState<TutorCard[] | null>(null);
  const byId = new Map((cards.data?.items ?? []).map((t) => [t.user_id, t]));

  const move = (i: number, d: number) => {
    const next = [...value.items];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    onChange({ ...value, items: next });
  };

  return (
    <div className="space-y-5">
      <Section title="Раздел «Преподаватели»">
        <Field label="Заголовок" maxLength={80} value={value.title} onChange={(e) => onChange({ ...value, title: e.target.value })} />
        <Field label="Подзаголовок" maxLength={300} value={value.subtitle} onChange={(e) => onChange({ ...value, subtitle: e.target.value })} />
      </Section>
      <Section title="На главной" hint="До 12 репетиторов. Показываются только опубликованные профили; подпись заменяет «коротко о себе».">
        {!value.items.length && <p className="text-sm text-fg-soft">Пока никого — найдите репетиторов ниже.</p>}
        <ul className="space-y-2">
          {value.items.map((item, i) => {
            const t = byId.get(item.user_id);
            return (
              <li key={item.user_id} className="flex flex-wrap items-center gap-3 rounded-xl bg-muted p-3">
                <Avatar url={t?.photo_url ?? null} name={t?.full_name ?? "?"} size={40} />
                <span className="min-w-40 flex-1">
                  <span className="block font-medium">{t?.full_name ?? "Профиль скрыт или не найден"}</span>
                  <span className="block text-xs text-fg-soft">{t?.headline}</span>
                </span>
                <input
                  className="h-9 min-w-56 flex-1 rounded-lg border border-line bg-surface px-3 text-sm"
                  placeholder="Своя подпись (необязательно)"
                  maxLength={200}
                  value={item.note}
                  onChange={(e) => onChange({ ...value, items: value.items.map((x, j) => (j === i ? { ...x, note: e.target.value } : x)) })}
                />
                <span className="flex gap-2 text-sm">
                  <button type="button" disabled={i === 0} onClick={() => move(i, -1)} className="text-fg-soft disabled:opacity-30" aria-label="Выше">
                    ↑
                  </button>
                  <button type="button" disabled={i === value.items.length - 1} onClick={() => move(i, 1)} className="text-fg-soft disabled:opacity-30" aria-label="Ниже">
                    ↓
                  </button>
                  <button type="button" onClick={() => onChange({ ...value, items: value.items.filter((_, j) => j !== i) })} className="text-fg-soft hover:text-danger" aria-label="Убрать">
                    ✕
                  </button>
                </span>
              </li>
            );
          })}
        </ul>
      </Section>
      <Section title="Добавить репетитора">
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            setFound((await marketplace.search({ q, sort: "rating" }, true)).items);
          }}
        >
          <div className="min-w-64 flex-1">
            <Field label="Поиск по имени или описанию" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <Button type="submit" variant="secondary">
            Найти
          </Button>
        </form>
        {found && (
          <ul className="divide-y divide-line rounded-xl border border-line">
            {found.length === 0 && <li className="px-3 py-2 text-sm text-fg-soft">Никого не нашли среди опубликованных профилей.</li>}
            {found.map((t) => {
              const added = ids.includes(t.user_id);
              return (
                <li key={t.user_id} className="flex items-center gap-3 px-3 py-2">
                  <Avatar url={t.photo_url} name={t.full_name} size={32} />
                  <span className="min-w-0 flex-1 truncate text-sm">
                    <b>{t.full_name}</b> · {t.headline}
                  </span>
                  {t.rating !== null && <Badge>★ {t.rating}</Badge>}
                  <Button
                    variant="secondary"
                    className="h-8"
                    disabled={added || value.items.length >= 12}
                    onClick={() => onChange({ ...value, items: [...value.items, { user_id: t.user_id, note: "" }] })}
                  >
                    {added ? "Уже на главной" : "Добавить"}
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </Section>
    </div>
  );
}
