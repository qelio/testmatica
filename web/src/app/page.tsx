import {
  BookOpen,
  CalendarDays,
  ChartLine,
  CircleCheck,
  Flame,
  GraduationCap,
  type LucideIcon,
  Mail,
  MapPin,
  MessageSquare,
  Phone,
  Send,
  ShieldCheck,
  Sparkles,
  Star,
  Target,
  Trophy,
  Users,
  Video,
  Wallet,
} from "lucide-react";
import Link from "next/link";

import { LegalBar } from "@/components/legal-bar";
import { NewsCard } from "@/components/news-card";
import { PublicShell } from "@/components/public-shell";
import { StartLink } from "@/components/start-link";
import { TutorCardView } from "@/components/tutor-card";
import { featuredTutors, type LandingIcon, type LandingOut, serverGet } from "@/lib/server-api";

const ICONS: Record<LandingIcon, LucideIcon> = {
  book: BookOpen,
  users: Users,
  calendar: CalendarDays,
  video: Video,
  chart: ChartLine,
  shield: ShieldCheck,
  sparkles: Sparkles,
  graduation: GraduationCap,
  target: Target,
  message: MessageSquare,
  wallet: Wallet,
  check: CircleCheck,
};

// Если сервис недоступен — хотя бы первый экран.
const FALLBACK_HERO: LandingOut["hero"] = {
  title: "Учите, учитесь и находите друг друга на одной платформе",
  subtitle: "ТестМатика объединяет инструменты школьного учителя, маркетплейс репетиторов и библиотеку знаний с заданиями.",
  primary_text: "Начать бесплатно",
  primary_href: "/register",
  secondary_text: "Найти репетитора",
  secondary_href: "/tutors",
  image_file_id: null,
};

/** Цвета карточек по кругу — классы целиком, чтобы Tailwind их нашёл. */
const TONES = [
  { icon: "bg-brand/15 text-brand-text", card: "hover:border-brand/40", glow: "from-brand/10" },
  { icon: "bg-pink/15 text-pink", card: "hover:border-pink/40", glow: "from-pink/10" },
  { icon: "bg-sun/20 text-sun", card: "hover:border-sun/50", glow: "from-sun/10" },
  { icon: "bg-sky/15 text-sky", card: "hover:border-sky/40", glow: "from-sky/10" },
  { icon: "bg-mint/15 text-mint", card: "hover:border-mint/40", glow: "from-mint/10" },
  { icon: "bg-grape/15 text-grape", card: "hover:border-grape/40", glow: "from-grape/10" },
];
const STAT_TONES = ["text-brand-text", "text-pink", "text-sun", "text-mint", "text-sky", "text-grape"];

