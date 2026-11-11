"use client";

import { CalendarDays, ChartLine, ListChecks, NotebookPen, PenLine, Target } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useDarkMode } from "@/lib/theme";

// Ролики — настоящий интерфейс с локального стенда, ученики в них вымышленные (`public/landing/video`, постеры — `screens`).
const SCENES = [
  {
    id: "journal",
    title: "Журнал",
    Icon: NotebookPen,
    text: "Оценка за проверенную работу сама попадает в журнал.",
    label: "Журнал класса с оценками и посещаемостью",
  },
  {
    id: "results",
    title: "Тесты",
    Icon: ListChecks,
    text: "Сразу видно, кто сдал и какие оценки получились.",
    label: "Результаты теста по ученикам класса",
  },
  {
    id: "board",
    title: "Доска",
    Icon: PenLine,
    text: "Рисуйте вместе с учениками, доска сохраняется после урока.",
    label: "Онлайн-доска с разбором перевода чисел",
  },
  {
    id: "exams",
    title: "ЕГЭ и ОГЭ",
    Icon: Target,
    text: "Прогресс по каждому заданию экзамена.",
    label: "Прогресс ученика по заданиям ОГЭ",
  },
  {
    id: "analytics",
    title: "Аналитика",
    Icon: ChartLine,
    text: "Сразу видно, кому нужна помощь.",
    label: "Аналитика успеваемости класса",
  },
  {
    id: "schedule",
    title: "Расписание",
    Icon: CalendarDays,
    text: "Видеоурок открывается прямо из расписания.",
    label: "Расписание учителя",
  },
];

export function LandingShowcase() {
  const dark = useDarkMode();
  const theme = dark ? "dark" : "light";
  const [index, setIndex] = useState(0);
  const [progress, setProgress] = useState(0);
  const [reduced, setReduced] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const root = useRef<HTMLDivElement>(null);
  const tabs = useRef<HTMLDivElement>(null);
  const visible = useRef(false);
  const scene = SCENES[index];

  useEffect(() => {
    // Настройка системы известна только в браузере.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setReduced(window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }, []);

  // Ролик идёт, только пока блок на экране: лишнее не скачиваем и не отвлекаем.
  useEffect(() => {
    if (reduced || !root.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        visible.current = entry.isIntersecting;
        if (entry.isIntersecting) void video.current?.play().catch(() => {});
        else video.current?.pause();
      },
      { threshold: 0.35 },
    );
    observer.observe(root.current);
    return () => observer.disconnect();
  }, [reduced]);

  function select(i: number) {
    setIndex(i);
    setProgress(0);
    // На телефоне вкладки листаются: выбранная должна быть видна. Страницу при этом не двигаем.
    const box = tabs.current;
    const tab = box?.children[i] as HTMLElement | undefined;
    if (box && tab && box.scrollWidth > box.clientWidth) box.scrollTo({ left: tab.offsetLeft - box.clientWidth / 2 + tab.offsetWidth / 2, behavior: "smooth" });
  }

  return (
    <div ref={root} className="tm-reveal mt-8 overflow-hidden rounded-[2rem] bg-brand/10 px-4 pt-5 sm:px-8 sm:pt-8 lg:-mx-8">
      <div ref={tabs} className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:px-0 lg:justify-center">
        {SCENES.map((s, i) => {
          const active = i === index;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => select(i)}
              aria-pressed={active}
              className={`relative flex shrink-0 items-center gap-2 overflow-hidden rounded-full px-5 py-3 font-semibold transition-colors ${active ? "bg-surface text-fg shadow-sm" : "text-fg-soft hover:bg-surface/60 hover:text-fg"}`}
            >
              {active && !reduced && <span aria-hidden className="absolute inset-y-0 left-0 bg-brand/25 transition-[width] duration-200 ease-linear" style={{ width: `${progress * 100}%` }} />}
              <s.Icon size={18} strokeWidth={2} aria-hidden className="relative" />
              <span className="relative">{s.title}</span>
            </button>
          );
        })}
      </div>
      <p key={scene.id} className="tm-rise mt-5 text-center text-xl font-semibold">
        {scene.text}
      </p>
      <div className="mx-auto mt-6 max-w-5xl overflow-hidden rounded-t-2xl border border-b-0 border-line bg-surface shadow-xl">
        <div aria-hidden className="flex items-center gap-1.5 border-b border-line px-4 py-2.5">
          <span className="h-2.5 w-2.5 rounded-full bg-danger/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-sun/80" />
          <span className="h-2.5 w-2.5 rounded-full bg-ok/70" />
          <span className="ml-3 rounded-md bg-muted px-3 py-0.5 text-xs text-fg-soft">testmatica.ru</span>
        </div>
        <video
          key={`${scene.id}-${theme}`}
          ref={video}
          src={`/landing/video/${scene.id}-${theme}.mp4`}
          poster={`/landing/screens/${scene.id}-${theme}.jpg`}
          aria-label={scene.label}
          width={1440}
          height={900}
          muted
          playsInline
          preload="metadata"
          controls={reduced}
          onCanPlay={(e) => {
            if (!reduced && visible.current) void e.currentTarget.play().catch(() => {});
          }}
          onTimeUpdate={(e) => {
            const v = e.currentTarget;
            if (v.duration) setProgress(v.currentTime / v.duration);
          }}
          onEnded={() => select((index + 1) % SCENES.length)}
          className="block aspect-[16/10] w-full bg-muted object-cover"
        />
      </div>
    </div>
  );
}
