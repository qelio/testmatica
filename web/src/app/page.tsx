import {
  BookOpen,
  CalendarDays,
  ChartLine,
  CircleCheck,
  GraduationCap,
  ListChecks,
  type LucideIcon,
  Mail,
  MapPin,
  MessageSquare,
  Phone,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Star,
  Target,
  Users,
  Video,
  Wallet,
} from "lucide-react";
import Link from "next/link";

import { HeroInfo } from "@/components/hero-info";
import { LandingTasks } from "@/components/landing-tasks";
import { FeatureArt } from "@/components/landing-art";
import { Pixels, TopicsMarquee } from "@/components/landing-decor";
import { LandingShowcase } from "@/components/landing-showcase";
import { LogoMark } from "@/components/logo-mark";
import { LegalBar } from "@/components/legal-bar";
import { NewsCard } from "@/components/news-card";
import { PublicShell } from "@/components/public-shell";
import { StartLink } from "@/components/start-link";
import { APP_VERSION } from "@/lib/version";
import { TutorCardView } from "@/components/tutor-card";
import type { CourseSummary } from "@/lib/api";
import { pluralWord } from "@/lib/format";
import { FOUNDER } from "@/lib/founder";
import { OPERATOR } from "@/lib/legal";
import { featuredTutors, type LandingIcon, type LandingOut, serverGet } from "@/lib/server-api";

/** Яркие карточки курсов. Фиолетовый на сайте не используем. */
const COURSE_TONES = ["bg-lime text-logo-ink", "bg-sky text-logo-ink", "bg-sun text-logo-ink", "bg-brand-strong text-on-brand", "bg-pink text-logo-ink", "bg-danger text-on-danger"];
const COURSE_GLYPHS = ["</>", "x²", "01", "{ }", "π", "if"];
const STEP_ICONS: Record<"teachers" | "students", LucideIcon[]> = {
  teachers: [Users, ListChecks, ChartLine],
  students: [Search, Video, Star],
};
/** Мозаика возможностей: широкие и узкие плитки заполняют сетку без пустот. */
const FEATURE_TILES = [
  "bg-brand/10 lg:col-span-2",
  "bg-sky/15",
  "bg-sun/20",
  "bg-danger/10 lg:col-span-2",
  "bg-pink/15",
  "bg-muted lg:col-span-2",
];

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

