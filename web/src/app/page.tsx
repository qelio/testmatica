import {
  BookOpen,
  CalendarDays,
  ChartLine,
  CircleCheck,
  GraduationCap,
  type LucideIcon,
  Mail,
  MapPin,
  MessageSquare,
  Phone,
  Send,
  ShieldCheck,
  Sparkles,
  Target,
  Users,
  Video,
  Wallet,
} from "lucide-react";
import Link from "next/link";

import { NewsCard } from "@/components/news-card";
import { PublicShell } from "@/components/public-shell";
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
  subtitle: "Тестматика объединяет инструменты школьного учителя, маркетплейс репетиторов и библиотеку знаний с заданиями.",
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

  return (
    <PublicShell wide>
      {/* Первый экран */}
      <section className="border-b border-line bg-gradient-to-b from-brand/10 to-transparent">
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-16 sm:px-6 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] md:py-24">
          <div>
            <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl">{hero.title}</h1>
            {hero.subtitle && <p className="mt-5 max-w-2xl text-lg text-fg-soft">{hero.subtitle}</p>}
            <div className="mt-8 flex flex-wrap gap-3">
              {hero.primary_text && hero.primary_href && (
                <Link href={hero.primary_href} className="rounded-xl bg-brand px-5 py-3 font-medium text-white hover:bg-brand-strong">
                  {hero.primary_text}
                </Link>
              )}
              {hero.secondary_text && hero.secondary_href && (
                <Link href={hero.secondary_href} className="rounded-xl border border-line bg-surface px-5 py-3 font-medium hover:bg-muted">
                  {hero.secondary_text}
                </Link>
              )}
            </div>
          </div>
          {data?.hero_image_url && (
            // Картинка из хранилища по временной ссылке — обычный img, без оптимизатора Next.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={data.hero_image_url} alt="" className="w-full rounded-3xl border border-line object-cover shadow-sm" />
          )}
        </div>
      </section>

      {data?.sections.stats && data.stats.length > 0 && (
        <section className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
          <dl className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-4">
            {data.stats.map((st) => (
              <div key={st.label} className="rounded-2xl border border-line bg-surface p-5 text-center">
                <dt className="sr-only">{st.label}</dt>
                <dd className="text-3xl font-semibold text-brand">{st.value}</dd>
                <p className="mt-1 text-sm text-fg-soft">{st.label}</p>
              </div>
            ))}
          </dl>
        </section>
      )}

      {data?.sections.features && data.features.length > 0 && (
        <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Что есть на платформе</h2>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.features.map((f) => {
              const Icon = ICONS[f.icon] ?? Sparkles;
              return (
                <div key={f.title} className="rounded-2xl border border-line bg-surface p-5">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand/10 text-brand">
                    <Icon size={20} aria-hidden />
                  </span>
                  <h3 className="mt-3 font-semibold">{f.title}</h3>
                  {f.text && <p className="mt-1.5 text-sm text-fg-soft">{f.text}</p>}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {data?.sections.steps && (data.steps.students.length > 0 || data.steps.teachers.length > 0) && (
        <section className="border-y border-line bg-muted/50">
          <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
            <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{data.steps.title}</h2>
            <div className="mt-6 grid gap-6 md:grid-cols-2">
              {(
                [
                  ["Ученикам", data.steps.students],
                  ["Педагогам", data.steps.teachers],
                ] as const
              ).map(([who, steps]) =>
                steps.length ? (
                  <div key={who} className="rounded-2xl border border-line bg-surface p-6">
                    <h3 className="text-lg font-semibold">{who}</h3>
                    <ol className="mt-4 space-y-3">
                      {steps.map((step, i) => (
                        <li key={i} className="flex gap-3">
                          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-brand text-sm font-semibold text-white">{i + 1}</span>
                          <span className="pt-0.5">{step}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : null,
              )}
            </div>
          </div>
        </section>
      )}

      {data?.sections.teachers && teachers.length > 0 && (
        <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{data.teachers.title}</h2>
              {data.teachers.subtitle && <p className="mt-2 max-w-2xl text-fg-soft">{data.teachers.subtitle}</p>}
            </div>
            <Link href="/tutors" className="font-medium text-brand hover:underline">
              Все репетиторы →
            </Link>
          </div>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            {teachers.map((t) => (
              <TutorCardView key={t.user_id} tutor={notes.get(t.user_id) ? { ...t, headline: notes.get(t.user_id)! } : t} />
            ))}
          </div>
        </section>
      )}

      {data?.sections.news && data.latest_news.length > 0 && (
        <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{data.news.title}</h2>
            <Link href="/news" className="font-medium text-brand hover:underline">
              Все новости →
            </Link>
          </div>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {data.latest_news.map((n) => (
              <NewsCard key={n.id} news={n} />
            ))}
          </div>
        </section>
      )}

      {data?.sections.faq && data.faq.length > 0 && (
        <section className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Частые вопросы</h2>
          <div className="mt-6 divide-y divide-line rounded-2xl border border-line bg-surface">
            {data.faq.map((f) => (
              <details key={f.q} className="group px-5 py-4">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 font-medium">
                  {f.q}
                  <span className="text-fg-soft transition group-open:rotate-45">+</span>
                </summary>
                <p className="mt-2 whitespace-pre-line text-fg-soft">{f.a}</p>
              </details>
            ))}
          </div>
        </section>
      )}

      <Footer contacts={data?.contacts} />
    </PublicShell>
  );
}

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
          <p className="font-semibold">Тестматика</p>
          {contacts?.text && <p className="text-sm text-fg-soft">{contacts.text}</p>}
        </div>
        {items.length > 0 && (
          <ul className="space-y-2 text-sm">
            {items.map(({ icon: Icon, text, href }) => (
              <li key={text} className="flex items-center gap-2">
                <Icon size={16} className="text-fg-soft" aria-hidden />
                {href ? (
                  <a href={href} className="hover:text-brand" target={href.startsWith("http") ? "_blank" : undefined} rel="noreferrer">
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
        </nav>
      </div>
    </footer>
  );
}
