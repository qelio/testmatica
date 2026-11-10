import { Check, ShieldCheck, Star, UserRound, type LucideIcon } from "lucide-react";

import type { LandingIcon } from "@/lib/server-api";

// Маленькие анимированные сценки для плиток «Что ещё есть на платформе».

const delay = (i: number, step = 0.22) => ({ animationDelay: `${i * step}s` });

function Journal() {
  const grades = ["5", "4", "5", "Н", "5", "3", "4", "5", "4", "5", "5", "4", "Н", "5", "4"];
  return (
    <div className="grid w-full grid-cols-5 gap-1.5">
      {grades.map((g, i) => (
        <span
          key={i}
          style={delay(i)}
          className={`tm-loop grid h-10 place-items-center rounded-lg bg-surface font-bold shadow-sm ${g === "Н" ? "text-danger" : g === "3" ? "text-tutor" : "text-ok"}`}
        >
          {g}
        </span>
      ))}
    </div>
  );
}

function VideoCall() {
  return (
    <div className="relative flex w-full gap-2">
      <span className="absolute top-2 left-2 z-10 flex items-center gap-1.5 rounded-md bg-surface px-2 py-1 text-xs font-bold">
        <span className="tm-blink h-2 w-2 rounded-full bg-danger" />
        REC
      </span>
      {[0, 1, 2].map((i) => (
        <span key={i} className="grid h-32 flex-1 place-items-center rounded-2xl bg-surface shadow-sm">
          <span className="relative grid h-12 w-12 place-items-center rounded-full bg-muted text-fg-soft">
            {i === 1 && <span aria-hidden className="absolute inset-0 rounded-full bg-brand/40 motion-safe:animate-ping" />}
            <UserRound size={24} className="relative" aria-hidden />
          </span>
        </span>
      ))}
    </div>
  );
}

function AutoCheck() {
  return (
    <div className="relative w-full rounded-2xl bg-surface p-4 font-mono text-sm shadow-sm">
      <p className="tm-type overflow-hidden whitespace-nowrap">for i in range(5):</p>
      <p className="tm-type overflow-hidden pl-5 whitespace-nowrap [animation-delay:1s]">print(i * 2)</p>
      <span className="tm-loop mt-3 inline-flex items-center gap-1.5 rounded-full bg-ok/15 px-3 py-1 font-sans text-sm font-bold text-ok [animation-delay:2.4s]">
        <Check size={16} aria-hidden /> Верно
      </span>
    </div>
  );
}

function Rating() {
  return (
    <div className="w-full rounded-2xl bg-surface p-4 shadow-sm">
      <div className="flex items-center gap-3">
        <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-muted text-fg-soft">
          <UserRound size={24} aria-hidden />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block h-3 w-3/5 rounded-full bg-muted" />
          <span className="mt-2 block h-2.5 w-4/5 rounded-full bg-muted" />
        </span>
      </div>
      <span className="mt-4 flex gap-1.5">
        {[0, 1, 2, 3, 4].map((i) => (
          <span key={i} className="relative">
            <Star size={26} className="text-line" aria-hidden />
            <Star size={26} style={delay(i, 0.3)} className="tm-loop absolute inset-0 fill-sun text-sun" aria-hidden />
          </span>
        ))}
      </span>
    </div>
  );
}

function Chart() {
  return (
    <svg aria-hidden viewBox="0 0 320 130" className="h-32 w-full overflow-visible" preserveAspectRatio="none">
      {[0, 1, 2, 3, 4, 5, 6].map((i) => {
        const h = [46, 62, 54, 78, 70, 96, 112][i];
        return <rect key={i} x={i * 46 + 6} y={130 - h} width="30" height={h} rx="7" style={delay(i, 0.14)} className="tm-grow fill-brand/30" />;
      })}
      <path d="M21 88 L67 70 L113 78 L159 52 L205 60 L251 32 L297 14" pathLength={1} className="tm-draw-loop stroke-brand" fill="none" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Proctor() {
  return (
    <div className="relative h-32 w-full overflow-hidden rounded-2xl bg-surface p-4 shadow-sm">
      <span className="block h-2.5 w-2/3 rounded-full bg-muted" />
      <span className="mt-2.5 block h-2.5 w-full rounded-full bg-muted" />
      <span className="mt-2.5 block h-2.5 w-4/5 rounded-full bg-muted" />
      <span className="tm-loop absolute right-3 bottom-3 inline-flex items-center gap-1.5 rounded-full bg-danger/15 px-3 py-1 text-xs font-bold text-danger [animation-delay:1.2s]">
        Смена вкладки
      </span>
      <ShieldCheck size={30} className="absolute bottom-3 left-3 text-brand-text" aria-hidden />
      <span aria-hidden className="tm-scan absolute inset-x-0 top-0 h-0.5 bg-brand" />
    </div>
  );
}

const SCENES: Partial<Record<LandingIcon, () => React.JSX.Element>> = {
  graduation: Journal,
  video: VideoCall,
  check: AutoCheck,
  users: Rating,
  chart: Chart,
  shield: Proctor,
};

export function FeatureArt({ kind, Icon, className = "" }: { kind: LandingIcon; Icon: LucideIcon; className?: string }) {
  const Scene = SCENES[kind];
  return (
    <div aria-hidden className={`flex min-h-36 items-center ${className}`}>
      {Scene ? <Scene /> : <Icon size={72} strokeWidth={1.4} className="tm-bob text-brand-text" />}
    </div>
  );
}