/** Главная — содержимое задаёт администратор («Главная страница» в кабинете). Рендерится на сервере. */
export default async function Home() {
  const data = await serverGet<LandingOut>("/api/content/site/landing");
  const teachers = data?.sections.teachers ? await featuredTutors(data.teachers.items.map((t) => t.user_id)) : [];
  const notes = new Map((data?.teachers.items ?? []).map((t) => [t.user_id, t.note]));
  const hero = data?.hero ?? FALLBACK_HERO;
  const courses = (await serverGet<CourseSummary[]>("/api/content/catalog")) ?? [];
  const materials = courses.reduce((sum, c) => sum + c.materials_count, 0);

  return (
    <PublicShell wide>
      {/* Первый экран: мягкие цветные пятна на фоне, справа фотография с зелёной орбитой. */}
      <section className="relative flex flex-col overflow-hidden border-b border-line pt-[84px] lg:min-h-[min(100dvh,calc(46vw+180px))] xl:min-h-dvh">
        <div aria-hidden className="pointer-events-none absolute inset-0">
          <div className="absolute -top-24 -left-24 h-96 w-96 rounded-full bg-lime/30 blur-3xl" />
          <div className="absolute top-10 right-0 h-96 w-96 rounded-full bg-mint/15 blur-3xl" />
          <div className="absolute -bottom-32 left-1/4 h-96 w-96 rounded-full bg-pink/20 blur-3xl" />
        </div>
        <div className="relative mx-auto grid w-full max-w-[1446px] flex-1 items-end gap-8 px-4 sm:px-6 lg:px-[60px] md:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
          <div className="relative z-10 self-center pt-16 md:py-8 lg:py-16">
            <Pixels className="absolute top-8 right-4 hidden w-20 sm:block md:top-6 lg:right-16" />
            <span className="tm-rise inline-flex items-center gap-1.5 rounded-full border border-brand/30 bg-surface/70 px-3 py-1 text-sm font-medium text-brand-text backdrop-blur">
              <Sparkles size={15} aria-hidden /> Учителям, репетиторам и ученикам
            </span>
            <h1 className="tm-rise mt-5 bg-gradient-to-br [animation-delay:90ms] from-fg via-brand-text to-brand bg-clip-text text-4xl font-bold tracking-tight text-balance text-transparent sm:text-5xl md:text-[5vw] lg:text-[min(4.44vw,4rem)] lg:leading-[1.08] 2xl:text-7xl">
              {hero.title.replace("друг друга", "друг\u00a0друга") /* «друг друга» не разрываем: так заголовок ложится в четыре ровные строки */}
            </h1>
            {hero.subtitle && <p className="tm-rise mt-5 max-w-2xl text-lg text-fg-soft [animation-delay:180ms] md:max-w-[21rem] md:text-base lg:max-w-2xl lg:text-lg">{hero.subtitle}</p>}
            <div className="tm-rise mt-8 flex flex-wrap gap-3 [animation-delay:270ms]">
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
        <section className="mx-auto max-w-[1446px] px-4 py-12 sm:px-6 lg:px-[60px]">
          <dl className="tm-reveal-list grid gap-6 sm:grid-cols-3">
            {data.stats.map((st) => (
              <div key={st.label} className="border-t-2 border-fg pt-3">
                <dt className="sr-only">{st.label}</dt>
                <dd className="text-5xl font-bold tracking-tight">{st.value}</dd>
                <p className="mt-2 text-fg-soft">{st.label}</p>
              </div>
            ))}
          </dl>
        </section>
      )}

      <TopicsMarquee />

      <section className="mx-auto max-w-[1446px] px-4 py-12 sm:px-6 lg:px-[60px]">
        <SectionTitle>Как это выглядит внутри</SectionTitle>
        <p className="mt-3 max-w-2xl text-lg text-fg-soft">Настоящая платформа в работе, а не иллюстрации. Имена учеников вымышленные.</p>
        <LandingShowcase />
      </section>

      <section className="mx-auto max-w-[1446px] px-4 py-12 sm:px-6 lg:px-[60px]">
        <SectionTitle>Решите задачу прямо здесь</SectionTitle>
        <p className="mt-3 mb-8 max-w-2xl text-lg text-fg-soft">Две задачи из открытой библиотеки. Регистрироваться для этого не нужно.</p>
        <LandingTasks />
      </section>

      {courses.length > 0 && (
        <section className="mx-auto max-w-[1446px] px-4 py-12 sm:px-6 lg:px-[60px]">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <SectionTitle>Открытая библиотека</SectionTitle>
              <p className="mt-3 max-w-2xl text-lg text-fg-soft">
                {materials} {pluralWord(materials, "материал", "материала", "материалов")} в {courses.length} {pluralWord(courses.length, "курсе", "курсах", "курсах")}: теория, разборы и задачи с проверкой.
              </p>
            </div>
            <Link href="/library" className="font-semibold text-brand-text hover:underline">
              Вся библиотека →
            </Link>
          </div>
          <div className="tm-reveal-list mt-8 grid grid-cols-[repeat(auto-fit,minmax(min(100%,19rem),1fr))] gap-4 lg:-mx-8">
            {courses.slice(0, 6).map((c, i) => (
              <Link
                key={c.id}
                href={`/library/course/${c.id}`}
                className={`group relative flex h-64 flex-col justify-end overflow-hidden rounded-[2rem] p-7 transition-transform duration-300 hover:-translate-y-1.5 ${COURSE_TONES[i % COURSE_TONES.length]}`}
              >
                <span aria-hidden className="absolute -top-4 right-3 font-mono text-[8.5rem] leading-none font-bold opacity-20 transition-transform duration-500 group-hover:scale-110 group-hover:-rotate-6">
                  {COURSE_GLYPHS[i % COURSE_GLYPHS.length]}
                </span>
                <span className="relative text-sm font-semibold opacity-75">{c.subject?.name ?? "Курс"}</span>
                <span className="relative mt-1 text-2xl leading-tight font-bold">{c.title}</span>
                <span className="relative mt-3 inline-flex items-center gap-2 font-semibold">
                  {c.materials_count} {pluralWord(c.materials_count, "материал", "материала", "материалов")}
                  <span aria-hidden className="transition-transform group-hover:translate-x-1.5">→</span>
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {data?.sections.steps && (data.steps.students.length > 0 || data.steps.teachers.length > 0) && (
        <section className="mx-auto max-w-[1446px] px-4 py-12 sm:px-6 lg:px-[60px]">
          <SectionTitle>{data.steps.title}</SectionTitle>
          <div className="tm-reveal-list mt-8 grid gap-4 md:grid-cols-2 lg:-mx-8">
            {(
              [
                ["Учителям", data.steps.teachers, "teachers", "bg-brand-strong text-on-brand"],
                ["Ученикам", data.steps.students, "students", "bg-lime text-logo-ink"],
              ] as const
            ).map(([who, steps, key, tone]) =>
              steps.length ? (
                <div key={who} className={`relative overflow-hidden rounded-[2rem] p-7 sm:p-10 ${tone}`}>
                  {key === "teachers" ? <Pixels className="absolute top-8 right-8 w-20" /> : <LogoMark className="tm-bob absolute top-5 right-7 h-20 w-auto" />}
                  <h3 className="text-3xl font-bold tracking-tight sm:text-4xl">{who}</h3>
                  <ol className="relative mt-8 space-y-6">
                    <span aria-hidden className="absolute top-6 bottom-6 left-6 w-0.5 -translate-x-1/2 bg-current opacity-25" />
                    {steps.map((step, i) => {
                      const Icon = STEP_ICONS[key][i % STEP_ICONS[key].length];
                      return (
                        <li key={i} className="relative flex items-center gap-4">
                          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-surface text-fg shadow-sm">
                            <Icon size={22} strokeWidth={2} aria-hidden />
                          </span>
                          <span className="text-lg leading-snug font-semibold">{step}</span>
                        </li>
                      );
                    })}
                  </ol>
                </div>
              ) : null,
            )}
          </div>
        </section>
      )}

      {data?.sections.features && data.features.length > 0 && (
        <section className="mx-auto max-w-[1446px] px-4 py-12 sm:px-6 lg:px-[60px]">
          <SectionTitle>Что ещё есть на платформе</SectionTitle>
          <dl className="tm-reveal-list mt-8 grid gap-4 sm:grid-cols-2 lg:-mx-8 lg:grid-cols-3">
            {data.features.map((f, i) => {
              const tile = FEATURE_TILES[i % FEATURE_TILES.length];
              // В широкой плитке картинка и подпись стоят рядом, чтобы она заполнялась целиком.
              const wide = tile.includes("col-span-2");
              return (
                <div key={f.title} className={`flex flex-col justify-between gap-5 rounded-[2rem] p-7 ${tile} ${wide ? "lg:flex-row-reverse lg:items-center lg:gap-10 lg:p-10" : ""}`}>
                  <FeatureArt kind={f.icon} Icon={ICONS[f.icon] ?? Sparkles} className={wide ? "lg:w-3/5 lg:shrink-0" : ""} />
                  <div>
                    <dt className={`font-bold ${wide ? "text-2xl" : "text-xl"}`}>{f.title}</dt>
                    {f.text && <dd className="mt-1 text-fg-soft">{f.text}</dd>}
                  </div>
                </div>
              );
            })}
          </dl>
        </section>
      )}

      {data?.sections.teachers && teachers.length > 0 && (
        <section className="mx-auto max-w-[1446px] px-4 py-12 sm:px-6 lg:px-[60px]">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <SectionTitle>{data.teachers.title}</SectionTitle>
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
        </section>
      )}

      {data?.sections.news && data.latest_news.length > 0 && (
        <section className="mx-auto max-w-[1446px] px-4 py-12 sm:px-6 lg:px-[60px]">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <SectionTitle>{data.news.title}</SectionTitle>
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
        <section className="mx-auto max-w-[1446px] px-4 py-12 sm:px-6 lg:px-[60px]">
          <SectionTitle>Частые вопросы</SectionTitle>
          <div className="mt-8 divide-y divide-line border-y border-line">
            {data.faq.map((f) => (
              <details key={f.q} className="group py-5">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-lg font-semibold">
                  {f.q}
                  <span aria-hidden className="shrink-0 text-2xl leading-none text-fg-soft transition group-open:rotate-45">
                    +
                  </span>
                </summary>
                <p className="mt-3 max-w-3xl whitespace-pre-line text-fg-soft">{f.a}</p>
              </details>
            ))}
          </div>
        </section>
      )}

      {hero.primary_text && hero.primary_href && (
        <section className="mx-auto max-w-[1446px] px-4 py-8 sm:px-6 lg:px-[60px]">
          <div className="tm-reveal relative flex flex-wrap items-center justify-between gap-6 overflow-hidden rounded-[2rem] bg-brand-strong px-7 py-10 text-on-brand sm:px-12 lg:-mx-8">
            <Pixels className="absolute top-5 left-[46%] hidden w-24 md:block" />
            <LogoMark className="tm-bob absolute right-[30%] -bottom-3 hidden h-40 w-auto lg:block" />
            <div className="relative">
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Попробуйте на своём классе</h2>
              <p className="mt-2 text-lg opacity-80">Регистрация бесплатная, ничего устанавливать не нужно.</p>
            </div>
            <StartLink
              href={hero.primary_href}
              text={hero.primary_text}
              className="relative rounded-2xl bg-surface px-7 py-3.5 font-semibold text-fg transition hover:-translate-y-0.5"
            />
          </div>
        </section>
      )}

      <section className="mx-auto max-w-[1446px] px-4 py-12 sm:px-6 lg:px-[60px]">
        <SectionTitle>Администрация проекта</SectionTitle>
        <div className="tm-reveal mt-8 flex flex-col gap-6 sm:flex-row sm:items-start sm:gap-8">
          <span className="relative block h-36 w-36 shrink-0 sm:h-44 sm:w-44">
            <svg aria-hidden viewBox="0 0 100 100" className="tm-spin absolute inset-0 h-full w-full">
              <defs>
                <linearGradient id="founder-ring" x1="0" y1="1" x2="1" y2="0">
                  <stop offset="0" stopColor="#0b8a4f" />
                  <stop offset="1" stopColor="#b8f04a" />
                </linearGradient>
              </defs>
              <circle cx="50" cy="50" r="47.5" fill="none" stroke="url(#founder-ring)" strokeWidth="4" strokeLinecap="round" strokeDasharray="210 89" />
            </svg>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/landing/founder.jpg" alt={`${FOUNDER.name}, основатель ТестМатики`} width={240} height={240} loading="lazy" className="absolute inset-[9%] h-[82%] w-[82%] rounded-full object-cover" />
          </span>
          <div className="min-w-0">
            <h3 className="text-2xl font-bold tracking-tight sm:text-3xl">{FOUNDER.name}</h3>
            <p className="mt-3 text-xl font-semibold text-brand-text">Основатель проекта, программист и разработчик</p>
            <div className="mt-5 max-w-4xl space-y-4 text-lg leading-relaxed text-fg-soft">
              <p>
                ТестМатику придумал и создаёт человек, который каждый день сам заходит в класс. Сейчас Вячеслав работает учителем информатики в школе
                №293 имени Твардовского, поэтому хорошо знает, сколько сил уходит на журнал, проверку работ и подготовку к уроку.
              </p>
              <p>
                В нём соединились две профессии: программист, которому важно, чтобы всё работало точно, и учитель, которому важно, чтобы ученик понял. Так
                появилась платформа, где журнал, задачи с автопроверкой, доска и видеоурок собраны в одном месте, а у учителя остаётся больше времени на
                самое главное — на учеников.
              </p>
            </div>
            <dl className="mt-8 flex flex-wrap gap-x-14 gap-y-5">
              {FOUNDER.stats.map((st) => (
                <div key={st.label}>
                  <dd className="text-5xl font-bold tracking-tight">{st.value}</dd>
                  <dt className="mt-1 text-fg-soft">{st.label}</dt>
                </div>
              ))}
            </dl>
            <p className="mt-8 text-lg">
              Написать напрямую:{" "}
              <a href={`mailto:${OPERATOR.email}`} className="font-semibold text-brand-text hover:underline">
                {OPERATOR.email}
              </a>
            </p>
          </div>
        </div>
      </section>

      <Footer contacts={data?.contacts} />
    </PublicShell>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="tm-reveal text-3xl font-bold tracking-tight sm:text-4xl">{children}</h2>;
}

/** Иллюстрация первого экрана: картинка администратора (если есть) и парящие карточки — как выглядит учёба на платформе. */
/** Участки орбиты в координатах макета: вокруг фотографии, поверх футболки ниже рук. */
const ORBIT = "M1640 905C1400 880 932 760 932 575C932 420 1250 246 1560 246C1640 246 1657 285 1655 315C1650 390 1580 445 1500 490";

function HeroArt({ imageUrl }: { imageUrl: string | null }) {
  if (imageUrl) {
    // Администратор загрузил свою картинку. Она из хранилища по временной ссылке — обычный img, без оптимизатора Next.
    return (
      <div aria-hidden className="relative mx-auto mb-16 w-full max-w-md self-center md:my-24">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={imageUrl} alt="" className="aspect-square w-full rounded-[2rem] border-4 border-surface object-cover shadow-2xl" />
      </div>
    );
  }
  return (
    <div className="relative mx-auto w-full max-w-lg md:mx-0 md:-mr-4 md:w-[56vw] md:max-w-none md:justify-self-end lg:-mr-8 lg:w-[min(calc(100dvh-84px),46vw,49rem)] lg:justify-self-end min-[106rem]:-mr-28 min-[106rem]:w-[min(calc(100dvh-84px),44vw,49rem)]">
      <svg aria-hidden viewBox="900 87 800 800" className="block w-full">
        <defs>
          <linearGradient id="hero-orbit" gradientUnits="userSpaceOnUse" x1="960" y1="900" x2="1660" y2="230">
            <stop offset="0" stopColor="#0b8a4f" />
            <stop offset="0.6" stopColor="#2db562" />
            <stop offset="0.85" stopColor="#8fe04f" />
            <stop offset="1" stopColor="#b8f04a" />
          </linearGradient>
          <clipPath id="hero-below-arms">
            <path d="M1103 819L1127 819L1167 819L1194 821L1227 819L1261 818L1288 815L1314 810L1341 805L1368 800L1395 790L1415 784L1428 782L1455 784L1489 785L1502 779L1542 776L1582 779L1602 759H1800V1000H1103Z" />
          </clipPath>
        </defs>
        <path d={ORBIT} pathLength={1} className="tm-orbit" fill="none" stroke="url(#hero-orbit)" strokeWidth="52" />
        <image href="/landing/hero-person.webp" x="966" y="87" width="728" height="970" className="tm-rise [animation-delay:120ms]" />
        <path d={ORBIT} pathLength={1} className="tm-orbit" fill="none" stroke="url(#hero-orbit)" strokeWidth="52" clipPath="url(#hero-below-arms)" />
      </svg>
      <HeroInfo className="top-[50%] left-[36%]" />
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
      <div className="mx-auto flex max-w-[1446px] flex-wrap items-start justify-between gap-6 px-4 py-10 sm:px-6 lg:px-[60px]">
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
          {APP_VERSION && <span>Версия {APP_VERSION}</span>}
        </nav>
      </div>
      <LegalBar wide />
    </footer>
  );
}
