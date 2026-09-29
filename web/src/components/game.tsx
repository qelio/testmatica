"use client";

import {
  BookOpen,
  CalendarCheck,
  CalendarDays,
  ClipboardCheck,
  Code,
  Flame,
  Footprints,
  Gem,
  Lock,
  type LucideIcon,
  Medal,
  Mountain,
  Star,
  Target,
  Trophy,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { assessment, type Game, type GameAchievement, type UserInfo } from "@/lib/api";
import { confetti } from "@/lib/confetti";
import { useLoad } from "@/lib/hooks";

const ACHIEVEMENT_ICONS: Record<string, LucideIcon> = {
  footprints: Footprints,
  target: Target,
  medal: Medal,
  trophy: Trophy,
  flame: Flame,
  "calendar-check": CalendarCheck,
  "clipboard-check": ClipboardCheck,
  star: Star,
  gem: Gem,
  code: Code,
  mountain: Mountain,
};

// Цвета значков по кругу — классы целиком, чтобы Tailwind их нашёл.
const BADGE_TONES = [
  "bg-sun/20 text-sun",
  "bg-pink/15 text-pink",
  "bg-sky/15 text-sky",
  "bg-mint/15 text-mint",
  "bg-grape/15 text-grape",
  "bg-brand/15 text-brand",
];

const TILES: { href: string; title: string; icon: LucideIcon; tone: string }[] = [
  { href: "/dashboard/assignments", title: "Назначенные тесты", icon: ClipboardCheck, tone: "from-brand to-grape" },
  { href: "/dashboard/schedule", title: "Расписание", icon: CalendarDays, tone: "from-sky to-brand" },
  { href: "/dashboard/grades", title: "Оценки", icon: Star, tone: "from-sun to-pink" },
  { href: "/dashboard/exams", title: "ЕГЭ и ОГЭ", icon: Target, tone: "from-pink to-grape" },
  { href: "/dashboard/library", title: "Библиотека", icon: BookOpen, tone: "from-mint to-sky" },
];

const WEEKDAYS = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];

function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

/** Главная ученика в игровой форме: уровень и опыт, серия дней, разделы и достижения. */
export function StudentHome({ user }: { user: UserInfo }) {
  const game = useLoad(() => assessment.myGame(user.timezone), [user.timezone]);
  const fresh = useFreshAchievements(user.id, game.data);
  return (
    <div className="space-y-5">
      {game.data ? (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <LevelCard game={game.data} name={user.full_name.split(" ")[0]} />
          <StreakCard game={game.data} />
        </div>
      ) : (
        !game.error && <div className="h-48 animate-pulse rounded-3xl bg-muted" />
      )}
      <nav className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {TILES.map(({ href, title, icon: Icon, tone }) => (
          <Link
            key={href}
            href={href}
            className={`group flex flex-col justify-between gap-6 rounded-2xl bg-gradient-to-br ${tone} p-4 text-white shadow-sm transition hover:-translate-y-1 hover:shadow-lg`}
          >
            <Icon size={26} className="transition group-hover:scale-110 group-hover:-rotate-6" aria-hidden />
            <span className="font-semibold">{title}</span>
          </Link>
        ))}
      </nav>
      {game.data && <Achievements items={game.data.achievements} fresh={fresh} />}
    </div>
  );
}

function LevelCard({ game, name }: { game: Game; name: string }) {
  const { level, xp } = game;
  const pct = Math.min(100, ((xp - level.xp_from) / (level.xp_to - level.xp_from)) * 100);
  const left = level.xp_to - xp;
  return (
    <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand via-grape to-pink p-6 text-white shadow-lg shadow-grape/20">
      <div aria-hidden className="pointer-events-none absolute -top-12 -right-12 h-44 w-44 rounded-full bg-sun/40 blur-2xl" />
      <div aria-hidden className="pointer-events-none absolute -bottom-16 left-10 h-40 w-40 rounded-full bg-sky/40 blur-2xl" />
      <div className="relative flex items-center gap-5">
        <div className="grid h-20 w-20 shrink-0 place-items-center rounded-full border-4 border-white/40 bg-white/15 backdrop-blur">
          <span className="text-center leading-none">
            <span className="block text-3xl font-bold">{level.number}</span>
            <span className="text-[10px] font-semibold tracking-wider uppercase opacity-80">уровень</span>
          </span>
        </div>
        <div className="min-w-0">
          <p className="text-white/80">Привет, {name}!</p>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{level.title}</h1>
        </div>
      </div>
      <div className="relative mt-6">
        <div className="flex items-center justify-between text-sm font-medium">
          <span className="inline-flex items-center gap-1">
            <Zap size={15} className="fill-sun text-sun" aria-hidden /> {xp} опыта
          </span>
          <span className="text-white/80">
            до уровня {level.number + 1}: {left}
          </span>
        </div>
        <div
          className="mt-2 h-3 overflow-hidden rounded-full bg-white/20"
          role="progressbar"
          aria-valuemin={level.xp_from}
          aria-valuemax={level.xp_to}
          aria-valuenow={xp}
          aria-label="Опыт до следующего уровня"
        >
          <div className="h-full rounded-full bg-gradient-to-r from-sun to-white transition-[width] duration-700" style={{ width: `${pct}%` }} />
        </div>
        <p className="mt-3 text-sm text-white/80">
          Решено задач: <b className="text-white">{game.solved}</b> · сдано тестов: <b className="text-white">{game.tests}</b>
        </p>
      </div>
    </section>
  );
}