/** Главная — содержимое задаёт администратор («Главная страница» в кабинете). Рендерится на сервере. */
export default async function Home() {
  const data = await serverGet<LandingOut>("/api/content/site/landing");
  const teachers = data?.sections.teachers ? await featuredTutors(data.teachers.items.map((t) => t.user_id)) : [];
  const notes = new Map((data?.teachers.items ?? []).map((t) => [t.user_id, t.note]));
  const hero = data?.hero ?? FALLBACK_HERO;

  return (
    <PublicShell wide>
      {/* Первый экран: цветные пятна на фоне и «живые» карточки платформы. */}
      <section className="relative overflow-hidden border-b border-line">
        <div aria-hidden className="pointer-events-none absolute inset-0">
          <div className="absolute -top-24 -left-24 h-96 w-96 rounded-full bg-grape/25 blur-3xl" />
          <div className="absolute top-10 right-0 h-80 w-80 rounded-full bg-sky/25 blur-3xl" />
          <div className="absolute -bottom-32 left-1/3 h-96 w-96 rounded-full bg-pink/20 blur-3xl" />
          <div className="absolute right-1/4 bottom-0 h-56 w-56 rounded-full bg-sun/25 blur-3xl" />
        </div>
        <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 sm:px-6 md:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] md:py-24">
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-brand/30 bg-surface/70 px-3 py-1 text-sm font-medium text-brand-text backdrop-blur">
              <Sparkles size={15} aria-hidden /> Учителям, репетиторам и ученикам
            </span>
            <h1 className="mt-5 bg-gradient-to-br from-fg via-brand to-school bg-clip-text text-4xl font-bold tracking-tight text-balance text-transparent sm:text-5xl lg:text-6xl">
              {hero.title}
            </h1>
            {hero.subtitle && <p className="mt-5 max-w-2xl text-lg text-fg-soft">{hero.subtitle}</p>}
            <div className="mt-8 flex flex-wrap gap-3">
              {hero.primary_text && hero.primary_href && (
                <StartLink
                  href={hero.primary_href}
                  text={hero.primary_text}
                  className="rounded-2xl bg-brand px-6 py-3.5 font-semibold text-on-brand shadow-lg shadow-brand/30 transition hover:-translate-y-0.5 hover:shadow-xl hover:shadow-brand/30"
                />
              )}
              {hero.secondary_text && hero.secondary_href && (
                <Link
                  href={hero.secondary_href}
                  className="rounded-2xl border border-line bg-surface/80 px-6 py-3.5 font-semibold backdrop-blur transition hover:-translate-y-0.5 hover:border-brand/40"
                >
                  {hero.secondary_text}
                </Link>
              )}
            </div>
          </div>
          <HeroArt imageUrl={data?.hero_image_url ?? null} />
        </div>
      </section>

      {data?.sections.stats && data.stats.length > 0 && (
        <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
          <dl className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-4">
            {data.stats.map((st, i) => (
              <div key={st.label} className="rounded-3xl border border-line bg-surface p-6 text-center shadow-sm">
                <dt className="sr-only">{st.label}</dt>
                <dd className={`text-4xl font-bold tracking-tight ${STAT_TONES[i % STAT_TONES.length]}`}>{st.value}</dd>
                <p className="mt-1 text-sm text-fg-soft">{st.label}</p>
              </div>
            ))}
          </dl>
        </section>
      )}

      {data?.sections.features && data.features.length > 0 && (
        <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
          <SectionTitle kicker="Возможности">Что есть на платформе</SectionTitle>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.features.map((f, i) => {
              const Icon = ICONS[f.icon] ?? Sparkles;
              const tone = TONES[i % TONES.length];
              return (
                <div
                  key={f.title}
                  className={`group rounded-3xl border border-line bg-gradient-to-br ${tone.glow} to-surface to-60% p-6 transition hover:-translate-y-1 hover:shadow-lg ${tone.card}`}
                >
                  <span className={`grid h-12 w-12 place-items-center rounded-2xl ${tone.icon} transition group-hover:scale-110 group-hover:-rotate-6`}>
                    <Icon size={24} aria-hidden />
                  </span>
                  <h3 className="mt-4 text-lg font-semibold">{f.title}</h3>
                  {f.text && <p className="mt-1.5 text-fg-soft">{f.text}</p>}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {data?.sections.steps && (data.steps.students.length > 0 || data.steps.teachers.length > 0) && (
        <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
          <SectionTitle kicker="Как начать">{data.steps.title}</SectionTitle>
          <div className="mt-8 grid gap-6 md:grid-cols-2">
            {(
              [
                ["Ученикам", data.steps.students, "from-sky to-brand-fill", "bg-sky"],
                ["Педагогам", data.steps.teachers, "from-sun to-pink", "bg-pink"],
              ] as const
            ).map(([who, steps, gradient, dot]) =>
              steps.length ? (
                <div key={who} className="overflow-hidden rounded-3xl border border-line bg-surface shadow-sm">
                  <h3 className={`bg-gradient-to-r ${gradient} px-6 py-4 text-lg font-semibold text-white`}>{who}</h3>
                  <ol className="space-y-4 p-6">
                    {steps.map((step, i) => (
                      <li key={i} className="flex gap-3">
                        <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full ${dot} text-sm font-bold text-white`}>{i + 1}</span>
                        <span className="pt-1">{step}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              ) : null,
            )}
          </div>
        </section>
      )}

      {data?.sections.teachers && teachers.length > 0 && (
        <section className="relative border-y border-line bg-gradient-to-b from-sun/10 via-transparent to-transparent">
          <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <SectionTitle kicker="Преподаватели">{data.teachers.title}</SectionTitle>
                {data.teachers.subtitle && <p className="mt-2 max-w-2xl text-fg-soft">{data.teachers.subtitle}</p>}
              </div>
              <Link href="/tutors" className="font-semibold text-brand-text hover:underline">
                Все репетиторы →
              </Link>
            </div>
            <div className="mt-8 grid gap-4 md:grid-cols-2">
              {teachers.map((t) => (
                <TutorCardView key={t.user_id} tutor={notes.get(t.user_id) ? { ...t, headline: notes.get(t.user_id)! } : t} />
              ))}
            </div>
          </div>
        </section>
      )}

      {data?.sections.news && data.latest_news.length > 0 && (
        <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <SectionTitle kicker="Новости">{data.news.title}</SectionTitle>
            <Link href="/news" className="font-semibold text-brand-text hover:underline">
              Все новости →
            </Link>
          </div>
          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {data.latest_news.map((n) => (
              <NewsCard key={n.id} news={n} />
            ))}
          </div>
        </section>
      )}

      {data?.sections.faq && data.faq.length > 0 && (
        <section className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
          <SectionTitle kicker="Вопросы и ответы">Частые вопросы</SectionTitle>
          <div className="mt-8 space-y-3">
            {data.faq.map((f, i) => (
              <details key={f.q} className="group rounded-2xl border border-line bg-surface px-5 py-4 open:shadow-sm">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 font-semibold">
                  {f.q}
                  <span
                    className={`grid h-7 w-7 shrink-0 place-items-center rounded-full text-lg transition group-open:rotate-45 ${TONES[i % TONES.length].icon}`}
                  >
                    +
                  </span>
                </summary>
                <p className="mt-2 whitespace-pre-line text-fg-soft">{f.a}</p>
              </details>
            ))}
          </div>
        </section>
      )}

      {hero.primary_text && hero.primary_href && (
        <section className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
          <div className="relative overflow-hidden rounded-[2rem] bg-gradient-to-r from-brand-fill via-school to-sky px-6 py-12 text-center text-white shadow-xl shadow-brand/20 sm:px-12">
            <div aria-hidden className="pointer-events-none absolute -top-10 -left-10 h-40 w-40 rounded-full bg-sun/40 blur-2xl" />
            <div aria-hidden className="pointer-events-none absolute -right-10 -bottom-10 h-48 w-48 rounded-full bg-sky/40 blur-2xl" />
            <h2 className="relative text-3xl font-bold tracking-tight sm:text-4xl">Готовы попробовать?</h2>
            <p className="relative mx-auto mt-3 max-w-xl text-white/85">Регистрация бесплатная, а первые задачи можно решить уже сегодня.</p>
            <StartLink
              href={hero.primary_href}
              text={hero.primary_text}
              className="relative mt-7 inline-block rounded-2xl bg-surface px-7 py-3.5 font-semibold text-fg shadow-lg transition hover:-translate-y-0.5"
            />
          </div>
        </section>
      )}

      <Footer contacts={data?.contacts} />
    </PublicShell>
  );
}

function SectionTitle({ kicker, children }: { kicker: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-sm font-semibold tracking-wide text-brand-text uppercase">{kicker}</p>
      <h2 className="mt-1 text-3xl font-bold tracking-tight sm:text-4xl">{children}</h2>
    </div>
  );
}

/** Иллюстрация первого экрана: картинка администратора (если есть) и парящие карточки — как выглядит учёба на платформе. */
function HeroArt({ imageUrl }: { imageUrl: string | null }) {
  return (
    <div aria-hidden className="relative mx-auto h-[22rem] w-full max-w-md sm:h-[26rem]">
      {imageUrl ? (
        // Картинка из хранилища по временной ссылке — обычный img, без оптимизатора Next.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={imageUrl} alt="" className="absolute inset-6 h-[calc(100%-3rem)] w-[calc(100%-3rem)] rounded-[2rem] border-4 border-surface object-cover shadow-2xl" />
      ) : (
        <div className="absolute inset-6 rounded-[2rem] border border-line bg-surface/80 p-6 shadow-2xl backdrop-blur">
          <p className="text-sm font-medium text-fg-soft">Задача дня</p>
          <p className="mt-1 text-lg font-semibold">Решите уравнение 2x − 6 = 0</p>
          <div className="mt-4 grid grid-cols-3 gap-2">
            {["x = −3", "x = 3", "x = 12"].map((o, i) => (
              <span
                key={o}
                className={`rounded-xl border px-2 py-2 text-center text-sm font-medium ${i === 1 ? "border-mint bg-mint/15 text-mint" : "border-line"}`}
              >
                {o}
              </span>
            ))}
          </div>
          <div className="mt-5">
            <div className="flex justify-between text-xs font-medium text-fg-soft">
              <span>Уровень 4 · Знаток</span>
              <span>240 / 300</span>
            </div>
            <div className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-muted">
              <div className="h-full w-4/5 rounded-full bg-gradient-to-r from-sun via-pink to-grape" />
            </div>
          </div>
          <div className="mt-5 flex gap-1.5">
            {["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((d, i) => (
              <span
                key={d}
                className={`grid h-8 flex-1 place-items-center rounded-lg text-xs font-semibold ${i < 5 ? "bg-sun/20 text-sun" : "bg-muted text-fg-soft"}`}
              >
                {d}
              </span>
            ))}
          </div>
        </div>
      )}
      <div className="tm-float absolute -top-1 -right-2 flex items-center gap-2 rounded-2xl border border-line bg-surface px-3 py-2 shadow-lg [--tilt:4deg]">
        <span className="grid h-8 w-8 place-items-center rounded-full bg-mint/15 text-mint">
          <CircleCheck size={18} />
        </span>
        <span className="text-sm font-semibold">
          Верно! <span className="text-mint">+10 опыта</span>
        </span>
      </div>
      <div className="tm-float absolute bottom-16 -left-4 flex items-center gap-2 rounded-2xl border border-line bg-surface px-3 py-2 shadow-lg [--tilt:-5deg] [animation-delay:-2s]">
        <span className="grid h-8 w-8 place-items-center rounded-full bg-sun/20 text-sun">
          <Flame size={18} />
        </span>
        <span className="text-sm font-semibold">5 дней подряд</span>
      </div>
      <div className="tm-float absolute -right-3 bottom-2 flex items-center gap-2 rounded-2xl border border-line bg-surface px-3 py-2 shadow-lg [--tilt:3deg] [animation-delay:-4s]">
        <span className="grid h-8 w-8 place-items-center rounded-full bg-grape/15 text-grape">
          <Trophy size={18} />
        </span>
        <span className="text-sm font-semibold">Отличник</span>
        <Star size={14} className="fill-sun text-sun" />
      </div>
    </div>
  );
}

const IDEAS_EMAIL = "info@testmatica.ru";

function Footer({ contacts }: { contacts?: LandingOut["contacts"] }) {
  const items: { icon: LucideIcon; text: string; href?: string }[] = [];
  if (contacts?.email) items.push({ icon: Mail, text: contacts.email, href: `mailto:${contacts.email}` });
  if (contacts?.phone) items.push({ icon: Phone, text: contacts.phone, href: `tel:${contacts.phone.replace(/[^+\d]/g, "")}` });
  if (contacts?.telegram) items.push({ icon: Send, text: "Telegram", href: contacts.telegram });
  if (contacts?.vk) items.push({ icon: MessageSquare, text: "ВКонтакте", href: contacts.vk });
  if (contacts?.address) items.push({ icon: MapPin, text: contacts.address });
  return (
    <footer className="mt-8 border-t border-line bg-surface">
      <div className="mx-auto flex max-w-6xl flex-wrap items-start justify-between gap-6 px-4 py-10 sm:px-6">
        <div className="max-w-sm space-y-2">
          <p>
            <span className="font-logo font-bold text-leaf">ТестМатика</span> — Образовательная платформа
          </p>
          {contacts?.text && <p className="text-sm text-fg-soft">{contacts.text}</p>}
          <p className="flex items-center gap-2 text-sm">
            <Mail size={16} className="text-fg-soft" aria-hidden />
            <span className="text-fg-soft">Предложения и идеи:</span>
            <a href={`mailto:${IDEAS_EMAIL}`} className="font-medium text-brand-text hover:underline">
              {IDEAS_EMAIL}
            </a>
          </p>
        </div>
        {items.length > 0 && (
          <ul className="space-y-2 text-sm">
            {items.map(({ icon: Icon, text, href }) => (
              <li key={text} className="flex items-center gap-2">
                <Icon size={16} className="text-fg-soft" aria-hidden />
                {href ? (
                  <a href={href} className="hover:text-brand-text" target={href.startsWith("http") ? "_blank" : undefined} rel="noreferrer">
                    {text}
                  </a>
                ) : (
                  text
                )}
              </li>
            ))}
          </ul>
        )}
        <nav className="flex flex-col gap-2 text-sm text-fg-soft">
          <Link href="/tutors" className="hover:text-fg">
            Репетиторы
          </Link>
          <Link href="/groups" className="hover:text-fg">
            Группы
          </Link>
          <Link href="/library" className="hover:text-fg">
            Библиотека
          </Link>
          <Link href="/news" className="hover:text-fg">
            Новости
          </Link>
          <Link href="/legal" className="hover:text-fg">
            Документы
          </Link>
          {/* Для интерактивной доски в кабинете: открыть страницу с кодом без входа (решение №53). */}
          <Link href="/board" className="font-medium text-brand-text hover:underline">
            Показать экран на доске
          </Link>
        </nav>
      </div>
      <LegalBar />
    </footer>
  );
}
