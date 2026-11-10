"use client";

import { Info } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { FOUNDER } from "@/lib/founder";

/** Кнопка на фотографии с карточкой учителя: мышью — при наведении, на телефоне и с клавиатуры — нажатием. */
export function HeroInfo({ className }: { className: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const pointer = useRef<string | null>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div
      ref={root}
      className={`absolute -translate-x-1/2 -translate-y-1/2 ${className}`}
      onPointerEnter={(e) => e.pointerType === "mouse" && setOpen(true)}
      onPointerLeave={(e) => e.pointerType === "mouse" && setOpen(false)}
    >
      <button
        type="button"
        aria-label="Об учителе"
        aria-expanded={open}
        aria-controls={panelId}
        onPointerDown={(e) => {
          pointer.current = e.pointerType;
        }}
        onClick={() => {
          // Мышью карточка уже открыта наведением: нажатие не должно её закрывать.
          if (pointer.current !== "mouse") setOpen(!open);
          pointer.current = null;
        }}
        className="relative grid h-9 w-9 place-items-center rounded-full bg-brand text-on-brand shadow-lg ring-4 ring-surface/80 transition hover:scale-110 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand"
      >
        {!open && <span aria-hidden className="absolute inset-0 rounded-full bg-brand opacity-40 motion-safe:animate-ping" />}
        <Info size={20} strokeWidth={2.2} aria-hidden className="relative" />
      </button>
      {/* Прозрачная верхняя часть держит наведение, пока курсор идёт от кнопки к карточке. */}
      {/* Пока фото небольшое, ниже кнопки места нет: первый экран обрезал бы карточку, поэтому она открывается вверх. */}
      <div id={panelId} hidden={!open} className="absolute bottom-full left-1/2 z-10 w-64 -translate-x-1/2 pb-3 lg:top-full lg:bottom-auto lg:w-72 lg:pt-3 lg:pb-0">
        <div className="relative rounded-2xl bg-brand-strong p-4 text-on-brand shadow-2xl">
          <span aria-hidden className="absolute -bottom-1.5 left-1/2 h-3 w-3 -translate-x-1/2 rotate-45 rounded-[2px] bg-brand-strong lg:-top-1.5 lg:bottom-auto" />
          <p className="font-semibold">{FOUNDER.name}</p>
          <p className="mt-0.5 text-sm opacity-75">Учитель информатики</p>
          <dl className="mt-3 grid grid-cols-2 gap-3">
            {FOUNDER.stats.map((s) => (
              <div key={s.label}>
                <dd className="text-3xl leading-none font-bold tracking-tight">{s.value}</dd>
                <dt className="mt-1 text-xs leading-tight opacity-75">{s.label}</dt>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </div>
  );
}