function StreakCard({ game }: { game: Game }) {
  const today = new Date();
  const labels = game.week.map((_, i) => WEEKDAYS[(today.getDay() - (6 - i) + 7) % 7]);
  return (
    <section className="flex flex-col rounded-3xl border border-line bg-surface p-6 shadow-sm">
      <div className="flex items-center gap-3">
        <span className={`grid h-14 w-14 place-items-center rounded-2xl ${game.streak ? "bg-sun/20 text-sun" : "bg-muted text-fg-soft"}`}>
          <Flame size={30} className={game.streak ? "fill-sun/40" : ""} aria-hidden />
        </span>
        <div>
          <p className="text-3xl leading-none font-bold">
            {game.streak} <span className="text-base font-semibold">{plural(game.streak, "день", "дня", "дней")} подряд</span>
          </p>
          <p className="mt-1 text-sm text-fg-soft">Рекорд: {game.best_streak}</p>
        </div>
      </div>
      <ol className="mt-5 grid grid-cols-7 gap-1.5">
        {game.week.map((active, i) => (
          <li key={i} className="text-center">
            <span
              className={`grid aspect-square place-items-center rounded-xl text-xs font-bold ${
                active ? "bg-gradient-to-br from-sun to-pink text-white" : i === 6 ? "border-2 border-dashed border-sun/60 text-sun" : "bg-muted text-fg-soft"
              }`}
              title={active ? "Занимался" : "Нет решений"}
            >
              {active ? "✓" : ""}
            </span>
            <span className="mt-1 block text-[11px] text-fg-soft">{labels[i]}</span>
          </li>
        ))}
      </ol>
      <p className="mt-auto pt-4 text-sm text-fg-soft">
        {game.today_active
          ? "Сегодня уже засчитано — так держать!"
          : game.streak
            ? "Реши сегодня хотя бы одну задачу, чтобы не прервать серию."
            : "Реши задачу сегодня — и начнётся новая серия."}
      </p>
    </section>
  );
}

function Achievements({ items, fresh }: { items: GameAchievement[]; fresh: Set<string> }) {
  const earned = items.filter((a) => a.earned).length;
  return (
    <section className="rounded-3xl border border-line bg-surface p-5 shadow-sm">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-lg font-semibold">Достижения</h2>
        <span className="text-sm text-fg-soft">
          {earned} из {items.length}
        </span>
      </div>
      <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {items.map((a, i) => {
          const Icon = ACHIEVEMENT_ICONS[a.icon] ?? Trophy;
          return (
            <li
              key={a.code}
              className={`relative rounded-2xl border p-3 ${a.earned ? "border-line bg-surface" : "border-dashed border-line bg-muted/40"} ${
                fresh.has(a.code) ? "tm-pop ring-2 ring-sun" : ""
              }`}
              title={a.text}
            >
              {fresh.has(a.code) && (
                <span className="absolute -top-2 right-2 rounded-full bg-sun px-2 py-0.5 text-[10px] font-bold text-white">Новое!</span>
              )}
              <div className="flex items-center gap-3">
                <span
                  className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${a.earned ? BADGE_TONES[i % BADGE_TONES.length] : "bg-muted text-fg-soft"}`}
                >
                  {a.earned ? <Icon size={22} aria-hidden /> : <Lock size={18} aria-hidden />}
                </span>
                <div className="min-w-0">
                  <p className={`truncate text-sm font-semibold ${a.earned ? "" : "text-fg-soft"}`}>{a.title}</p>
                  <p className="truncate text-xs text-fg-soft">{a.text}</p>
                </div>
              </div>
              {!a.earned && a.target > 1 && (
                <div className="mt-2.5 flex items-center gap-2">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-grape/70" style={{ width: `${(a.current / a.target) * 100}%` }} />
                  </div>
                  <span className="text-[11px] text-fg-soft tabular-nums">
                    {a.current}/{a.target}
                  </span>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** Достижения, полученные с прошлого визита (помним в браузере): подсвечиваем и запускаем конфетти. */
function useFreshAchievements(userId: string, game: Game | null | undefined): Set<string> {
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!game) return;
    const key = `achievements:${userId}`;
    const earned = game.achievements.filter((a) => a.earned).map((a) => a.code);
    let seen: string[] | null = null;
    try {
      seen = JSON.parse(localStorage.getItem(key) ?? "null");
      localStorage.setItem(key, JSON.stringify(earned));
    } catch {}
    if (!seen) return; // первый визит — всё полученное раньше не «новое»
    const added = earned.filter((c) => !seen.includes(c));
    if (added.length) {
      // Сравнение с сохранённым в браузере — после загрузки данных.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFresh(new Set(added));
      confetti();
    }
  }, [game, userId]);
  return fresh;
}
